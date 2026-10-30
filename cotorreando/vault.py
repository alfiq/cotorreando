"""Encrypted storage for everything learning keeps about the user's voice and words.

Records are sealed to a public key, so dictation can store them without being able
to read them back. The private key is wrapped with DPAPI, which ties it to this
Windows account on this PC, and optionally with a password as well. Nothing else
ever reaches the disk in clear: training receives the audio through a pipe.

Word lists and replacement rules are needed while dictating, before any password
could be asked for, so they are protected by DPAPI alone (``load_private`` /
``save_private``).
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import struct
import time
import uuid
import wave
from ctypes import wintypes
from pathlib import Path

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .audio import RATE
from .paths import DATA_DIR, RECORDINGS_DIR

log = logging.getLogger(__name__)

VAULT_DIR = DATA_DIR / "vault"
KEY_FILE = VAULT_DIR / "key.json"
RECORDS_DIR = VAULT_DIR / "records"
RAW = serialization.Encoding.Raw, serialization.PublicFormat.Raw


class WrongPassword(Exception):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(function, data: bytes) -> bytes:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = _Blob(len(data), buffer), _Blob()
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def protect(data: bytes) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    return _dpapi(crypt32.CryptProtectData, data)


def unprotect(data: bytes) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    return _dpapi(crypt32.CryptUnprotectData, data)


def _stretch(password: str, salt: bytes) -> bytes:
    return Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536).derive(
        password.encode("utf-8"))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)


def _derive(shared: bytes) -> bytes:
    return HKDF(hashes.SHA256(), 32, None, b"cotorreando-record").derive(shared)


class Vault:
    def __init__(self):
        self._private: X25519PrivateKey | None = None
        if KEY_FILE.exists():
            self._file = json.loads(KEY_FILE.read_text(encoding="utf-8"))
        else:
            private = X25519PrivateKey.generate()
            self._file = {"public": private.public_key().public_bytes(*RAW).hex()}
            self._store(private, None)
        self._public = X25519PublicKey.from_public_bytes(bytes.fromhex(self._file["public"]))

    def _store(self, private: X25519PrivateKey, password: str | None) -> None:
        raw = private.private_bytes_raw()
        self._file.pop("salt", None)
        if password:
            salt = os.urandom(16)
            nonce = os.urandom(12)
            raw = nonce + AESGCM(_stretch(password, salt)).encrypt(nonce, raw, None)
            self._file["salt"] = salt.hex()
        self._file["wrapped"] = protect(raw).hex()
        _write(KEY_FILE, json.dumps(self._file).encode("utf-8"))

    # -- password -------------------------------------------------------------

    @property
    def has_password(self) -> bool:
        return "salt" in self._file

    @property
    def locked(self) -> bool:
        return self._private is None and self.has_password

    def unlock(self, password: str | None = None) -> None:
        """Raises WrongPassword. Without a password set, none is needed."""
        if self._private is not None:
            return
        raw = unprotect(bytes.fromhex(self._file["wrapped"]))
        if self.has_password:
            if not password:
                raise WrongPassword
            try:
                raw = AESGCM(_stretch(password, bytes.fromhex(self._file["salt"]))).decrypt(
                    raw[:12], raw[12:], None)
            except InvalidTag as err:
                raise WrongPassword from err
        self._private = X25519PrivateKey.from_private_bytes(raw)

    def lock(self) -> None:
        self._private = None

    def set_password(self, password: str | None) -> None:
        """Change or remove the password. The vault must be unlocked."""
        self.unlock()
        self._store(self._private, password)

    # -- sealing --------------------------------------------------------------

    def seal(self, data: bytes) -> bytes:
        ephemeral = X25519PrivateKey.generate()
        key = _derive(ephemeral.exchange(self._public))
        nonce = os.urandom(12)
        return ephemeral.public_key().public_bytes(*RAW) + nonce + AESGCM(key).encrypt(nonce, data, None)

    def open(self, sealed: bytes) -> bytes:
        self.unlock()
        peer = X25519PublicKey.from_public_bytes(sealed[:32])
        return AESGCM(_derive(self._private.exchange(peer))).decrypt(sealed[32:44], sealed[44:], None)

    # -- records: a JSON header followed by 16-bit PCM ------------------------

    def _pack(self, meta: dict, audio: np.ndarray) -> bytes:
        head = json.dumps(meta, ensure_ascii=False).encode("utf-8")
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        return self.seal(struct.pack("<I", len(head)) + head + pcm)

    def _unpack(self, path: Path) -> tuple[dict, np.ndarray]:
        data = self.open(path.read_bytes())
        size = struct.unpack("<I", data[:4])[0]
        meta = json.loads(data[4:4 + size].decode("utf-8"))
        return meta, np.frombuffer(data[4 + size:], np.int16).astype(np.float32) / 32768

    def add_record(self, meta: dict, audio: np.ndarray) -> str:
        """``meta`` holds at least kind and text. Returns the new record's id."""
        rid = time.strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8]
        _write(RECORDS_DIR / f"{rid}.sealed", self._pack({**meta, "id": rid, "time": time.time()}, audio))
        return rid

    def record_ids(self) -> list[str]:
        return sorted(p.stem for p in RECORDS_DIR.glob("*.sealed"))

    def read_record(self, rid: str) -> tuple[dict, np.ndarray]:
        return self._unpack(RECORDS_DIR / f"{rid}.sealed")

    def update_record(self, rid: str, meta: dict) -> None:
        old, audio = self.read_record(rid)
        _write(RECORDS_DIR / f"{rid}.sealed", self._pack({**old, **meta}, audio))

    def delete_record(self, rid: str) -> None:
        (RECORDS_DIR / f"{rid}.sealed").unlink(missing_ok=True)

    def delete_older_than(self, days: int) -> int:
        limit, removed = time.time() - days * 86400, 0
        for path in RECORDS_DIR.glob("*.sealed"):
            if path.stat().st_mtime < limit:
                path.unlink()
                removed += 1
        return removed

    def delete_all_records(self) -> None:
        for path in RECORDS_DIR.glob("*.sealed"):
            path.unlink()

    # -- calibration readings -------------------------------------------------

    def save_reading(self, language: str, index: int, audio: np.ndarray) -> None:
        _write(reading_path(language, index), self._pack({"language": language, "index": index}, audio))

    def read_reading(self, language: str, index: int) -> np.ndarray:
        return self._unpack(reading_path(language, index))[1]

    def migrate_readings(self) -> None:
        """Seal the plain WAV files older versions left behind, then remove them."""
        for wav in RECORDINGS_DIR.glob("*/*.wav"):
            try:
                with wave.open(str(wav)) as w:
                    audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
                    if w.getframerate() != RATE:
                        continue
                self.save_reading(wav.parent.name, int(wav.stem), audio)
                wav.unlink()
            except (OSError, ValueError, wave.Error):
                log.exception("Could not seal %s", wav.name)
        (RECORDINGS_DIR / "manifest.jsonl").unlink(missing_ok=True)


def reading_path(language: str, index: int) -> Path:
    return RECORDINGS_DIR / language / f"{index:03d}.sealed"


def load_private(name: str, default):
    try:
        return json.loads(unprotect((VAULT_DIR / f"{name}.bin").read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return default


def save_private(name: str, data) -> None:
    _write(VAULT_DIR / f"{name}.bin", protect(json.dumps(data, ensure_ascii=False).encode("utf-8")))
