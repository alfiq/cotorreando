"""User settings, persisted as JSON next to the downloaded models."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields

from .paths import CONFIG_FILE

log = logging.getLogger(__name__)


@dataclass
class Settings:
    # General
    welcome_accepted: bool = False   # saw and accepted the first-run privacy notice
    ui_language: str = "es"            # "es" | "en"
    mode: str = "activation"           # "open" | "ptt" | "activation"
    activation: str = "voice"          # "voice" | "keyword"
    keyword: str = "oye cotorro"
    hotkey: str = "ctrl+win"
    use_gpu: bool = True
    autostart: bool = False

    # Audio
    microphone: str = ""               # empty = system default
    noise_suppression: bool = True
    echo_cancellation: bool = True
    auto_gain: bool = True
    auto_threshold: bool = True
    energy_threshold_db: float = -50.0  # used when auto_threshold is off
    vad_threshold: float = 0.5
    silence_ms: int = 700
    session_timeout_s: float = 6.0     # activation mode: stay awake this long

    # Typing
    typing_holdoff_ms: int = 1200      # pause dictation after you touch the keyboard
    trailing_space: bool = True
    streaming: bool = True             # type words while you are still speaking

    # Model
    custom_model: str = ""             # folder of the user's own model; empty = the downloaded one
    lora_adapter: str = ""             # empty = stock model
    lora_language: str = "es"          # "es" | "en" | "both"
    calibrated: bool = False           # finished or skipped the first calibration

    # Learning
    learning: bool = True              # learn from corrections and hesitations
    excluded_apps: str = ""            # comma-separated executable names
    retention_days: int = 180
    password_offered: bool = False
    boost_mode: str = "auto"           # "auto" | "on" | "off": leaning towards your words
    vocabulary_on: bool = False        # only ever enabled by a measured improvement
    boost_alpha: float = 1.0           # strength of the boost, the one that measured best
    training_notice_shown: bool = False
    check_updates: bool = True         # ask GitHub once a day whether a newer version exists
    update_last_check: float = 0.0     # time.time() of the last attempt
    update_skipped: str = ""           # version the user chose to skip

    # Blob
    blob_size: str = "medium"          # "small" | "medium" | "large"
    blob_x: int = -1
    blob_y: int = -1
    hidden: bool = False

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            temp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
            temp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            os.replace(temp, CONFIG_FILE)
        except OSError as err:
            log.error("Could not save settings: %s", err)
