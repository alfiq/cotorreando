"""The vault is where dictation audio and learned words live: these tests guard against loss and leaks."""

import logging
import os
import time
import wave

import numpy as np
import pyrage
import pytest

from cotorreando import vault as v
from cotorreando.audio import RATE
from cotorreando.vault import Locked, Vault, WrongPassword

AGE = b"age-encryption.org/"


def _write_wav(path, audio, rate=RATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())


# -- password ------------------------------------------------------------------


def test_create_makes_vault_ready_and_unlocked(vault):
    assert not vault.ready
    code = vault.create("a fine password")
    assert vault.ready and not vault.locked
    assert len(code.replace("-", "")) == 24 and code.count("-") == 5


def test_key_files_are_not_plaintext(unlocked_vault):
    for path in (v.IDENTITY_FILE, v.RECOVERY_FILE):
        data = path.read_bytes()
        assert data.startswith(AGE)
        assert b"AGE-SECRET-KEY" not in data
    assert v.RECIPIENT_FILE.read_text().startswith("age1")


def test_unlock_and_wrong_password(unlocked_vault):
    other = Vault()
    with pytest.raises(WrongPassword):
        other.unlock("not the password")
    assert other.locked
    other.unlock(unlocked_vault.password)
    assert not other.locked


def test_lock(unlocked_vault):
    unlocked_vault.lock()
    assert unlocked_vault.locked


def test_recover_normalises_code_and_sets_new_password(unlocked_vault):
    code = unlocked_vault.code
    messy = " " + code.lower().replace("-", " - ") + " "
    other = Vault()
    other.recover(messy, "brand new password")
    assert not other.locked
    Vault().unlock("brand new password")
    with pytest.raises(WrongPassword):
        Vault().unlock(unlocked_vault.password)
    # the recovery code keeps working after a recovery
    Vault().recover(code, "yet another one")


def test_recover_wrong_code(unlocked_vault):
    other = Vault()
    with pytest.raises(WrongPassword):
        other.recover("AAAA-AAAA-AAAA-AAAA-AAAA-AAAA", "whatever password")
    assert other.locked


def test_change_password_requires_unlock(unlocked_vault):
    with pytest.raises(Locked):
        Vault().change_password("whatever password")


def test_change_password(unlocked_vault):
    unlocked_vault.change_password("second password")
    Vault().unlock("second password")
    with pytest.raises(WrongPassword):
        Vault().unlock(unlocked_vault.password)
    Vault().recover(unlocked_vault.code, "third password")


def test_create_twice_orphans_old_records(vault, fake_audio):
    vault.create("first password")
    rid = vault.add_record({"kind": "x", "text": "hi"}, fake_audio)
    vault.create("second password")
    # Pinned behaviour: a new key replaces the old one, so earlier records can no longer be read.
    with pytest.raises(pyrage.DecryptError):
        vault.read_record(rid)
    assert vault.record_ids() == [rid]


# -- records -------------------------------------------------------------------


def test_record_roundtrip(unlocked_vault, fake_audio):
    rid = unlocked_vault.add_record({"kind": "correction", "text": "canción ñandú 日本"}, fake_audio)
    meta, audio = unlocked_vault.read_record(rid)
    assert meta["id"] == rid and meta["text"] == "canción ñandú 日本"
    assert abs(meta["time"] - time.time()) < 60
    assert len(audio) == len(fake_audio)
    assert np.abs(audio - fake_audio).max() <= 2 / 32768


def test_record_keeps_given_time(unlocked_vault, fake_audio):
    rid = unlocked_vault.add_record({"kind": "k", "text": "t", "time": 123.0}, fake_audio)
    assert unlocked_vault.read_record(rid)[0]["time"] == 123.0


def test_record_empty_and_clipped_audio(unlocked_vault):
    rid = unlocked_vault.add_record({"kind": "k", "text": ""}, np.zeros(0, np.float32))
    assert len(unlocked_vault.read_record(rid)[1]) == 0
    loud = np.array([5.0, -5.0, 0.0], np.float32)
    audio = unlocked_vault.read_record(unlocked_vault.add_record({"kind": "k", "text": ""}, loud))[1]
    assert audio[0] == pytest.approx(32767 / 32768) and audio[1] == pytest.approx(-32767 / 32768)


def test_record_bytes_do_not_contain_text(unlocked_vault, fake_audio):
    rid = unlocked_vault.add_record({"kind": "k", "text": "secretword"}, fake_audio)
    raw = (v.RECORDS_DIR / f"{rid}.sealed").read_bytes()
    assert raw.startswith(AGE) and b"secretword" not in raw


def test_seal_works_locked_open_raises(unlocked_vault):
    blob = unlocked_vault.seal(b"data")
    unlocked_vault.lock()
    assert unlocked_vault.seal(b"more")  # sealing needs only the public key
    with pytest.raises(Locked):
        unlocked_vault.open(blob)


def test_update_record_merges_meta(unlocked_vault, fake_audio):
    rid = unlocked_vault.add_record({"kind": "k", "text": "one"}, fake_audio)
    unlocked_vault.update_record(rid, {"text": "two", "extra": 1})
    meta, audio = unlocked_vault.read_record(rid)
    assert (meta["kind"], meta["text"], meta["extra"], meta["id"]) == ("k", "two", 1, rid)
    assert len(audio) == len(fake_audio)


def test_delete_record_is_idempotent(unlocked_vault, fake_audio):
    rid = unlocked_vault.add_record({"kind": "k", "text": "t"}, fake_audio)
    unlocked_vault.delete_record(rid)
    unlocked_vault.delete_record(rid)
    assert unlocked_vault.record_ids() == []


def test_record_ids_sorted_and_delete_all(unlocked_vault):
    v.RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("20240103T000000-b", "20240101T000000-a", "20240102T000000-c"):
        (v.RECORDS_DIR / f"{name}.sealed").write_bytes(b"x")
    assert unlocked_vault.record_ids() == ["20240101T000000-a", "20240102T000000-c", "20240103T000000-b"]
    unlocked_vault.delete_all_records()
    assert unlocked_vault.record_ids() == []


def test_delete_older_than(unlocked_vault, fake_audio):
    old = unlocked_vault.add_record({"kind": "k", "text": "old"}, fake_audio)
    new = unlocked_vault.add_record({"kind": "k", "text": "new"}, fake_audio)
    unlocked_vault.add_event({"op": "word", "word": "viejo"})
    unlocked_vault.add_event({"op": "word", "word": "nuevo"})
    past = time.time() - 40 * 86400
    os.utime(v.RECORDS_DIR / f"{old}.sealed", (past, past))
    os.utime(sorted(v.JOURNAL_DIR.glob("*.sealed"))[0], (past, past))
    assert unlocked_vault.delete_older_than(30) == 2
    assert unlocked_vault.record_ids() == [new]
    assert unlocked_vault.journal_size() == 1


def test_no_tmp_files_left(unlocked_vault, fake_audio):
    unlocked_vault.add_record({"kind": "k", "text": "t"}, fake_audio)
    unlocked_vault.save_private("x", [1])
    unlocked_vault.add_event({"op": "word", "word": "w"})
    unlocked_vault.change_password("another password")
    unlocked_vault.set_trained_ids(["a"])
    assert not list(v.VAULT_DIR.rglob("*.tmp"))


# -- private lists and journal ---------------------------------------------------


def test_private_roundtrip(unlocked_vault):
    unlocked_vault.save_private("words", {"ñu": [1, 2], "日本": "x"})
    assert unlocked_vault.load_private("words", None) == {"ñu": [1, 2], "日本": "x"}
    assert unlocked_vault.load_private("missing", ["d"]) == ["d"]
    raw = (v.VAULT_DIR / "words.sealed").read_bytes()
    assert raw.startswith(AGE) and "日本".encode() not in raw


def test_private_locked(unlocked_vault):
    unlocked_vault.save_private("words", [1])
    unlocked_vault.lock()
    with pytest.raises(Locked):
        unlocked_vault.load_private("words", [])
    assert unlocked_vault.load_private("missing", "d") == "d"


def test_journal_added_while_locked_is_sealed(unlocked_vault):
    unlocked_vault.lock()
    unlocked_vault.add_event({"op": "word", "word": "uno"})
    unlocked_vault.add_event({"op": "correction", "old": "a", "new": "b"})
    assert unlocked_vault.journal_size() == 2
    assert b"uno" not in next(v.JOURNAL_DIR.glob("*.sealed")).read_bytes()
    with pytest.raises(Locked):
        unlocked_vault.read_events()


def test_journal_read_after_unlock_and_clear(unlocked_vault):
    identity = unlocked_vault._identity
    unlocked_vault.lock()
    unlocked_vault.add_event({"op": "word", "word": "uno"})
    unlocked_vault._identity = identity
    assert unlocked_vault.read_events() == [{"op": "word", "word": "uno"}]
    unlocked_vault.clear_events()
    assert unlocked_vault.journal_size() == 0 and unlocked_vault.read_events() == []


def test_journal_empty_without_folder(vault):
    assert vault.journal_size() == 0
    vault.clear_events()


# -- trained ids and readings --------------------------------------------------------


def test_trained_ids(vault):
    assert vault.trained_ids() == []
    vault.set_trained_ids(["a", "b"])
    assert vault.trained_ids() == ["a", "b"]
    v.TRAINED_FILE.write_text("{not json")
    assert vault.trained_ids() == []


def test_readings_roundtrip(unlocked_vault, fake_audio):
    unlocked_vault.save_reading("es", 3, fake_audio)
    assert v.reading_path("es", 3).name == "003.sealed"
    audio = unlocked_vault.read_reading("es", 3)
    assert np.abs(audio - fake_audio).max() <= 2 / 32768


def test_migrate_readings(unlocked_vault, fake_audio, caplog):
    good = v.RECORDINGS_DIR / "es" / "001.wav"
    slow = v.RECORDINGS_DIR / "es" / "002.wav"
    bad = v.RECORDINGS_DIR / "es" / "003.wav"
    odd = v.RECORDINGS_DIR / "es" / "extra.wav"
    _write_wav(good, fake_audio)
    _write_wav(slow, fake_audio, rate=44100)
    bad.write_bytes(b"not a wav at all")
    _write_wav(odd, fake_audio)
    (v.RECORDINGS_DIR / "manifest.jsonl").write_text("{}")
    with caplog.at_level(logging.ERROR):
        unlocked_vault.migrate_readings()
    assert not good.exists() and v.reading_path("es", 1).exists()
    assert len(unlocked_vault.read_reading("es", 1)) == len(fake_audio)
    assert slow.exists() and not v.reading_path("es", 2).exists()  # 44.1 kHz is left alone
    assert bad.exists() and "003.wav" in caplog.text  # logged, not fatal
    assert odd.exists()  # non-numeric stem survives
    assert not (v.RECORDINGS_DIR / "manifest.jsonl").exists()


# -- password policy -------------------------------------------------------------------


@pytest.mark.parametrize(
    "password,expected",
    [
        ("", "password_short"),
        ("1234567", "password_short"),
        ("abc", "password_short"),
        ("password", "password_weak"),
        ("PASSWORD", "password_weak"),
        ("cotorreando", "password_weak"),
        ("aaaaaaaa", "password_weak"),
        ("abababab", "password_weak"),
        ("01234567", "password_weak"),
        ("98765432", "password_weak"),
        ("correct horse", None),
        ("13572468", None),
    ],
)
def test_password_problem(password, expected):
    assert v.password_problem(password) == expected
