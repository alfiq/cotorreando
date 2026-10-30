"""Wires everything together: audio -> listener -> recognizer -> keyboard, plus the UI.

Threads
-------
mic / loopback   capture and WebRTC processing (audio.py)
keyboard         low-level hook (keyboard.py)
recognizer       Parakeet inference and typing (this file)
Qt main thread   blob, tray, menus and dialogs; other threads talk to it via signals.
"""

from __future__ import annotations

import ctypes
import difflib
import logging
import queue
import sys
import threading
import time
import unicodedata
import winreg

import numpy as np

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import asr
from .audio import AudioInput
from .blob import Blob
from .config import Settings
from .dialogs import STYLE, AboutDialog, SettingsDialog, styled_menu
from .i18n import set_language, tr
from .keyboard import KeyboardMonitor, foreground, replace_text, type_text
from .listener import Listener
from .paths import DATA_DIR, MODELS_DIR

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if c.isalnum() or c.isspace())
    return " ".join(text.split())


def after_keyword(text: str, keyword: str) -> str | None:
    """Fuzzy-find ``keyword`` in ``text``; return what follows it, or None."""
    words, key = text.split(), normalize(keyword)
    n = len(key.split())
    for i in range(len(words) - n + 1):
        window = normalize(" ".join(words[i:i + n]))
        if difflib.SequenceMatcher(None, window, key).ratio() >= 0.75:
            return " ".join(words[i + n:]).lstrip(",.;: ")
    return None


class Cotorreando(QObject):
    level = Signal(float, float, bool)
    writing = Signal(bool)
    status = Signal(str)
    loaded = Signal()
    toggle_requested = Signal()
    warning = Signal(str)
    loading = Signal(float)   # -1 = busy, 0..1 = download progress

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.s = Settings.load()
        set_language(self.s.ui_language)
        self.enabled = True
        self.model: asr.Parakeet | None = None
        self.audio: AudioInput | None = None
        self.listener: Listener | None = None
        self.jobs: queue.Queue = queue.Queue()
        self._silent_frames = -1

        self.blob = Blob(self.s.blob_size)
        self.blob.place(self.s.blob_x, self.s.blob_y)
        self.blob.moved.connect(self._remember_position)
        self.blob.menu_requested.connect(self._show_menu)
        self.level.connect(self.blob.set_level)
        self.writing.connect(self.blob.set_writing)
        self.loaded.connect(self.start_audio)
        self.loading.connect(lambda v: self.blob.set_loading(None if v < -1 else v))
        self.toggle_requested.connect(self.toggle_enabled)

        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Cotorreando")
        self.tray.activated.connect(self._tray_activated)
        self.status.connect(lambda text: self.tray.setToolTip(f"Cotorreando · {text}"))
        self.menu = styled_menu()
        self.menu.aboutToShow.connect(self._build_menu)
        self.tray.setContextMenu(self.menu)
        self.warning.connect(lambda text: self.tray.showMessage(
            "Cotorreando", text, QSystemTrayIcon.MessageIcon.Warning))
        self.tray.show()

        self.keyboard = KeyboardMonitor(self.s.hotkey, self._hotkey_down, self._hotkey_up)
        self.keyboard.start()
        threading.Thread(target=self._recognizer, daemon=True, name="recognizer").start()

        if not self.s.hidden:
            self.blob.show()
        self.blob.set_enabled(False)   # grey until the model is loaded
        threading.Thread(target=self._load_model, daemon=True).start()

    # -- model & audio --------------------------------------------------------

    def _model_dir(self):
        path = MODELS_DIR / "adapters" / self.s.lora_adapter
        return path if self.s.lora_adapter and path.exists() else asr.model_dir()

    def _load_model(self) -> None:
        self.status.emit(tr("loading"))
        self.loading.emit(-1)
        try:
            if not asr.is_downloaded():
                asr.download(self._download_progress)
                self.loading.emit(-1)
            try:
                self.model = asr.Parakeet(self._model_dir(), use_gpu=self.s.use_gpu)
            except Exception:
                if not self.s.use_gpu:
                    raise
                log.exception("GPU model load failed; retrying on the CPU")
                self.model = asr.Parakeet(self._model_dir(), use_gpu=False)
        except Exception as err:
            log.exception("Model load failed")
            self.status.emit(tr("load_failed", error=err))
            self.warning.emit(tr("load_failed", error=err))
            self.loading.emit(-2)
            return
        log.info("Model loaded (%s)", "GPU" if self.model.on_gpu else "CPU")
        self.status.emit(tr("ready"))
        self.loading.emit(-2)
        self.loaded.emit()

    def _download_progress(self, done: int, total: int) -> None:
        self.status.emit(tr("downloading", pct=done * 100 // max(total, 1)))
        if total:
            self.loading.emit(done / total)

    def start_audio(self) -> None:
        self.stop_audio()
        if not self.enabled or self.model is None:
            log.info("Not listening (enabled=%s, model=%s)", self.enabled, self.model is not None)
            return
        self.listener = Listener(self.s, lambda uid, audio: self.jobs.put(("audio", uid, audio)),
                                 lambda uid: self.jobs.put(("end", uid, None)), self.level.emit)
        self.audio = AudioInput(self._on_frame, self.s.microphone, self.s.noise_suppression,
                                self.s.echo_cancellation, self.s.auto_gain)
        self._silent_frames = 0
        log.info("Listening on %s (mode %s)", self.s.microphone or "default microphone", self.s.mode)
        self.audio.start()
        self.blob.set_enabled(True)

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
            if self._silent_frames == 300:   # 3 s
                log.warning("Microphone delivers only silence")
                self.warning.emit(tr("mic_silent"))
                self._silent_frames = -1
        holdoff = self.s.typing_holdoff_ms / 1000
        if time.monotonic() - self.keyboard.last_typed < holdoff:
            listener.pause_for_typing(holdoff)
        listener.feed(frame)

    def _recognizer(self) -> None:
        """Consume listener events; stream text out as soon as it is final."""
        uid, stream, buffered, cancelled = 0, None, [], False
        while True:
            kind, job_uid, audio = self.jobs.get()
            if self.model is None or not self.enabled:
                continue
            if job_uid != uid:                  # a new utterance (an unfinished one was cancelled)
                uid, buffered, cancelled = job_uid, [], False
                stream = asr.Stream(self.model) if self._should_stream() else None
                self._tail, self._tail_since, self._tail_window = "", time.monotonic(), foreground()
            if time.monotonic() - self.keyboard.last_typed < self.s.typing_holdoff_ms / 1000:
                cancelled = True                # you are typing; never write over it
            if cancelled:
                continue
            try:
                if kind == "audio":
                    if stream:
                        self._rewrite(stream.feed(audio), stream.tail)
                    else:
                        buffered.append(audio)
                elif stream:
                    self._rewrite(stream.finish(), "", end=True)
                elif buffered:
                    text = self.model.transcribe(np.concatenate(buffered))
                    self._type(self._apply_activation(text), end=True)
            except Exception:
                log.exception("Transcription failed")

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
            self.listener.wake()                # keyword mode: keep the session alive
        if end and text.strip() and self.s.trailing_space:
            text = text.rstrip() + " "
        old, self._tail = self._tail, tail
        if text + tail == old:                  # what was tentative may just have become final
            return
        self.writing.emit(True)
        replace_text(old, text + tail)
        self.writing.emit(False)

    def _type(self, text: str, end: bool = False) -> None:
        if text and self.listener and self.listener.awake:
            self.listener.wake()                # keyword mode: keep the session alive
        if end and text.strip() and self.s.trailing_space:
            text = text.rstrip() + " "
        if not text:
            return
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
        if self.enabled and self.model is None:   # an earlier load failed: try again
            threading.Thread(target=self._load_model, daemon=True).start()
        self.blob.set_enabled(self.enabled)
        self.start_audio() if self.enabled else self.stop_audio()
        self.tray.setIcon(self._tray_icon())
        self.status.emit(tr("ready") if self.enabled else tr("disabled"))

    def toggle_hidden(self) -> None:
        self.s.hidden = not self.s.hidden
        self.blob.setVisible(not self.s.hidden)
        self.s.save()

    def open_settings(self) -> None:
        old = (self.s.use_gpu, self.s.lora_adapter)
        dialog = SettingsDialog(self.s, self.listener)
        if not dialog.exec():
            return
        set_language(self.s.ui_language)
        self.keyboard.set_hotkey(self.s.hotkey)
        self.blob.set_size(self.s.blob_size)
        set_autostart(self.s.autostart)
        self.s.save()
        if (self.s.use_gpu, self.s.lora_adapter) != old:
            self.stop_audio()
            threading.Thread(target=self._load_model, daemon=True).start()
        else:
            self.start_audio()

    def open_training(self) -> None:
        from .lora.ui import TrainingDialog, confirm_dependencies   # rarely used, load lazily
        if not confirm_dependencies():
            return
        was_enabled, adapter = self.enabled, self.s.lora_adapter
        if was_enabled:
            self.toggle_enabled()       # free the microphone while recording
        TrainingDialog(self.s).exec()
        self.s.save()
        if self.s.lora_adapter != adapter:
            self.enabled = was_enabled
            threading.Thread(target=self._load_model, daemon=True).start()
        elif was_enabled:
            self.toggle_enabled()

    def open_about(self) -> None:
        AboutDialog().exec()

    def quit(self) -> None:
        self.stop_audio()
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
        p.setBrush(QColor(64, 196, 255) if self.enabled else QColor(128, 128, 134))
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(DATA_DIR / "cotorreando.log", mode="w", encoding="utf-8")]
    if sys.stderr is not None:   # the windowed build has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s",
                        handlers=handlers)
    # Without a console, exceptions raised in Qt slots would vanish.
    sys.excepthook = lambda *exc: logging.getLogger("cotorreando").error(
        "Unhandled exception", exc_info=exc)
    if already_running():
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    app._cotorreando = Cotorreando(app)  # noqa: SLF001 - keep it alive
    return app.exec()
