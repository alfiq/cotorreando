"""Wires everything together: audio -> listener -> recognizer -> keyboard, plus the UI.

Threads
-------
mic / loopback   capture and WebRTC processing (audio.py)
keyboard         hotkey and typing detection (keyboard.py)
recognizer       Parakeet inference and typing (this file)
Qt main thread   blob, tray, menus and dialogs; other threads talk to it via signals.
"""

from __future__ import annotations

import ctypes
import difflib
import logging
import queue
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
import winreg
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import __version__, asr, model_store, palette, updates
from .audio import AudioInput
from .blob import Blob
from .config import Settings
from .dialogs import (
    AboutDialog,
    DownloadDialog,
    ModelErrorDialog,
    Notice,
    SettingsDialog,
    SetupDialog,
    UnlockDialog,
    WelcomeDialog,
    apply_theme,
    choose_model_folder,
    model_error_text,
    styled_menu,
)
from .i18n import set_language, tr
from .keyboard import KeyboardMonitor, foreground, ours_in_front, replace_text, type_text
from .learning import Learner, fit_start
from .listener import Listener
from .lora import env
from .paths import DATA_DIR, MODELS_DIR
from .residency import ModelHolder

log = logging.getLogger(__name__)
UPDATE_DELAY_MS = 30_000  # let the app settle before going online
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WM_QUERYENDSESSION = 0x0011
ENDSESSION_CRITICAL = 0x40000000


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if c.isalnum() or c.isspace())
    return " ".join(text.split())


def after_keyword(text: str, keyword: str) -> str | None:
    """Fuzzy-find ``keyword`` in ``text``; return what follows it, or None."""
    words, key = text.split(), normalize(keyword)
    n = len(key.split())
    for i in range(len(words) - n + 1):
        window = normalize(" ".join(words[i : i + n]))
        if difflib.SequenceMatcher(None, window, key).ratio() >= 0.75:
            return " ".join(words[i + n :]).lstrip(",.;: ")
    return None


class SessionFilter(QAbstractNativeEventFilter):
    """Lets ``handler`` hold back a shutdown or restart while Windows is asking for permission."""

    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    def nativeEventFilter(self, _kind, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_QUERYENDSESSION and not msg.lParam & ENDSESSION_CRITICAL and self.handler():
            return True, 0
        return False, 0


def on_battery() -> bool:
    class Power(ctypes.Structure):
        _fields_ = [
            ("ac", ctypes.c_ubyte),
            ("flag", ctypes.c_ubyte),
            ("percent", ctypes.c_ubyte),
            ("saver", ctypes.c_ubyte),
            ("life", wintypes.DWORD),
            ("full", wintypes.DWORD),
        ]

    power = Power()
    return bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power))) and power.ac == 0


class Cotorreando(QObject):
    level = Signal(float, float, bool)
    writing = Signal(bool)
    status = Signal(str)
    loaded = Signal()
    toggle_requested = Signal()
    warning = Signal(str)
    loading = Signal(float)  # -1 = busy, 0..1 = download progress
    update_found = Signal(str, str)  # version, release page
    model_failed = Signal(object)  # the exception that kept the model from loading

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.s = Settings.load()
        set_language(self.s.ui_language)
        self.enabled = True
        self.holder = ModelHolder(
            self._build_model,
            self.s.model_unload_min * 60,
            on_load_start=self._on_load_start,
            on_load_done=self._on_load_done,
        )
        self._announce = False  # the next successful load emits ``loaded``
        self._queued_uid = None
        self._pinned = None  # the model the calibration window holds
        self.audio: AudioInput | None = None
        self.listener: Listener | None = None
        self.jobs: queue.Queue = queue.Queue()
        self._silent_frames = -1
        self.calibration = None
        self.learner = Learner(self.s)
        self._leaving = False
        self._asking = False
        self.screen = None
        self._session_filter = SessionFilter(self._on_end_session)
        app.installNativeEventFilter(self._session_filter)

        self.blob = Blob(self.s.blob_size)
        self.blob.place(self.s.blob_x, self.s.blob_y)
        self.blob.set_hotkey(self.s.hotkey)
        self.blob.moved.connect(self._remember_position)
        self.blob.menu_requested.connect(self._show_menu)
        self.level.connect(self.blob.set_level)
        self.writing.connect(self.blob.set_writing)
        self.loaded.connect(self._on_loaded)
        self.loading.connect(lambda v: self.blob.set_loading(None if v < -1 else v))
        self.toggle_requested.connect(self.toggle_enabled)

        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Cotorreando")
        self.tray.activated.connect(self._tray_activated)
        self.status.connect(lambda text: self.tray.setToolTip(f"Cotorreando · {text}"))
        self.menu = styled_menu()
        self.menu.aboutToShow.connect(self._build_menu)
        self.tray.setContextMenu(self.menu)
        self.warning.connect(
            lambda text: self.tray.showMessage("Cotorreando", text, QSystemTrayIcon.MessageIcon.Warning)
        )
        self.tray.show()

        self.keyboard = KeyboardMonitor(self.s.hotkey, self._hotkey_down, self._hotkey_up)
        self.keyboard.start()
        threading.Thread(target=self._recognizer, daemon=True, name="recognizer").start()

        if not self.s.hidden:
            self.blob.show()
        self.blob.set_enabled(False)  # grey until the model is loaded
        self.model_failed.connect(self._on_model_failed)
        QTimer.singleShot(0, self._prepare_model)  # its dialogs need the event loop running
        self.update_found.connect(self._offer_update)
        QTimer.singleShot(UPDATE_DELAY_MS, self._check_updates)
        self._collector = QTimer(self, interval=30_000)
        self._collector.timeout.connect(self.holder.collect)  # frees the model when idle
        self._collector.start()

    # -- model & audio --------------------------------------------------------

    def _model_dir(self):
        if self.s.custom_model:
            return Path(self.s.custom_model)  # adapters are trained on the stock model only
        path = MODELS_DIR / "adapters" / self.s.lora_adapter
        return path if self.s.lora_adapter and path.exists() else asr.model_dir()

    def _prepare_model(self) -> None:
        """Main thread: download the model if needed (with its own window), then load it."""
        self.holder.unload(force=True)
        while not self.s.custom_model and not asr.is_downloaded():
            self.status.emit(tr("loading"))
            dialog = DownloadDialog(asr.download)
            if dialog.exec():
                break
            log.warning("Model download failed: %r", dialog.error)
            if not self._resolve_model_problem(model_error_text(dialog.error), "retry", tr("retry")):
                return
        self._announce = True
        self.holder.invalidate()

    def _resolve_model_problem(self, text: str, fix: str, fix_label: str) -> bool:
        """Offer ``fix``, the user's own model (or back to the stock one) and quitting.
        True if something changed and the model should be prepared again."""
        options = [("own", tr("use_own_model")), (fix, fix_label)]
        if self.s.custom_model:
            options.insert(0, ("stock", tr("use_stock_model")))
        dialog = ModelErrorDialog(text, options)
        dialog.exec()
        if dialog.choice == "own":
            path = choose_model_folder(None, self.s.custom_model)
            if not path:
                return self._resolve_model_problem(text, fix, fix_label)
            self.s.custom_model = path
        elif dialog.choice == "stock":
            self.s.custom_model = ""
        elif dialog.choice == "redownload":
            model_store.remove(asr.model_dir())
        elif dialog.choice != "retry":
            QTimer.singleShot(0, self.quit)
            return False
        self.s.save()
        return True

    def _on_model_failed(self, err: Exception) -> None:
        if self.s.custom_model:
            text = tr("model_custom_failed", path=self.s.custom_model, error=err)
            again = self._resolve_model_problem(text, "retry", tr("retry"))
        else:
            again = self._resolve_model_problem(tr("model_corrupt", error=err), "redownload", tr("redownload"))
        if again:
            self._prepare_model()

    def _build_model(self) -> asr.Parakeet:
        """Loading thread: the holder's factory."""
        custom = bool(self.s.custom_model)
        try:
            model = asr.Parakeet(self._model_dir(), use_gpu=self.s.use_gpu, custom=custom)
        except Exception:
            if not self.s.use_gpu:
                raise
            log.exception("GPU model load failed; retrying on the CPU")
            model = asr.Parakeet(self._model_dir(), use_gpu=False, custom=custom)
        model.boost_alpha = self.s.boost_alpha
        log.info("Model loaded (%s)", "GPU" if model.on_gpu else "CPU")
        return model

    def _on_load_start(self) -> None:
        self.status.emit(tr("loading"))
        self.loading.emit(-1)

    def _on_load_done(self, err: Exception | None, discarded: bool) -> None:
        self.loading.emit(-2)
        if discarded:
            return
        if err is not None:
            log.error("Model load failed", exc_info=err)
            self.status.emit(tr("load_failed", error=err))
            self.model_failed.emit(err)
            return
        self.status.emit(tr("ready") if self.enabled else tr("disabled"))
        if self._announce:  # reloads after an idle unload stay silent
            self._announce = False
            self.loaded.emit()

    def _on_loaded(self) -> None:
        vault = self.learner.vault
        first_run = not vault.ready and not self.s.password_offered
        if first_run:
            self.s.password_offered = True
            self.s.save()
            SetupDialog(self.learner).exec()
        if self.s.calibrated or self.s.lora_adapter:
            self.start_audio()
        elif vault.ready:
            self.open_training()
        else:
            self.s.calibrated = True  # calibration keeps your voice, which takes the password
            self.start_audio()
        if not first_run:
            self._offer_password()

    # -- updates --------------------------------------------------------------

    def _check_updates(self) -> None:
        if not updates.due(self.s):
            return

        def run():
            found = updates.check(self.s)
            if found:
                self.update_found.emit(*found)

        threading.Thread(target=run, daemon=True, name="updates").start()

    def _offer_update(self, version: str, url: str) -> None:
        def skip():
            self.s.update_skipped = version
            self.s.save()

        self.update_notice = Notice(
            tr("update_available", version=version, current=__version__),
            tr("update_open"),
            lambda: webbrowser.open(url),
            tr("update_skip"),
            skip,
        )
        area = self.blob.screen().availableGeometry()
        corner = QRect(area.bottomRight(), area.bottomRight())
        self.update_notice.show_near(self.blob.geometry() if self.blob.isVisible() else corner, area)

    # -- password -------------------------------------------------------------

    def _offer_password(self) -> None:
        if not self.s.learning or self.learner.loaded:
            return
        ready = self.learner.vault.ready
        self.notice = Notice(
            tr("notice_unlock" if ready else "notice_setup"),
            tr("notice_action" if ready else "notice_setup_action"),
            self.ask_password,
        )
        area = self.blob.screen().availableGeometry()
        corner = QRect(area.bottomRight(), area.bottomRight())
        self.notice.show_near(self.blob.geometry() if self.blob.isVisible() else corner, area)

    def ask_password(self) -> None:
        vault = self.learner.vault
        if not vault.ready:
            SetupDialog(self.learner).exec()
        elif UnlockDialog(self.learner).exec():
            vault.lock()  # the word lists stay in memory; the key does not

    def start_audio(self) -> None:
        self.stop_audio()
        if not self.enabled or not self.holder.available:
            log.info("Not listening (enabled=%s, model=%s)", self.enabled, self.holder.available)
            return
        self.listener = Listener(
            self.s,
            lambda uid, audio: self._queue("audio", uid, audio),
            lambda uid: self.jobs.put(("end", uid, None)),
            self.level.emit,
        )
        self.audio = AudioInput(
            self._on_frame, self.s.microphone, self.s.noise_suppression, self.s.echo_cancellation, self.s.auto_gain
        )
        self._silent_frames = 0
        log.info("Listening on %s (mode %s)", self.s.microphone or "default microphone", self.s.mode)
        self.audio.start()
        self.blob.set_enabled(True)

    def _queue(self, kind: str, uid, audio) -> None:
        if uid != self._queued_uid:  # a new utterance: start loading the model if it was freed
            self._queued_uid = uid
            if not self.holder.failed:
                self.holder.ensure_loading()
        self.jobs.put((kind, uid, audio))

    def stop_audio(self) -> None:
        if self.audio:
            self.audio.stop()
        self.audio = None

    def _on_frame(self, frame) -> None:
        listener = self.listener
        if listener is None:
            return
        # Windows hands out pure zeros when microphone access is denied in Privacy settings.
        if self._silent_frames >= 0:
            self._silent_frames = self._silent_frames + 1 if not frame.any() else -1
            if self._silent_frames == 300:  # 3 s
                log.warning("Microphone delivers only silence")
                self.warning.emit(tr("mic_silent"))
                self._silent_frames = -1
        holdoff = self.s.typing_holdoff_ms / 1000
        if time.monotonic() - self.keyboard.last_typed < holdoff:
            listener.pause_for_typing(holdoff)
        listener.feed(frame)

    def _recognizer(self) -> None:
        """Consume listener events; stream text out as soon as it is final."""
        uid, stream, buffered, cancelled, heard, field = 0, None, [], False, [], None
        bound = None  # the model this utterance started on
        while True:
            kind, job_uid, audio = self.jobs.get()
            if not self.enabled:
                continue
            try:
                with self.holder.using() as model:  # waits while a freed model loads again
                    if job_uid != uid:  # a new utterance (an unfinished one was cancelled)
                        uid, buffered, cancelled, heard, bound = job_uid, [], False, [], model
                        stream = asr.Stream(model) if self._should_stream() else None
                        self._tail, self._tail_since, self._tail_window = "", time.monotonic(), foreground()
                        self._typed, self._started = "", False
                        field = self.learner.begin(self._tail_window)
                        self._before = field.before if field and not field.password else None
                        boost = self.s.boost_mode == "on" or (self.s.boost_mode == "auto" and self.s.vocabulary_on)
                        model.set_phrases(self.learner.bias_words(field) if boost else None)
                    elif model is not bound or model.closed:
                        cancelled = True  # the model was replaced mid-utterance
                    if time.monotonic() - self.keyboard.last_typed < self.s.typing_holdoff_ms / 1000:
                        cancelled = True  # you are typing; never write over it
                    if ours_in_front():
                        cancelled = True  # never into our own windows, such as the password
                    if cancelled:
                        continue
                    if kind == "audio":
                        heard.append(audio)
                        if stream:
                            self._rewrite(stream.feed(audio), stream.tail)
                        else:
                            buffered.append(audio)
                    elif stream:
                        self._rewrite(stream.finish(), "", end=True)
                        self._finish_utterance(heard, stream.trace, field)
                    elif buffered:
                        whole = asr.Stream(model)
                        text = (whole.feed(np.concatenate(buffered)) + whole.finish()).strip()
                        self._type(self._apply_activation(text), end=True)
                        self._finish_utterance(heard, whole.trace, field)
            except Exception:
                if self.holder.failed or not self.holder.available:
                    continue  # no model: drop the job (model_failed says why)
                log.exception("Transcription failed")

    def _finish_utterance(self, heard: list, trace: list, field) -> None:
        typed = self._typed
        if heard:
            self.learner.finish(typed, np.concatenate(heard), trace, field)

    def _fit(self, text: str, tail: str) -> tuple[str, str]:
        """Until something is final, the first text on screen is fitted to what precedes it."""
        if self._started:
            return text, tail
        if text.strip():
            self._started = True
            return fit_start(text, self._before), tail
        return text, fit_start(tail, self._before)

    def _should_stream(self) -> bool:
        keyword = self.s.mode == "activation" and self.s.activation == "keyword"
        return self.s.streaming and (not keyword or bool(self.listener and self.listener.awake))

    def _rewrite(self, text: str, tail: str, end: bool = False) -> None:
        """Swap the tentative tail on screen for the new final text plus the new tail."""
        window = foreground()
        if self.keyboard.last_click > self._tail_since or window != self._tail_window:
            # The caret moved: what is before it is no longer ours to delete.
            self._tail, self._tail_since, self._tail_window = "", time.monotonic(), window
        if (text or tail) and self.listener and self.listener.awake:
            self.listener.wake()  # keyword mode: keep the session alive
        text, tail = self._fit(text, tail)
        if end and text.strip() and self.s.trailing_space:
            text = text.rstrip() + " "
        self._typed += text
        old, self._tail = self._tail, tail
        if text + tail == old:  # what was tentative may just have become final
            return
        self.writing.emit(True)
        replace_text(old, text + tail)
        self.writing.emit(False)

    def _type(self, text: str, end: bool = False) -> None:
        if text and self.listener and self.listener.awake:
            self.listener.wake()  # keyword mode: keep the session alive
        text = self._fit(text, "")[0]
        if end and text.strip() and self.s.trailing_space:
            text = text.rstrip() + " "
        if not text:
            return
        self._typed += text
        self.writing.emit(True)
        type_text(text)
        self.writing.emit(False)

    def _apply_activation(self, text: str) -> str:
        if self.s.mode != "activation" or self.s.activation != "keyword" or not text:
            return text
        if self.listener and self.listener.awake:
            self.listener.wake()
            return text
        rest = after_keyword(text, self.s.keyword)
        if rest is None:
            return ""
        self.listener.wake()
        return rest[:1].upper() + rest[1:]

    # -- hotkey ---------------------------------------------------------------

    def _hotkey_down(self) -> None:
        if self.enabled and not self.holder.failed:
            self.holder.ensure_loading()  # you are about to speak
        if self.s.mode == "ptt":
            if self.listener:
                self.listener.push_to_talk(True)
        else:
            self.toggle_requested.emit()

    def _hotkey_up(self) -> None:
        if self.s.mode == "ptt" and self.listener:
            self.listener.push_to_talk(False)

    # -- UI actions -----------------------------------------------------------

    def toggle_enabled(self) -> None:
        self.enabled = not self.enabled
        if self.enabled:
            if self.holder.failed:  # an earlier load failed: try again, then start listening
                self._announce = True
            self.holder.ensure_loading()
        self.blob.set_enabled(self.enabled)
        self.start_audio() if self.enabled else self.stop_audio()
        self.tray.setIcon(self._tray_icon())
        self.status.emit(tr("ready") if self.enabled else tr("disabled"))

    def toggle_hidden(self) -> None:
        self.s.hidden = not self.s.hidden
        self.blob.setVisible(not self.s.hidden)
        self.s.save()

    def open_settings(self) -> None:
        old = (self.s.use_gpu, self.s.lora_adapter, self.s.custom_model)
        dialog = SettingsDialog(self.s, self.listener, self.learner)
        accepted = dialog.exec()
        if dialog.calibrate_requested:
            self.open_training()
            return
        if not accepted:
            return
        set_language(self.s.ui_language)
        self.keyboard.set_hotkey(self.s.hotkey)
        self.blob.set_hotkey(self.s.hotkey)
        self.blob.set_size(self.s.blob_size)
        set_autostart(self.s.autostart)
        self.holder.idle_s = self.s.model_unload_min * 60
        self.s.save()
        if (self.s.use_gpu, self.s.lora_adapter, self.s.custom_model) != old:
            self._reload_model()
        else:
            self.start_audio()

    def _reload_model(self) -> None:
        self.stop_audio()
        self._prepare_model()

    def open_training(self) -> None:
        from .lora.ui import CalibrationDialog  # rarely used, load lazily

        if self.calibration is not None:
            self.calibration.show()
            self.calibration.raise_()
            return
        model = self.holder.pin()  # kept loaded while the window is open
        if model is None:
            self.holder.ensure_loading()
            self.warning.emit(tr("loading"))
            return
        self._pinned = model
        dialog = self.calibration = CalibrationDialog(self.s, model, self.learner)
        dialog.skipped.connect(self._calibration_skipped)
        dialog.reading_started.connect(self.stop_audio)  # free the microphone
        dialog.reading_finished.connect(self.start_audio)
        dialog.trained.connect(self._calibration_trained)
        dialog.finished.connect(self._calibration_closed)
        dialog.show()

    def _calibration_skipped(self) -> None:
        self.s.calibrated = True
        self.s.save()
        self.tray.showMessage("Cotorreando", tr("cal_skipped_tip"))

    def _calibration_trained(self, adapter: str) -> None:
        self.s.calibrated = True
        if adapter:
            self.s.lora_adapter = adapter
            self.tray.showMessage("Cotorreando", tr("cal_applied"))
            self._reload_model()
        if not self.s.training_notice_shown:
            self.s.training_notice_shown = True
            self.tray.showMessage("Cotorreando", tr("train_notice"))
        self.s.save()
        if not self.calibration.isVisible():
            self._calibration_closed()

    def _calibration_closed(self) -> None:
        dialog = self.calibration
        if not dialog.training:
            self.calibration = None
            dialog.deleteLater()
            if self._pinned is not None:
                self.holder.unpin(self._pinned)
                self._pinned = None
        self.s.save()
        if not self.audio:
            self.start_audio()

    # -- training at shutdown -------------------------------------------------

    def _on_end_session(self) -> bool:
        """True holds the shutdown back. Windows then cancels it and we run it again later."""
        if self._leaving:
            return False
        if self._asking:
            return True
        from .lora import job

        if not self.s.learning or on_battery() or self.calibration or not job.is_pending(self.learner):
            return False
        self._asking = True
        QTimer.singleShot(0, self._ask_at_shutdown)
        return True

    def _ask_at_shutdown(self) -> None:
        from .lora.screen import ShutdownPrompt

        prompt = ShutdownPrompt()
        prompt.exec()
        self._asking = False
        if prompt.choice is None:
            return
        train, action = prompt.choice
        if train:
            self._train_then(action)
        else:
            self._power(action)

    def _train_then(self, action: str | None) -> None:
        from .lora.screen import TrainingScreen

        self.stop_audio()
        self.holder.suspend()  # free the GPU for training, and keep it free
        self.screen = TrainingScreen(self.learner, self.s)
        self.screen.ended.connect(lambda result: self._training_over(result, action))
        self.screen.begin()

    def _training_over(self, result, action: str | None) -> None:
        if result and result.adapter:
            self.s.lora_adapter = result.adapter
        self.s.save()
        self.learner.vault.lock()
        self.screen = None
        self.holder.resume()
        if action:
            self._power(action)
        else:
            self._reload_model()

    def _power(self, action: str) -> None:
        self._leaving = True
        self.s.save()
        subprocess.run(["shutdown", action, "/t", "0"], creationflags=subprocess.CREATE_NO_WINDOW)

    def open_about(self) -> None:
        AboutDialog().exec()

    def quit(self) -> None:
        self.stop_audio()
        env.stop()
        self.keyboard.stop()
        self.s.save()
        self.tray.hide()
        self.app.quit()

    def _build_menu(self) -> None:
        self.menu.clear()
        items = [
            (tr("disable") if self.enabled else tr("enable"), self.toggle_enabled),
            (tr("show") if self.s.hidden else tr("hide"), self.toggle_hidden),
            None,
            *([(tr("unlock_menu"), self.ask_password)] if not self.learner.loaded else []),
            (tr("settings"), self.open_settings),
            (tr("train"), self.open_training),
            (tr("about"), self.open_about),
            None,
            (tr("quit"), self.quit),
        ]
        for item in items:
            if item is None:
                self.menu.addSeparator()
            else:
                action = QAction(item[0], self.menu)
                action.triggered.connect(item[1])
                self.menu.addAction(action)

    def _show_menu(self, pos: QPoint) -> None:
        self.menu.popup(pos)

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_hidden()

    def _remember_position(self, x: int, y: int) -> None:
        self.s.blob_x, self.s.blob_y = x, y
        self.s.save()

    def _tray_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(palette.ACCENT if self.enabled else palette.OFF))
        p.drawEllipse(6, 6, 52, 52)
        p.end()
        return QIcon(pix)


def set_autostart(on: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            command = f'"{sys.executable}"'
            if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
                command = f'"{sys.executable.replace("python.exe", "pythonw.exe")}" -m cotorreando'
            winreg.SetValueEx(key, "Cotorreando", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "Cotorreando")
            except FileNotFoundError:
                pass


def already_running() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    already_running.mutex = kernel32.CreateMutexW(None, False, "Local\\Cotorreando")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main() -> int:
    if already_running():  # before the log is opened: opening it wipes what the running copy wrote
        return 0
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(DATA_DIR / "cotorreando.log", mode="w", encoding="utf-8")]
    if sys.stderr is not None:  # the windowed build has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s", handlers=handlers)
    # Without a console, exceptions raised in Qt slots would vanish.
    sys.excepthook = lambda *exc: logging.getLogger("cotorreando").error("Unhandled exception", exc_info=exc)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    settings = Settings.load()
    if not settings.welcome_accepted:  # before anything is downloaded or recorded
        set_language(settings.ui_language)
        if not WelcomeDialog(settings).exec():
            return 0
    app._cotorreando = Cotorreando(app)  # noqa: SLF001 - keep it alive
    return app.exec()
