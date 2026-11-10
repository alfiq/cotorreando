"""Files that someone else could have written: a hand-edited settings file or an export
from an untrusted source must never wipe data, crash the app or slip in nonsense."""

import json
import os

import numpy as np
import pytest

from cotorreando import config, transfer
from cotorreando.config import Settings


def head_of(**extra) -> dict:
    return {"format": transfer.FORMAT, "version": transfer.VERSION, **extra}


@pytest.mark.parametrize("days", [0, -1, -99999])
def test_retention_below_one_day_never_deletes(unlocked_vault, days):
    rid = unlocked_vault.add_record({"kind": "correction", "text": "keep me"}, np.zeros(10, np.float32))
    assert unlocked_vault.delete_older_than(days) == 0
    assert unlocked_vault.record_ids() == [rid]


@pytest.mark.parametrize(
    "field, value",
    [
        ("retention_days", 0),
        ("retention_days", -1),
        ("retention_days", "180"),
        ("retention_days", True),
        ("retention_days", 10**9),
        ("mode", "rm -rf"),
        ("ui_language", "xx"),
        ("silence_ms", -5),
        ("vad_threshold", float("nan")),
        ("vad_threshold", 7.0),
        ("boost_alpha", float("inf")),
        ("keyword", 123),
        ("hotkey", None),
        ("blob_size", ["large"]),
        ("model_unload_min", -1),
        ("model_unload_min", 10**9),
        ("model_unload_min", "10"),
        ("model_unload_min", True),
    ],
)
def test_bad_values_in_settings_file_fall_back_to_defaults(isolated_data, field, value):
    config.CONFIG_FILE.write_text(json.dumps({field: value}), encoding="utf-8")
    assert getattr(Settings.load(), field) == getattr(Settings(), field)


def test_imported_settings_are_validated_and_skip_machine_fields():
    settings = Settings()
    transfer.apply_settings(
        settings,
        head_of(
            settings={
                "retention_days": -1,
                "mode": "evil",
                "use_gpu": False,
                "custom_model": "C:/evil",
                "lora_adapter": r"\\attacker\share",
                "keyword": "hola",
                "silence_ms": 900,
            }
        ),
    )
    assert settings.retention_days == Settings().retention_days
    assert settings.mode == Settings().mode
    assert settings.custom_model == "" and settings.lora_adapter == "" and settings.use_gpu
    assert settings.keyword == "hola" and settings.silence_ms == 900


@pytest.mark.parametrize("settings", [None, [], "x", 5])
def test_imported_settings_of_the_wrong_shape_are_ignored(settings):
    s = Settings()
    transfer.apply_settings(s, head_of(settings=settings))
    assert s == Settings()


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"text": "a"},
        {"kind": "correction"},
        {"kind": "reading", "text": "a"},
        {"kind": "../../x", "text": "a"},
        {"kind": "correction", "text": 5},
        {"kind": "correction", "text": "a", "old": ["x"]},
    ],
)
def test_imported_records_with_bad_meta_are_rejected(unlocked_vault, meta):
    head = head_of(records=[{"id": "R1", "meta": meta, "samples": 4}])
    with pytest.raises(transfer.NotAnExport):
        transfer.merge(unlocked_vault, head, b"\0" * 16)
    assert unlocked_vault.record_ids() == []


@pytest.mark.parametrize(
    "records, audio",
    [
        ([{"id": "R1", "meta": {"kind": "correction", "text": "a"}, "samples": 10**12}], b"\0" * 16),
        ([{"id": "R1", "meta": {"kind": "correction", "text": "a"}, "samples": -1}], b"\0" * 16),
        ([{"id": "R1", "meta": {"kind": "correction", "text": "a"}, "samples": 4.0}], b"\0" * 16),
        ([{"id": 1, "meta": {"kind": "correction", "text": "a"}, "samples": 4}], b"\0" * 16),
        ([{"meta": {"kind": "correction", "text": "a"}, "samples": 4}], b"\0" * 16),
        ("not a list", b""),
    ],
)
def test_imported_audio_lengths_cannot_overrun(unlocked_vault, records, audio):
    with pytest.raises(transfer.NotAnExport):
        transfer.merge(unlocked_vault, head_of(records=records), audio)


def test_imported_record_ids_cannot_choose_where_files_go(unlocked_vault):
    head = head_of(
        records=[
            {"id": r"..\..\..\evil", "meta": {"kind": "correction", "text": "a", "id": "../../evil"}, "samples": 4}
        ]
    )
    transfer.merge(unlocked_vault, head, b"\0" * 16)
    (rid,) = unlocked_vault.record_ids()
    assert ".." not in rid and "/" not in rid and "\\" not in rid
    assert unlocked_vault.read_record(rid)[0]["id"] == rid


@pytest.mark.parametrize("words", [["a", 1], "abc", {"a": 1}])
def test_imported_word_lists_of_the_wrong_type_are_rejected(unlocked_vault, words):
    with pytest.raises(transfer.NotAnExport):
        transfer.merge(unlocked_vault, head_of(custom_words=words), b"")


@pytest.mark.parametrize("blob", [b"", b"garbage", b"age-encryption.org/v1\n" + os.urandom(200)])
def test_garbage_export_file_is_a_wrong_password(tmp_path, blob):
    path = tmp_path / "x.cotorreando"
    path.write_bytes(blob)
    with pytest.raises(transfer.WrongPassword):
        transfer.read(path, "whatever123")
