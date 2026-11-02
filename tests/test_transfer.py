"""Export and import of settings and learned words, through a real (unlocked) vault."""

import json
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pyrage
import pytest
from pyrage import passphrase

from cotorreando import transfer
from cotorreando.config import Settings
from cotorreando.vault import Locked, WrongPassword

PW = "export password"
AGE = b"age-encryption.org/"


def head_of(**extra) -> dict:
    return {"format": transfer.FORMAT, "version": transfer.VERSION, **extra}


def seed(vault, custom=(), corrections=None, hard=None):
    vault.save_private("custom_words", list(custom))
    vault.save_private("corrections", corrections or {})
    vault.save_private("hard_words", hard or {})


def add_dictations(vault, count=3):
    sizes = [100 + 10 * i for i in range(count)]
    for i, size in enumerate(sizes):
        audio = np.full(size, 0.1 * (i + 1), np.float32)
        vault.add_record({"kind": "correction", "text": f"text {i}", "time": float(i)}, audio)
    return sizes


@pytest.fixture
def fast_decrypt(monkeypatch):
    """Decrypting returns the stored bytes as they are, to test what read() does with the payload."""
    monkeypatch.setattr(transfer, "passphrase", SimpleNamespace(decrypt=lambda data, password: data))


# -- export / read ---------------------------------------------------------------------

def test_export_import_roundtrip_without_dictations(unlocked_vault, tmp_path):
    seed(unlocked_vault, ["Cotorro"], {"a|b": 2}, {"hola": {"word": "hola", "count": 1, "read": 0}})
    settings = Settings(mode="ptt", keyword="hey loro", boost_alpha=2.5)
    file = tmp_path / "out.cotorreando"
    transfer.export(unlocked_vault, settings, file, PW, include_dictations=False)
    assert file.read_bytes().startswith(AGE)
    assert not list(tmp_path.glob("*.tmp"))
    head, audio = transfer.read(file, PW)
    assert audio == b"" and head["records"] == []
    assert head["custom_words"] == ["Cotorro"] and head["corrections"] == {"a|b": 2}
    assert head["hard_words"]["hola"]["count"] == 1
    other = Settings()
    transfer.apply_settings(other, head)
    assert (other.mode, other.keyword, other.boost_alpha) == ("ptt", "hey loro", 2.5)


def test_export_import_with_dictations(unlocked_vault, tmp_path):
    add_dictations(unlocked_vault)
    # ids within one second sort randomly, so go by the order the vault reports
    originals = [unlocked_vault.read_record(rid) for rid in unlocked_vault.record_ids()]
    sizes = [len(audio) for _, audio in originals]
    file = tmp_path / "out.cotorreando"
    transfer.export(unlocked_vault, Settings(), file, PW, include_dictations=True)
    head, audio = transfer.read(file, PW)
    assert [r["samples"] for r in head["records"]] == sizes
    assert len(audio) == sum(sizes) * 4
    offset = 0
    for record, (_, expected) in zip(head["records"], originals):
        chunk = np.frombuffer(audio, "<f4", record["samples"], offset * 4)
        np.testing.assert_array_equal(chunk, expected)
        offset += record["samples"]
    # into an install that has none of them: audio lands on the right record
    unlocked_vault.delete_all_records()
    assert transfer.merge(unlocked_vault, head, audio)[2] == 3
    by_text = {meta["text"]: audio for meta, audio in map(unlocked_vault.read_record, unlocked_vault.record_ids())}
    for meta, expected in originals:
        np.testing.assert_allclose(by_text[meta["text"]], expected, atol=2 / 32768)


def test_machine_fields_are_not_exported_and_file_is_not_plaintext(unlocked_vault, tmp_path):
    settings = Settings(microphone="Secret Mic", blob_x=10, hidden=True, lora_adapter="mine")
    seed(unlocked_vault, ["palabrasecreta"])
    file = tmp_path / "out.cotorreando"
    transfer.export(unlocked_vault, settings, file, PW, include_dictations=False)
    assert b"Secret Mic" not in file.read_bytes() and b"palabrasecreta" not in file.read_bytes()
    head, _ = transfer.read(file, PW)
    assert not set(head["settings"]) & transfer.MACHINE_FIELDS
    assert set(head["settings"]) == set(asdict(settings)) - transfer.MACHINE_FIELDS


def test_read_wrong_password_and_garbage(tmp_path):
    file = tmp_path / "x"
    file.write_bytes(passphrase.encrypt(b"{}\n", PW))
    with pytest.raises(WrongPassword):
        transfer.read(file, "not it")
    for junk in (b"", b"not an age file", b"age-encryption.org/v1\n garbage"):
        file.write_bytes(junk)
        with pytest.raises(WrongPassword):
            transfer.read(file, PW)


@pytest.mark.parametrize("payload", [
    b"not json at all\n",
    b"",
    json.dumps({"format": "other", "version": 1}).encode() + b"\n",
    json.dumps({"version": 1}).encode() + b"\n",
    json.dumps([1, 2]).encode() + b"\n",
    json.dumps(head_of(version=2)).encode() + b"\n",
])
def test_read_not_an_export(tmp_path, fast_decrypt, payload):
    file = tmp_path / "x"
    file.write_bytes(payload)
    with pytest.raises(transfer.NotAnExport):
        transfer.read(file, PW)


def test_read_missing_version_is_accepted(tmp_path, fast_decrypt):
    file = tmp_path / "x"
    file.write_bytes(json.dumps({"format": transfer.FORMAT}).encode() + b"\n")
    head, audio = transfer.read(file, PW)
    assert head == {"format": transfer.FORMAT} and audio == b""


def test_read_non_int_version_is_not_an_export(tmp_path, fast_decrypt):
    file = tmp_path / "x"
    file.write_bytes(json.dumps(head_of(version="2")).encode() + b"\n")
    with pytest.raises(transfer.NotAnExport):
        transfer.read(file, PW)


# -- merge ---------------------------------------------------------------------------------

def test_merge_adds_to_existing(unlocked_vault):
    seed(unlocked_vault, ["uno"], {"k": 1},
         {"hola": {"word": "hola", "count": 2, "read": 1}})
    head = head_of(custom_words=["uno", "dos", "dos"], corrections={"k": 2, "j": 1},
                   hard_words={"hola": {"word": "hola", "count": 3, "read": 2},
                               "nuevo": {"word": "nuevo", "count": 1}})
    assert transfer.merge(unlocked_vault, head, b"") == (1, 2, 0)
    assert unlocked_vault.load_private("custom_words", None) == ["uno", "dos"]
    assert unlocked_vault.load_private("corrections", None) == {"k": 3, "j": 1}
    hard = unlocked_vault.load_private("hard_words", None)
    assert hard["hola"] == {"word": "hola", "count": 5, "read": 3}
    assert hard["nuevo"] == {"word": "nuevo", "count": 1, "read": 0}


def test_merge_replace_replaces_lists_but_only_adds_dictations(unlocked_vault):
    seed(unlocked_vault, ["viejo"], {"x|y": 9}, {"w": {"word": "w", "count": 9, "read": 0}})
    unlocked_vault.add_record({"kind": "k", "text": "mine"}, np.zeros(10, np.float32))
    audio = np.ones(5, "<f4").tobytes()
    head = head_of(custom_words=["nuevo"], corrections={"a|b": 1}, hard_words={},
                   records=[{"id": "R1", "meta": {"kind": "k", "text": "theirs"}, "samples": 5}])
    assert transfer.merge(unlocked_vault, head, audio, replace=True) == (1, 1, 1)
    assert unlocked_vault.load_private("custom_words", None) == ["nuevo"]
    assert unlocked_vault.load_private("corrections", None) == {"a|b": 1}
    assert unlocked_vault.load_private("hard_words", None) == {}
    assert len(unlocked_vault.record_ids()) == 2


def test_merge_dedups_and_reimport_adds_nothing(unlocked_vault):
    audio = np.ones(8, "<f4").tobytes()
    head = head_of(records=[{"id": "R1", "meta": {"kind": "k", "text": "a"}, "samples": 4},
                            {"id": "R1", "meta": {"kind": "k", "text": "a"}, "samples": 4}])
    assert transfer.merge(unlocked_vault, head, audio)[2] == 1
    assert transfer.merge(unlocked_vault, head, audio)[2] == 0
    assert len(unlocked_vault.record_ids()) == 1


def test_import_back_to_origin_adds_nothing(unlocked_vault, tmp_path):
    add_dictations(unlocked_vault, 2)
    file = tmp_path / "out.cotorreando"
    transfer.export(unlocked_vault, Settings(), file, PW, include_dictations=True)
    head, audio = transfer.read(file, PW)
    assert transfer.merge(unlocked_vault, head, audio)[2] == 0
    assert len(unlocked_vault.record_ids()) == 2


def test_chain_keeps_the_original_id(unlocked_vault):
    audio = np.ones(4, "<f4").tobytes()
    first = head_of(records=[{"id": "A1", "meta": {"kind": "k", "text": "a"}, "samples": 4}])
    transfer.merge(unlocked_vault, first, audio)            # A -> B
    (rid,) = unlocked_vault.record_ids()
    meta, samples = unlocked_vault.read_record(rid)
    assert meta["imported_from"] == "A1"
    second = head_of(records=[{"id": rid, "meta": meta, "samples": len(samples)}])
    payload = samples.astype("<f4").tobytes()
    assert transfer.merge(unlocked_vault, second, payload)[2] == 0      # back where it came from
    unlocked_vault.delete_all_records()                                 # B -> C, which has nothing
    assert transfer.merge(unlocked_vault, second, payload)[2] == 1
    (rid2,) = unlocked_vault.record_ids()
    assert unlocked_vault.read_record(rid2)[0]["imported_from"] == "A1"
    assert transfer.merge(unlocked_vault, first, audio)[2] == 0         # the original is recognised


def test_merge_minimal_head(unlocked_vault):
    assert transfer.merge(unlocked_vault, {"format": transfer.FORMAT}, b"") == (0, 0, 0)


def test_merge_requires_unlock(unlocked_vault):
    seed(unlocked_vault, ["uno"])
    unlocked_vault.lock()
    with pytest.raises(Locked):
        transfer.merge(unlocked_vault, head_of(custom_words=["dos"]), b"")


def test_merge_is_all_or_nothing_on_bad_hard_word(unlocked_vault):
    seed(unlocked_vault)
    head = head_of(custom_words=["nuevo"], corrections={"a|b": 1}, hard_words={"x": {"count": 1}})
    with pytest.raises(Exception):
        transfer.merge(unlocked_vault, head, b"")
    assert unlocked_vault.load_private("custom_words", None) == []
    assert unlocked_vault.load_private("corrections", None) == {}


def test_merge_is_all_or_nothing_on_truncated_audio(unlocked_vault):
    seed(unlocked_vault)
    audio = np.ones(4, "<f4").tobytes()                      # the second record's audio is missing
    head = head_of(custom_words=["nuevo"],
                   records=[{"id": "R1", "meta": {"kind": "k", "text": "a"}, "samples": 4},
                            {"id": "R2", "meta": {"kind": "k", "text": "b"}, "samples": 4}])
    with pytest.raises(Exception):
        transfer.merge(unlocked_vault, head, audio)
    assert unlocked_vault.record_ids() == []
    assert unlocked_vault.load_private("custom_words", None) == []


# -- apply_settings --------------------------------------------------------------------------

def test_apply_settings_skips_machine_and_unknown():
    s = Settings()
    transfer.apply_settings(s, head_of(settings={"mode": "ptt", "microphone": "other", "use_gpu": False,
                                                 "blob_x": 5, "bogus": 1}))
    assert s.mode == "ptt" and s.microphone == "" and s.use_gpu is True and s.blob_x == -1
    assert not hasattr(s, "bogus")


def test_apply_settings_type_checks():
    s = Settings()
    transfer.apply_settings(s, head_of(settings={
        "streaming": 0,           # an int is not a bool
        "silence_ms": True,       # nor is a bool an int
        "retention_days": 30.5,   # a float is not an int
        "vad_threshold": 1,       # an int is accepted for a float and coerced
        "keyword": 5,
        "trailing_space": False,
    }))
    assert s.streaming is True and s.silence_ms == 700 and s.retention_days == 180
    assert s.vad_threshold == 1.0 and isinstance(s.vad_threshold, float)
    assert s.keyword == "oye cotorro" and s.trailing_space is False


def test_apply_settings_without_settings_key_is_a_noop():
    s = Settings()
    transfer.apply_settings(s, {"format": transfer.FORMAT})
    assert s == Settings()


def test_import_does_not_accept_the_privacy_notice():
    s = Settings()
    transfer.apply_settings(s, head_of(settings={"welcome_accepted": True}))
    assert s.welcome_accepted is False
