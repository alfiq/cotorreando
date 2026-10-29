"""Recording and training dialog: read each phrase aloud, then train."""

from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from ..audio import RATE, AudioInput
from ..i18n import tr
from ..paths import DATA_DIR, MODELS_DIR, PACKAGE_DIR, RECORDINGS_DIR
from . import env

DATASET_DIRS = (PACKAGE_DIR / "lora" / "datasets", DATA_DIR / "datasets")
MIN_RECORDINGS = 10


def datasets() -> dict[str, Path]:
    """Built-in phrase sets plus any .txt the user drops in the data folder."""
    found = {}
    for folder in DATASET_DIRS:
        for f in sorted(folder.glob("*.txt")) if folder.exists() else ():
            found[f.stem] = f
    return found


def read_phrases(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def save_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


class TrainingDialog(QDialog):
    log_line = Signal(str)
    finished_training = Signal(bool, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle(tr("train_title"))
        self.resize(620, 420)
        self.sets = datasets()
        self.index = 0
        self.frames: list[np.ndarray] = []
        self.audio: AudioInput | None = None

        self.dataset = QComboBox()
        self.dataset.addItems(self.sets)
        self.dataset.setCurrentText(self.s.lora_dataset)
        self.dataset.currentTextChanged.connect(self._load_set)
        self.phrase = QLabel(wordWrap=True, alignment=Qt.AlignCenter)
        self.phrase.setFont(QFont("Segoe UI", 16))
        self.phrase.setMinimumHeight(120)
        self.progress = QLabel(alignment=Qt.AlignCenter)
        self.prev = QPushButton(tr("prev"), clicked=lambda: self._go(-1))
        self.record = QPushButton(tr("record"), clicked=self._toggle_record)
        self.next = QPushButton(tr("next"), clicked=lambda: self._go(1))
        self.train = QPushButton(tr("start_training"), clicked=self._train)
        self.output = QPlainTextEdit(readOnly=True, maximumBlockCount=400)
        self.output.hide()
        self.log_line.connect(self.output.appendPlainText)
        self.finished_training.connect(self._done)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("dataset")))
        top.addWidget(self.dataset, 1)
        buttons = QHBoxLayout()
        for b in (self.prev, self.record, self.next):
            buttons.addWidget(b)
        buttons.addStretch()
        buttons.addWidget(self.train)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.phrase, 1)
        layout.addWidget(self.progress)
        layout.addLayout(buttons)
        layout.addWidget(self.output)
        self._load_set(self.dataset.currentText())

    # -- navigation -----------------------------------------------------------

    @property
    def folder(self) -> Path:
        return RECORDINGS_DIR / self.dataset.currentText()

    def _wav(self, i: int) -> Path:
        return self.folder / f"{i:03d}.wav"

    def _load_set(self, name: str) -> None:
        self.s.lora_dataset = name
        self.phrases = read_phrases(self.sets[name]) if name in self.sets else []
        done = [i for i in range(len(self.phrases)) if not self._wav(i).exists()]
        self.index = done[0] if done else 0
        self._refresh()

    def _go(self, step: int) -> None:
        self.index = min(max(self.index + step, 0), len(self.phrases) - 1)
        self._refresh()

    def _refresh(self) -> None:
        if not self.phrases:
            return
        recorded = sum(self._wav(i).exists() for i in range(len(self.phrases)))
        mark = "  ✓" if self._wav(self.index).exists() else ""
        self.phrase.setText(self.phrases[self.index] + mark)
        self.progress.setText(tr("progress", i=self.index + 1, n=len(self.phrases), done=recorded))

    # -- recording ------------------------------------------------------------

    def _toggle_record(self) -> None:
        if self.audio is None:
            self.frames = []
            self.audio = AudioInput(self.frames.append, self.s.microphone,
                                    self.s.noise_suppression, False, self.s.auto_gain)
            self.audio.start()
            self.record.setText(tr("stop"))
            return
        self.audio.stop()
        self.audio = None
        self.record.setText(tr("record"))
        if self.frames:
            save_wav(self._wav(self.index), np.concatenate(self.frames))
        self._go(1)

    # -- training -------------------------------------------------------------

    def _manifest(self) -> Path:
        path = self.folder / "manifest.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for i, text in enumerate(self.phrases):
                wav = self._wav(i)
                if wav.exists():
                    with wave.open(str(wav)) as w:
                        duration = w.getnframes() / RATE
                    f.write(json.dumps({"audio_filepath": str(wav), "duration": duration,
                                        "text": text}, ensure_ascii=False) + "\n")
        return path

    def _train(self) -> None:
        recorded = sum(self._wav(i).exists() for i in range(len(self.phrases)))
        if recorded < MIN_RECORDINGS:
            QMessageBox.information(self, tr("train_title"), tr("need_more"))
            return
        name = f"{self.dataset.currentText()}-{time.strftime('%Y%m%d-%H%M')}"
        manifest = self._manifest()
        self.train.setEnabled(False)
        self.output.show()
        self.output.appendPlainText(tr("training"))
        threading.Thread(target=self._train_worker, args=(name, manifest), daemon=True).start()

    def _train_worker(self, name: str, manifest: Path) -> None:
        from ..asr import model_dir
        try:
            if not env.installed():
                env.install(self.log_line.emit)
            env.run_train(["--manifest", str(manifest), "--base-onnx", str(model_dir()),
                           "--out", str(MODELS_DIR / "adapters" / name)], self.log_line.emit)
            self.finished_training.emit(True, name)
        except Exception as err:  # surfaced to the user in the log
            self.log_line.emit(str(err))
            self.finished_training.emit(False, name)

    def _done(self, ok: bool, name: str) -> None:
        self.train.setEnabled(True)
        if ok:
            self.s.lora_adapter = name
        QMessageBox.information(self, tr("train_title"),
                                tr("trained", name=name) if ok else tr("train_failed"))

    def closeEvent(self, e):
        if self.audio:
            self.audio.stop()
        super().closeEvent(e)


def confirm_dependencies(parent=None) -> bool:
    """Warn before entering: training needs a large separate environment."""
    if env.installed():
        return True
    answer = QMessageBox.question(parent, tr("deps_title"), tr("deps_text", path=env.ENV_DIR))
    return answer == QMessageBox.Yes
