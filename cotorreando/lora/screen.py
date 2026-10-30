"""What appears when the user lets a shutdown or restart be used for training."""

from __future__ import annotations

import logging
import threading

import numpy as np
from PySide6.QtCore import QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..audio import AudioInput
from ..dialogs import Window, ask_password
from ..i18n import tr
from ..mosaic import Mosaic
from ..vault import WrongPassword
from . import env, job

log = logging.getLogger(__name__)

FADE_MS = 900
MIN_READING_S = 1.0
PASSWORD_TRIES = 3
PREPARE_SHARE = 0.05         # of the parrot, lit before training starts
EXPORT_SHARE = 0.95


class ShutdownPrompt(Window):
    """Windows does not say whether a shutdown or a restart was asked for, so this does."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cotorreando")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.choice = None           # None = stay on, else (train, "/s" or "/r")
        title = QLabel(tr("shut_title"), objectName="title")
        text = QLabel(tr("shut_text"), objectName="body", wordWrap=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(text)
        layout.addSpacing(10)
        for label, choice, ghost in (("shut_train_off", (True, "/s"), False),
                                     ("shut_train_restart", (True, "/r"), False),
                                     ("shut_off", (False, "/s"), True),
                                     ("shut_restart", (False, "/r"), True),
                                     ("shut_stay", None, True)):
            button = QPushButton(tr(label), objectName="ghost" if ghost else "")
            button.clicked.connect(lambda _=False, c=choice: self._choose(c))
            layout.addWidget(button)
        self.setFixedWidth(460)

    def _choose(self, choice) -> None:
        self.choice = choice
        self.accept()


class TrainingScreen(QWidget):
    """Full screen: the parrot lights up with real progress. The cross saves and leaves."""

    ended = Signal(object)       # the job's Result, or None if nothing ran to the end
    line = Signal(str)
    stage = Signal(str)
    share = Signal(float)
    panels_ready = Signal(list)
    trained = Signal(object)

    def __init__(self, learner, settings):
        super().__init__()
        self.learner, self.s = learner, settings
        self.leaving = False
        self.audio: AudioInput | None = None
        self.frames: list[np.ndarray] = []
        self.panels: list[dict] = []
        self.setObjectName("screen")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setStyleSheet("#screen, #screen QWidget { background: #0d0e11; }")
        self.setAttribute(Qt.WA_StyledBackground)

        self.mosaic = Mosaic(12, 0.0)
        self.title = QLabel(objectName="title", alignment=Qt.AlignCenter)
        self.bar = QProgressBar(objectName="meter", textVisible=False, maximum=1000)
        self.bar.setFixedWidth(self.mosaic.width())
        hint = QLabel(tr("screen_hint"), objectName="note", alignment=Qt.AlignCenter)
        close = QPushButton("✕", objectName="ghost", clicked=self.cancel)
        close.setFixedSize(44, 44)
        close.setStyleSheet("font-size: 16pt; padding: 0;")
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(close)

        progress = QWidget()
        column = QVBoxLayout(progress)
        column.setAlignment(Qt.AlignCenter)
        column.addWidget(self.mosaic, 0, Qt.AlignHCenter)
        column.addSpacing(28)
        column.addWidget(self.title)
        column.addSpacing(12)
        column.addWidget(self.bar, 0, Qt.AlignHCenter)

        reading = QWidget()
        panel_column = QVBoxLayout(reading)
        panel_column.setAlignment(Qt.AlignCenter)
        self.read_title = QLabel(tr("screen_read"), objectName="title", alignment=Qt.AlignCenter)
        self.panel = QLabel(objectName="panel", wordWrap=True, alignment=Qt.AlignCenter)
        self.panel.setMaximumWidth(900)
        again = QPushButton(tr("cal_again"), objectName="ghost", clicked=self._restart_reading)
        skip = QPushButton(tr("screen_skip"), objectName="ghost", clicked=self._skip_readings)
        done = QPushButton(tr("cal_done"), clicked=self._finish_reading)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (skip, again, done):
            buttons.addWidget(button)
        buttons.addStretch()
        panel_column.addWidget(self.read_title)
        panel_column.addSpacing(24)
        panel_column.addWidget(self.panel, 0, Qt.AlignHCenter)
        panel_column.addSpacing(24)
        panel_column.addLayout(buttons)

        self.pages = QStackedWidget()
        self.pages.addWidget(progress)
        self.pages.addWidget(reading)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.addLayout(top)
        layout.addWidget(self.pages, 1)
        layout.addWidget(hint)

        self.stage.connect(self.title.setText)
        self.share.connect(self._set_share)
        self.line.connect(self._on_line)
        self.panels_ready.connect(self._on_panels)
        self.trained.connect(self._on_trained)

    def begin(self) -> None:
        self.setWindowOpacity(0.0)
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.fade = QPropertyAnimation(self, b"windowOpacity", duration=FADE_MS, startValue=0.0, endValue=1.0)
        self.fade.start()
        QTimer.singleShot(FADE_MS, self._start)

    def _start(self) -> None:
        if self.leaving:
            return
        if not self._unlock():
            self._leave(None)
            return
        self.title.setText(tr("screen_prepare"))
        threading.Thread(target=self._prepare, daemon=True, name="prepare").start()

    def _unlock(self) -> bool:
        vault = self.learner.vault
        for _ in range(PASSWORD_TRIES):
            if not vault.locked:
                return True
            password = ask_password(self, tr("password_current"))
            if password is None:
                return False
            try:
                vault.unlock(password)
            except WrongPassword:
                pass
        return not vault.locked

    def _prepare(self) -> None:
        try:
            env.ensure_installed(log.info)
            self.share.emit(PREPARE_SHARE / 2)
            self.stage.emit(tr("screen_panels"))
            language = "en" if self.s.lora_language == "en" else "es"
            panels = job.write_panels(self.learner, language) if not self.leaving else []
        except Exception:
            log.exception("Could not prepare the training")
            panels = []
        self.panels_ready.emit(panels)

    # -- reading --------------------------------------------------------------

    def _on_panels(self, panels: list) -> None:
        if self.leaving:
            return
        self.panels = panels
        if panels:
            self.pages.setCurrentIndex(1)
            self.audio = AudioInput(self.frames.append, self.s.microphone, self.s.noise_suppression,
                                    False, self.s.auto_gain)
            self.audio.start()
            self._show_reading()
        else:
            self._train()

    def _show_reading(self) -> None:
        self.frames.clear()
        self.panel.setText(self.panels[0]["text"])

    def _restart_reading(self) -> None:
        self.frames.clear()

    def _finish_reading(self) -> None:
        if len(self.frames) * 0.01 < MIN_READING_S:
            return
        current = self.panels.pop(0)
        self.learner.vault.add_record({"kind": "panel", "text": current["text"], "verified": True},
                                      np.concatenate(self.frames))
        self.learner.mark_practiced(current["word"])
        if self.panels:
            self._show_reading()
        else:
            self._skip_readings()

    def _skip_readings(self) -> None:
        self._stop_mic()
        self._train()

    def _stop_mic(self) -> None:
        if self.audio:
            self.audio.stop()
            self.audio = None

    # -- training -------------------------------------------------------------

    def _train(self) -> None:
        if self.leaving:
            return
        self.pages.setCurrentIndex(0)
        self.title.setText(tr("screen_train"))
        self._set_share(PREPARE_SHARE)
        threading.Thread(target=self._work, daemon=True, name="training").start()

    def _work(self) -> None:
        try:
            result = job.run(self.learner, self.s, self.line.emit)
        except Exception:
            log.exception("Training failed")
            result = None
        self.trained.emit(result)

    def _on_line(self, line: str) -> None:
        log.info(line)
        parts = line.split()
        if parts[:1] == ["PROGRESS"] and len(parts) == 3:
            done = int(parts[1]) / max(int(parts[2]), 1)
            self._set_share(PREPARE_SHARE + done * (EXPORT_SHARE - PREPARE_SHARE))
        elif parts[:1] == ["EXPORTING"] and not self.leaving:
            self.title.setText(tr("screen_export"))

    def _set_share(self, value: float) -> None:
        self.mosaic.set_progress(value)
        self.bar.setValue(int(value * 1000))

    def _on_trained(self, result) -> None:
        if result is not None and not result.paused:
            self._set_share(1.0)
            self.title.setText(tr("screen_done"))
        QTimer.singleShot(1200, lambda: self._leave(result))

    def cancel(self) -> None:
        """Save what was learnt so far and carry on with the shutdown."""
        if self.leaving:
            return
        self.leaving = True
        self._stop_mic()
        self.pages.setCurrentIndex(0)
        self.title.setText(tr("screen_saving"))
        if any(t.name == "training" for t in threading.enumerate()):
            env.pause()          # the worker ends and reports through ``trained``
        else:
            env.stop()           # installing or writing panels: nothing worth saving
            self._leave(None)

    def _leave(self, result) -> None:
        self._stop_mic()
        self.ended.emit(result)
        self.close()
