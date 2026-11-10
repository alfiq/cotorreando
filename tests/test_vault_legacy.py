"""Moving data from the DPAPI-era format to age: nothing may be lost on the way."""

import json
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from cotorreando import vault as v
from cotorreando import vault_legacy as legacy
from cotorreando.vault import WrongPassword

RAW = serialization.Encoding.Raw, serialization.PublicFormat.Raw
OLD_PASSWORD = "old password"


@pytest.fixture(autouse=True)
def no_dpapi(monkeypatch):
    monkeypatch.setattr(legacy, "_unprotect", lambda data: data)


@pytest.fixture
def old_key():
    return X25519PrivateKey.generate()


def _private(key) -> bytes:
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def write_key_file(key, password=None):
    raw = _private(key)
    file = {}
    if password is not None:
        salt = os.urandom(16)
        derived = Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536).derive(
            password.encode("utf-8")
        )
        nonce = os.urandom(12)
        raw = nonce + AESGCM(derived).encrypt(nonce, raw, None)
        file["salt"] = salt.hex()
    file["wrapped"] = raw.hex()
    legacy.KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    legacy.KEY_FILE.write_text(json.dumps(file), encoding="utf-8")


def old_seal(key, data: bytes) -> bytes:
    eph = X25519PrivateKey.generate()
    shared = eph.exchange(key.public_key())
    derived = HKDF(hashes.SHA256(), 32, None, b"cotorreando-record").derive(shared)
    nonce = os.urandom(12)
    return eph.public_key().public_bytes(*RAW) + nonce + AESGCM(derived).encrypt(nonce, data, None)


def put_record(key, name="20240101T000000-aaaaaaaa", data=b"payload", folder=None) -> "os.PathLike":
    folder = folder or v.RECORDS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.sealed"
    path.write_bytes(old_seal(key, data))
    return path


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# -- detection --------------------------------------------------------------------


def test_pending_and_password_flavours(isolated_data, old_key):
    assert not legacy.pending()
    write_key_file(old_key)
    assert legacy.pending() and not legacy.needs_old_password()
    write_key_file(old_key, OLD_PASSWORD)
    assert legacy.needs_old_password()


def test_check_old_password(isolated_data, old_key):
    write_key_file(old_key, OLD_PASSWORD)
    legacy.check_old_password(OLD_PASSWORD)
    for bad in ("nope", "", None):
        with pytest.raises(WrongPassword):
            legacy.check_old_password(bad)


def test_check_old_password_without_password(isolated_data, old_key):
    write_key_file(old_key)
    legacy.check_old_password(None)


# -- migrate ------------------------------------------------------------------------


def test_migrate_reseals_records_lists_and_training(unlocked_vault, old_key):
    first = put_record(old_key, "20240101T000000-aaaaaaaa", b"one")
    nested = put_record(old_key, "001", b"two", v.RECORDINGS_DIR / "es")
    for name, data in (
        ("hard_words", {"x": {"word": "x", "count": 1, "read": 0}}),
        ("corrections", {"a|b": 2}),
        ("training", {"trained": ["r1", "r2"], "checkpoint": "zzz"}),
    ):
        (v.VAULT_DIR / f"{name}.bin").write_text(json.dumps(data), encoding="utf-8")
    (v.VAULT_DIR / "checkpoint.sealed").write_bytes(b"old")
    write_key_file(old_key)

    legacy.migrate(unlocked_vault)

    assert unlocked_vault.open(first.read_bytes()) == b"one"
    assert unlocked_vault.open(nested.read_bytes()) == b"two"
    assert unlocked_vault.load_private("hard_words", None) == {"x": {"word": "x", "count": 1, "read": 0}}
    assert unlocked_vault.load_private("corrections", None) == {"a|b": 2}
    assert unlocked_vault.trained_ids() == ["r1", "r2"]
    assert not legacy.KEY_FILE.exists() and not legacy.UNREADABLE_DIR.exists()
    assert not list(v.VAULT_DIR.glob("*.bin")) and not (v.VAULT_DIR / "checkpoint.sealed").exists()
    assert not list(v.VAULT_DIR.rglob("*.tmp"))


def test_migrate_with_password(unlocked_vault, old_key):
    path = put_record(old_key, data=b"secret")
    write_key_file(old_key, OLD_PASSWORD)
    legacy.migrate(unlocked_vault, OLD_PASSWORD)
    assert unlocked_vault.open(path.read_bytes()) == b"secret"
    assert not legacy.KEY_FILE.exists()


def test_migrate_skips_already_age_and_second_run_is_harmless(unlocked_vault, old_key):
    new = v.RECORDS_DIR / "20240102T000000-bbbbbbbb.sealed"
    v.RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    new.write_bytes(unlocked_vault.seal(b"already new"))
    before = new.read_bytes()
    old = put_record(old_key, data=b"old")
    write_key_file(old_key)
    legacy.migrate(unlocked_vault)
    assert new.read_bytes() == before
    assert unlocked_vault.open(old.read_bytes()) == b"old"
    write_key_file(old_key)  # a stale key file left behind by an interrupted run
    resealed = old.read_bytes()
    legacy.migrate(unlocked_vault)
    assert old.read_bytes() == resealed and new.read_bytes() == before
    assert not legacy.KEY_FILE.exists()


def test_corrupt_record_is_set_aside_with_the_key(unlocked_vault, old_key):
    good = put_record(old_key, "20240101T000000-aaaaaaaa", b"good")
    bad = put_record(old_key, "20240102T000000-bbbbbbbb", b"bad")
    raw = bytearray(bad.read_bytes())
    raw[-1] ^= 1
    bad.write_bytes(bytes(raw))
    write_key_file(old_key)
    legacy.migrate(unlocked_vault)
    assert unlocked_vault.open(good.read_bytes()) == b"good"
    assert not bad.exists()
    assert (legacy.UNREADABLE_DIR / "records-20240102T000000-bbbbbbbb.sealed").read_bytes() == bytes(raw)
    assert (legacy.UNREADABLE_DIR / "key.json").exists() and not legacy.KEY_FILE.exists()


def test_corrupt_list_goes_to_unreadable(unlocked_vault, old_key):
    (v.VAULT_DIR / "corrections.bin").write_bytes(b"\xff not json")
    (v.VAULT_DIR / "hard_words.bin").write_text(json.dumps({"w": 1}), encoding="utf-8")
    write_key_file(old_key)
    legacy.migrate(unlocked_vault)
    assert (legacy.UNREADABLE_DIR / "vault-corrections.bin").exists()
    assert unlocked_vault.load_private("hard_words", None) == {"w": 1}
    assert (legacy.UNREADABLE_DIR / "key.json").exists()


def test_wrong_password_touches_nothing(unlocked_vault, old_key):
    put_record(old_key)
    (v.VAULT_DIR / "corrections.bin").write_text("{}", encoding="utf-8")
    write_key_file(old_key, OLD_PASSWORD)
    before = snapshot(v.VAULT_DIR.parent)
    for bad in ("wrong", None):
        with pytest.raises(WrongPassword):
            legacy.migrate(unlocked_vault, bad)
    assert snapshot(v.VAULT_DIR.parent) == before


@pytest.mark.parametrize("size", [0, 10, 40])
def test_short_blobs_are_unreadable_not_fatal(unlocked_vault, old_key, size):
    good = put_record(old_key, "20240101T000000-aaaaaaaa", b"good")
    short = v.RECORDS_DIR / "20240102T000000-short000.sealed"
    short.write_bytes(os.urandom(size))
    write_key_file(old_key)
    legacy.migrate(unlocked_vault)
    assert unlocked_vault.open(good.read_bytes()) == b"good"
    assert not short.exists() and (legacy.UNREADABLE_DIR / f"records-{short.name}").exists()
