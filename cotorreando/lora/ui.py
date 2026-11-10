"""The calibration wizard: read a few short texts aloud, then train in the background."""

from __future__ import annotations

import logging
import queue
import threading
import time
from html import escape

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..asr import Stream
from ..audio import AudioInput, list_microphones
from ..dialogs import Window
from ..dialogs import UnlockDialog
from ..i18n import tr
from ..mosaic import Mosaic
from ..paths import DATA_DIR
from ..vault import reading_path
from . import env, job
from .align import Follower, split_words

log = logging.getLogger(__name__)

QUIET_LEVEL = 0.01       # RMS below this counts as not speaking
END_SILENCE_S = 1.2      # after the last words, this much quiet finishes the panel
MIN_AUDIO_S = 1.0
NEARLY_ALL = 2           # words that may go unrecognised at the end of a panel
CHEERS = (0.0, 0.2, 0.45, 0.7, 0.9)


class CalibrationDialog(Window):
    """Welcome → reading panels → training. Closing it during training leaves training running."""

    skipped = Signal()
    reading_started = Signal()
    reading_finished = Signal()
    trained = Signal(str)
    words_read = Signal(int, int)        # panel serial, words read
    heard_level = Signal(float)
    train_log = Signal(str)
    train_ended = Signal(bool, str)

    def __init__(self, settings, model, learner, parent=None):
        super().__init__(parent)
        self.s, self.model, self.learner = settings, model, learner
        self.setWindowTitle(tr("train_title"))
        self.setObjectName("calibration")
        self.setFixedSize(760, 560)
        self.items: list[tuple[str, int, str]] = []
        self.index = self.serial = 0
        self.position = 0
        self.frames: list[np.ndarray] = []
        self.audio: AudioInput | None = None
        self.jobs: queue.Queue = queue.Queue()
        self.last_voice = 0.0
        self.deps_thread: threading.Thread | None = None
        self.training = False

        self.pages = QStackedWidget()
        for page in (self._welcome_page(), self._reading_page(), self._training_page()):
            self.pages.addWidget(page)
        QVBoxLayout(self).addWidget(self.pages)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.words_read.connect(self._on_words)
        self.heard_level.connect(self._on_level)
        self.train_log.connect(self._on_train_log)
        self.train_ended.connect(self._on_trained)
        self.end_timer = QTimer(self, interval=150, timeout=self._check_finished)

    # -- pages ----------------------------------------------------------------

    def _welcome_page(self) -> QWidget:
        page = QWidget()
        title = QLabel(tr("cal_welcome"), objectName="title", wordWrap=True)
        text = QLabel(tr("cal_intro"), objectName="body", wordWrap=True)
        self.language = QComboBox()
        for value, label in (("es", "Español"), ("en", "English"), ("both", tr("cal_both"))):
            self.language.addItem(label, value)
        self.language.setCurrentIndex(max(self.language.findData(self.s.lora_language), 0))
        self.mic = QComboBox()
        self.mic.addItem(tr("default"), "")
        for name in list_microphones():
            self.mic.addItem(name, name)
        self.mic.setCurrentIndex(max(self.mic.findData(self.s.microphone), 0))
        cost = tr("cal_cost") if env.has_nvidia() else tr("cal_cost_cpu")
        note = QLabel(cost + " " + tr("cal_skip_note"), objectName="note", wordWrap=True)
        skip = QPushButton(tr("cal_skip"), objectName="ghost", clicked=self._skip)
        start = QPushButton(tr("cal_start"), clicked=self._start_reading, default=True)

        fields = QVBoxLayout()
        fields.setSpacing(6)
        for caption, box in ((tr("cal_language"), self.language), (tr("microphone"), self.mic)):
            fields.addWidget(QLabel(caption, objectName="caption"))
            fields.addWidget(box)
            fields.addSpacing(6)
        right = QVBoxLayout()
        right.addStretch()
        right.addWidget(title)
        right.addSpacing(8)
        right.addWidget(text)
        right.addSpacing(16)
        right.addLayout(fields)
        right.addWidget(note)
        right.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(skip)
        buttons.addWidget(start)
        right.addLayout(buttons)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(36)
        layout.addWidget(Mosaic(8), 0, Qt.AlignVCenter)
        layout.addLayout(right, 1)
        return page

    def _reading_page(self) -> QWidget:
        page = QWidget()
        self.mosaic = Mosaic(4, 0.0)
        self.cheer = QLabel(objectName="cheer")
        self.percent = QLabel(objectName="caption", alignment=Qt.AlignRight | Qt.AlignVCenter)
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(self.mosaic)
        head.addWidget(self.cheer, 1)
        head.addWidget(self.percent)
        self.panel_text = QLabel(objectName="panel", wordWrap=True, alignment=Qt.AlignCenter,
                                 textFormat=Qt.RichText)
        self.meter = QProgressBar(objectName="meter", textVisible=False, maximum=100)
        self.hint = QLabel(tr("cal_read_hint"), objectName="note")
        again = QPushButton(tr("cal_again"), objectName="ghost", clicked=self._restart_panel)
        done = QPushButton(tr("cal_done"), clicked=self._finish_panel)
        buttons = QHBoxLayout()
        buttons.addWidget(self.hint, 1)
        buttons.addWidget(again)
        buttons.addWidget(done)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 24, 36, 28)
        layout.addLayout(head)
        layout.addStretch()
        layout.addWidget(self.panel_text)
        layout.addStretch()
        layout.addWidget(self.meter)
        layout.addSpacing(12)
        layout.addLayout(buttons)
        return page

    def _training_page(self) -> QWidget:
        page = QWidget()
        self.final_title = QLabel(tr("cal_thanks"), objectName="title", alignment=Qt.AlignCenter)
        self.stage = QLabel(objectName="body", wordWrap=True, alignment=Qt.AlignCenter)
        self.bar = QProgressBar(objectName="meter", textVisible=False)
        self.retry = QPushButton(tr("cal_retry"), objectName="ghost", clicked=self._begin_training)
        self.retry.hide()
        self.close_button = QPushButton(tr("cal_background"), clicked=self.close)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.retry)
        buttons.addWidget(self.close_button)
        buttons.addStretch()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(64, 32, 64, 28)
        layout.addStretch()
        layout.addWidget(Mosaic(6), 0, Qt.AlignHCenter)
        layout.addSpacing(20)
        layout.addWidget(self.final_title)
        layout.addWidget(self.stage)
        layout.addSpacing(16)
        layout.addWidget(self.bar)
        layout.addStretch()
        layout.addLayout(buttons)
        return page

    # -- welcome --------------------------------------------------------------

    def _skip(self) -> None:
        self.skipped.emit()
        self.close()

    def _start_reading(self) -> None:
        self.s.lora_language = self.language.currentData()
        self.s.microphone = self.mic.currentData()
        languages = ("es", "en") if self.s.lora_language == "both" else (self.s.lora_language,)
        self.items = [(lang, i, text) for lang in languages
                      for i, text in enumerate(job.read_panels(lang))]
        missing = [n for n, (lang, i, _) in enumerate(self.items) if not reading_path(lang, i).exists()]
        self.index = missing[0] if missing else 0   # resume, or start a new calibration over
        # The heavy download runs while the user reads, so that training can start right after.
        self.deps_thread = threading.Thread(target=self._install_deps, daemon=True)
        self.deps_thread.start()
        self.reading_started.emit()
        self.audio = AudioInput(self._on_frame, self.s.microphone, self.s.noise_suppression,
                                False, self.s.auto_gain)
        self.audio.start()
        threading.Thread(target=self._follow, daemon=True, name="follower").start()
        self.pages.setCurrentIndex(1)
        self._show_panel()

    def _install_deps(self) -> None:
        try:
            env.ensure_installed(log.info)
        except Exception:          # tried again, and reported, when training starts
            log.exception("Could not install the training environment")

    # -- reading --------------------------------------------------------------

    def _show_panel(self) -> None:
        self.serial += 1
        self.frames = []
        self.position = 0
        self.last_voice = time.monotonic()
        self.jobs.put(("start", self.serial, self.items[self.index][2]))
        share = self.index / len(self.items)
        self.mosaic.set_progress(share)
        self.percent.setText(f"{share * 100:.0f} %")
        level = sum(share >= c for c in CHEERS) - 1
        self.cheer.setText(tr(f"cal_cheer{level}"))
        self._paint_words()
        self.end_timer.start()

    def _paint_words(self) -> None:
        words = split_words(self.items[self.index][2])
        html = []
        for i, word in enumerate(words):
            color = "#f3f6f4" if i < self.position else "#54d7a3" if i == self.position else "#8b998e"
            html.append(f"<span style='color:{color}'>{escape(word)}</span>")
        self.panel_text.setText(" ".join(html))

    def _on_frame(self, frame: np.ndarray) -> None:
        self.frames.append(frame)
        self.jobs.put(("audio", self.serial, frame))
        rms = float(np.sqrt(np.mean(frame ** 2)))
        if rms > QUIET_LEVEL:
            self.last_voice = time.monotonic()
        self.heard_level.emit(rms)

    def _follow(self) -> None:
        """Recognizer thread: turns the live audio into a position in the text."""
        stream, follower, serial, pending = None, None, 0, []
        while True:
            kind, job_serial, payload = self.jobs.get()
            if kind == "stop":
                return
            if kind == "start":
                serial, pending = job_serial, []
                stream, follower = Stream(self.model), Follower(payload)
            elif job_serial == serial and stream:
                pending.append(payload)
                if len(pending) >= 8 or self.jobs.empty():   # catch up in batches if we fall behind
                    try:
                        heard = stream.feed(np.concatenate(pending))
                    except Exception:
                        log.exception("Live recognition failed; the Done button still works")
                        stream = None
                        continue
                    pending = []
                    if heard:
                        self.words_read.emit(serial, follower.hear(heard))

    def _on_words(self, serial: int, position: int) -> None:
        if serial == self.serial and self.pages.currentIndex() == 1:
            self.position = position
            self._paint_words()

    def _on_level(self, rms: float) -> None:
        self.meter.setValue(min(int(rms * 400), 100))

    def _check_finished(self) -> None:
        """A panel ends by itself once its last words were heard and the reader has gone quiet."""
        words = len(split_words(self.items[self.index][2]))
        if (self.position >= words - NEARLY_ALL
                and time.monotonic() - self.last_voice > END_SILENCE_S):
            self._finish_panel()

    def _restart_panel(self) -> None:
        self._show_panel()

    def _finish_panel(self) -> None:
        if len(self.frames) * 0.01 < MIN_AUDIO_S:
            return
        self.end_timer.stop()
        language, index, _ = self.items[self.index]
        self.learner.vault.save_reading(language, index, np.concatenate(self.frames))
        self.index += 1
        if self.index < len(self.items):
            self._show_panel()
        else:
            self._stop_reading()
            self.reading_finished.emit()
            self.pages.setCurrentIndex(2)
            self._begin_training()

    def _stop_reading(self) -> None:
        self.end_timer.stop()
        if self.audio:
            self.audio.stop()
            self.audio = None
            self.jobs.put(("stop", 0, None))

    # -- training -------------------------------------------------------------

    def _begin_training(self) -> None:
        if self.learner.vault.locked and not UnlockDialog(self.learner, self).exec():
            self.train_ended.emit(False, "")
            return
        self.training = True
        self.retry.hide()
        self.final_title.setText(tr("cal_thanks"))
        self.stage.setText(tr("cal_stage_install"))
        self.bar.setRange(0, 0)
        self.close_button.setText(tr("cal_background"))
        threading.Thread(target=self._train_worker, daemon=True).start()

    def _train_worker(self) -> None:
        try:
            self.deps_thread.join()
            env.ensure_installed(log.info)
            self.train_log.emit("TRAINING")
            result = job.run(self.learner, self.s, self.train_log.emit)
            if result.before is not None:
                self.train_log.emit(f"EVAL {result.before} {result.after}")
            self.train_ended.emit(True, result.adapter)
        except Exception:
            log.exception("Calibration failed")
            self.train_ended.emit(False, "")
        finally:
            self.learner.vault.lock()

    def _on_train_log(self, line: str) -> None:
        log.info(line)
        words = line.split()
        if line == "TRAINING":
            self.stage.setText(tr("cal_stage_train"))
        elif words[:1] == ["PROGRESS"]:
            self.bar.setRange(0, int(words[2]))
            self.bar.setValue(int(words[1]))
        elif words[:1] == ["EXPORTING"]:
            self.stage.setText(tr("cal_stage_export"))
            self.bar.setRange(0, 0)
        elif words[:1] == ["EVAL"]:
            self.errors = float(words[1]), float(words[2])

    def _on_trained(self, ok: bool, name: str) -> None:
        self.training = False
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.close_button.setText(tr("cal_finish"))
        if not ok:
            self.final_title.setText(tr("cal_failed_title"))
            self.stage.setText(tr("cal_failed", path=DATA_DIR / "cotorreando.log"))
            self.retry.show()
            return
        before, after = getattr(self, "errors", (0.0, 0.0))
        if name:
            self.final_title.setText(tr("cal_ready"))
            self.stage.setText(tr("cal_result", before=before * 100, after=after * 100))
            self.trained.emit(name)
        else:
            self.final_title.setText(tr("cal_ready"))
            self.stage.setText(tr("cal_no_gain"))
            self.trained.emit("")

    def closeEvent(self, e):
        self._stop_reading()
        super().closeEvent(e)
