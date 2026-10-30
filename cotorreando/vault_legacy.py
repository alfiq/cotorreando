"""Moves data from the format of older versions (a key wrapped with Windows DPAPI) to age.

The old key could be opened by any program of the same Windows account, so it is not
reused: everything is resealed to the new key and the old files are removed.
"""

from __future__ import annotations

import ctypes
import json
import logging
from ctypes import wintypes

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .paths import RECORDINGS_DIR
from .vault import RECORDS_DIR, VAULT_DIR, Vault, WrongPassword

log = logging.getLogger(__name__)

KEY_FILE = VAULT_DIR / "key.json"
LISTS = ("hard_words", "corrections", "training")


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _unprotect(data: bytes) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = _Blob(len(data), buffer), _Blob()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def pending() -> bool:
    return KEY_FILE.exists()


def needs_old_password() -> bool:
    return "salt" in json.loads(KEY_FILE.read_text(encoding="utf-8"))


def check_old_password(password: str | None) -> None:
    """Raises WrongPassword."""
    _old_key(password)


def _old_key(password: str | None) -> X25519PrivateKey:
    file = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    raw = _unprotect(bytes.fromhex(file["wrapped"]))
    if "salt" in file:
        if not password:
            raise WrongPassword
        key = Argon2id(salt=bytes.fromhex(file["salt"]), length=32, iterations=3, lanes=4,
                       memory_cost=65536).derive(password.encode("utf-8"))
        try:
            raw = AESGCM(key).decrypt(raw[:12], raw[12:], None)
        except InvalidTag as err:
            raise WrongPassword from err
    return X25519PrivateKey.from_private_bytes(raw)


def _open(key: X25519PrivateKey, sealed: bytes) -> bytes:
    shared = key.exchange(X25519PublicKey.from_public_bytes(sealed[:32]))
    derived = HKDF(hashes.SHA256(), 32, None, b"cotorreando-record").derive(shared)
    return AESGCM(derived).decrypt(sealed[32:44], sealed[44:], None)


def migrate(vault: Vault, old_password: str | None = None) -> None:
    """Reseal everything to ``vault``, which must have its new key. Old files go last."""
    key = _old_key(old_password)
    sealed = [*RECORDS_DIR.glob("*.sealed"), *RECORDINGS_DIR.glob("*/*.sealed")]
    resealed = {path: vault.seal(_open(key, path.read_bytes())) for path in sealed}
    for path, data in resealed.items():
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(data)
        temp.replace(path)
    for name in LISTS:
        path = VAULT_DIR / f"{name}.bin"
        if not path.exists():
            continue
        data = json.loads(_unprotect(path.read_bytes()).decode("utf-8"))
        if name == "training":   # the ids stay readable; the checkpoint they belonged to does not survive
            vault.set_trained_ids(data.get("trained", []))
        else:
            vault.save_private(name, data)
        path.unlink()
    (VAULT_DIR / "checkpoint.sealed").unlink(missing_ok=True)
    KEY_FILE.unlink()
    log.info("Moved %d records to the new key", len(sealed))
