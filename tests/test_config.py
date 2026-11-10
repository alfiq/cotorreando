"""Settings persistence: a bad file must never keep the app from starting."""

import json
import logging
from dataclasses import asdict, fields

import pytest

from cotorreando import config
from cotorreando.config import Settings


def test_defaults_are_pinned():
    s = Settings()
    assert s.welcome_accepted is False
    assert s.learning is True
    assert s.ui_language == "es"
    assert (s.mode, s.activation, s.keyword, s.hotkey) == ("activation", "voice", "oye cotorro", "ctrl+win")
    assert (s.use_gpu, s.autostart, s.calibrated) == (True, False, False)
    assert s.model_unload_min == 10
    assert (s.retention_days, s.silence_ms, s.boost_mode) == (180, 700, "auto")
    assert s.vocabulary_on is False and s.hidden is False and s.blob_size == "medium"
    assert (s.blob_x, s.blob_y) == (-1, -1) and s.microphone == "" and s.lora_adapter == ""


def test_missing_file_gives_defaults(isolated_data):
    assert Settings.load() == Settings()


@pytest.mark.parametrize("content", ["", "{not json", "\x00\x01"])
def test_corrupt_file_gives_defaults(isolated_data, content):
    config.CONFIG_FILE.write_text(content, encoding="utf-8")
    assert Settings.load() == Settings()


def test_invalid_utf8_gives_defaults(isolated_data):
    config.CONFIG_FILE.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    assert Settings.load() == Settings()


def test_file_from_0_0_7_has_no_welcome_accepted(isolated_data):
    old = {k: v for k, v in asdict(Settings()).items() if k != "welcome_accepted"}
    old.update(ui_language="en", mode="ptt", retention_days=30, learning=False)
    config.CONFIG_FILE.write_text(json.dumps(old), encoding="utf-8")
    s = Settings.load()
    assert s.welcome_accepted is False
    assert (s.ui_language, s.mode, s.retention_days, s.learning) == ("en", "ptt", 30, False)


def test_unknown_keys_are_ignored(isolated_data):
    config.CONFIG_FILE.write_text(json.dumps({"mode": "open", "from_the_future": 1}), encoding="utf-8")
    s = Settings.load()
    assert s.mode == "open" and not hasattr(s, "from_the_future")


def test_save_load_roundtrip_with_unicode(isolated_data):
    s = Settings(
        keyword="oye cotorro ñandú 日本",
        microphone="Micrófono (USB)",
        welcome_accepted=True,
        silence_ms=900,
        vad_threshold=0.25,
        model_unload_min=0,
    )
    s.save()
    assert Settings.load() == s
    json.loads(config.CONFIG_FILE.read_bytes().decode("utf-8"))  # valid UTF-8 JSON on disk


def test_save_creates_parent_folder(isolated_data, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", isolated_data / "deep" / "er" / "settings.json")
    Settings().save()
    assert config.CONFIG_FILE.exists()


def test_save_swallows_oserror_and_logs(isolated_data, monkeypatch, caplog):
    # A folder where the file should be makes the write fail.
    config.CONFIG_FILE.mkdir()
    with caplog.at_level(logging.ERROR):
        Settings().save()
    assert "Could not save settings" in caplog.text


def test_every_field_is_json_serialisable():
    data = json.loads(json.dumps(asdict(Settings())))
    assert set(data) == {f.name for f in fields(Settings)}


@pytest.mark.parametrize("content", ["[]", "null", "5"])
def test_non_object_json_gives_defaults(isolated_data, content):
    config.CONFIG_FILE.write_text(content, encoding="utf-8")
    assert Settings.load() == Settings()
