"""User settings, persisted as JSON next to the downloaded models."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields

from .paths import CONFIG_FILE

log = logging.getLogger(__name__)


@dataclass
class Settings:
    # General
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
    max_segment_s: float = 25.0

    # Typing
    typing_holdoff_ms: int = 1200      # pause dictation after you touch the keyboard
    trailing_space: bool = True

    # Model
    lora_adapter: str = ""             # empty = stock model
    lora_dataset: str = "es_60"

    # Blob
    blob_x: int = -1
    blob_y: int = -1
    hidden: bool = False

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError as err:
            log.error("Could not save settings: %s", err)
