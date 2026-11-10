"""Encrypted storage for everything learning keeps about the user's voice and words.

Everything uses age (https://age-encryption.org) through pyrage. Records are sealed
to a public key, so dictation can store them without being able to read them back.
The private key only exists on disk encrypted with the user's password, and again
with a recovery code shown once. Nothing here depends on the operating system, and
reading anything back always takes the password.

While the vault is locked, what learning notices goes to a journal of sealed events
that is merged into the word lists the next time it is unlocked.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import struct
import time
import uuid
import wave
from pathlib import Path

import numpy as np
import pyrage
from pyrage import passphrase, x25519

from .audio import RATE
from .paths import DATA_DIR, RECORDINGS_DIR

log = logging.getLogger(__name__)

VAULT_DIR = DATA_DIR / "vault"
RECIPIENT_FILE = VAULT_DIR / "recipient.txt"
IDENTITY_FILE = VAULT_DIR / "identity.age"
RECOVERY_FILE = VAULT_DIR / "recovery.age"
RECORDS_DIR = VAULT_DIR / "records"
JOURNAL_DIR = VAULT_DIR / "journal"
TRAINED_FILE = VAULT_DIR / "trained.json"
MIN_PASSWORD = 8
COMMON_PASSWORDS = {"password", "contraseña", "contrasena", "qwertyui", "qwerty123", "cotorreando",
                    "iloveyou", "administrador", "admin123", "password1"}
RECOVERY_GROUP = 4


class WrongPassword(Exception):
    pass


class Locked(Exception):
    pass


def password_problem(password: str) -> str | None:
    """Why this password cannot be used, as an i18n key; None if it can."""
    if len(password) < MIN_PASSWORD:
        return "password_short"
    lowered = password.lower()
    ascending = "01234567890123456789"
    if (lowered in COMMON_PASSWORDS or len(set(lowered)) < 4
            or lowered in ascending or lowered in ascending[::-1]):
        return "password_weak"
    return None


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(path)


def _normal_code(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


class Vault:
    def __init__(self):
        self._identity: x25519.Identity | None = None

    # -- password -------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return RECIPIENT_FILE.exists() and IDENTITY_FILE.exists()

    @property
    def locked(self) -> bool:
        return self._identity is None

    def create(self, password: str) -> str:
        """Start a new key, replacing any before it. Returns the recovery code, shown only once."""
        identity = x25519.Identity.generate()
        secret = str(identity).encode("ascii")
        raw = base64.b32encode(secrets.token_bytes(15)).decode("ascii")
        code = "-".join(raw[i:i + RECOVERY_GROUP] for i in range(0, len(raw), RECOVERY_GROUP))
        _write(IDENTITY_FILE, passphrase.encrypt(secret, password))
        _write(RECOVERY_FILE, passphrase.encrypt(secret, _normal_code(code)))
        _write(RECIPIENT_FILE, str(identity.to_public()).encode("ascii"))
        self._identity = identity
        return code

    def _open_key(self, path: Path, password: str) -> x25519.Identity:
        try:
            return x25519.Identity.from_str(passphrase.decrypt(path.read_bytes(), password).decode("ascii"))
        except pyrage.DecryptError as err:
            raise WrongPassword from err

    def unlock(self, password: str) -> None:
        """Raises WrongPassword."""
        self._identity = self._open_key(IDENTITY_FILE, password)

    def recover(self, code: str, new_password: str) -> None:
        """Set a new password with the recovery code. Raises WrongPassword."""
        self._identity = self._open_key(RECOVERY_FILE, _normal_code(code))
        self.change_password(new_password)

    def change_password(self, password: str) -> None:
        """The vault must be unlocked."""
        if self._identity is None:
            raise Locked
        _write(IDENTITY_FILE, passphrase.encrypt(str(self._identity).encode("ascii"), password))

    def lock(self) -> None:
        self._identity = None

    # -- sealing --------------------------------------------------------------

    def seal(self, data: bytes) -> bytes:
        recipient = x25519.Recipient.from_str(RECIPIENT_FILE.read_text(encoding="ascii"))
        return pyrage.encrypt(data, [recipient])

    def open(self, sealed: bytes) -> bytes:
        if self._identity is None:
            raise Locked
        return pyrage.decrypt(sealed, [self._identity])

    # -- word lists and journal -----------------------------------------------

    def load_private(self, name: str, default):
        try:
            return json.loads(self.open((VAULT_DIR / f"{name}.sealed").read_bytes()).decode("utf-8"))
        except FileNotFoundError:
            return default

    def save_private(self, name: str, data) -> None:
        _write(VAULT_DIR / f"{name}.sealed", self.seal(json.dumps(data, ensure_ascii=False).encode("utf-8")))

    def add_event(self, event: dict) -> None:
        name = time.strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8]
        _write(JOURNAL_DIR / f"{name}.sealed", self.seal(json.dumps(event, ensure_ascii=False).encode("utf-8")))

    def journal_size(self) -> int:
        return sum(1 for _ in JOURNAL_DIR.glob("*.sealed"))

    def read_events(self) -> list[dict]:
        return [json.loads(self.open(path.read_bytes()).decode("utf-8"))
                for path in sorted(JOURNAL_DIR.glob("*.sealed"))]

    def clear_events(self) -> None:
        for path in JOURNAL_DIR.glob("*.sealed"):
            path.unlink()

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
        """``meta`` holds at least kind and text, and keeps its time if it brings one.
        Returns the new record's id."""
        rid = time.strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8]
        _write(RECORDS_DIR / f"{rid}.sealed", self._pack({"time": time.time(), **meta, "id": rid}, audio))
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
        if days < 1:            # a bad setting must never wipe everything
            return 0
        limit, removed = time.time() - days * 86400, 0
        for folder in (RECORDS_DIR, JOURNAL_DIR):
            for path in folder.glob("*.sealed"):
                if path.stat().st_mtime < limit:
                    path.unlink()
                    removed += 1
        return removed

    def delete_all_records(self) -> None:
        for path in RECORDS_DIR.glob("*.sealed"):
            path.unlink()

    # -- which records have been trained on: only ids, which are just dates ----

    def trained_ids(self) -> list[str]:
        try:
            return json.loads(TRAINED_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def set_trained_ids(self, ids: list[str]) -> None:
        _write(TRAINED_FILE, json.dumps(ids).encode("utf-8"))

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
