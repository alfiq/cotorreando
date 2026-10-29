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

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import asr
from .audio import AudioInput
from .blob import Blob
from .config import Settings
from .dialogs import STYLE, AboutDialog, SettingsDialog, styled_menu
from .i18n import set_language, tr
from .keyboard import KeyboardMonitor, type_text
from .listener import Listener
from .paths import MODELS_DIR

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

        self.blob = Blob()
        self.blob.place(self.s.blob_x, self.s.blob_y)
        self.blob.moved.connect(self._remember_position)
        self.blob.menu_requested.connect(self._show_menu)
        self.level.connect(self.blob.set_level)
        self.writing.connect(self.blob.set_writing)
        self.loaded.connect(self.start_audio)
        self.toggle_requested.connect(self.toggle_enabled)

        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Cotorreando")
        self.tray.activated.connect(self._tray_activated)
        self.status.connect(lambda text: self.tray.setToolTip(f"Cotorreando · {text}"))
        self.menu = styled_menu()
        self.menu.aboutToShow.connect(self._build_menu)
        self.tray.setContextMenu(self.menu)
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
        if not asr.is_downloaded():
            asr.download(lambda d, t: self.status.emit(tr("downloading", pct=d * 100 // max(t, 1))))
        self.model = asr.Parakeet(self._model_dir(), use_gpu=self.s.use_gpu)
        self.status.emit(tr("ready"))
        self.loaded.emit()

    def start_audio(self) -> None:
        self.stop_audio()
        if not self.enabled or self.model is None:
            return
        self.listener = Listener(self.s, self.jobs.put, self.level.emit)
        self.audio = AudioInput(self._on_frame, self.s.microphone, self.s.noise_suppression,
                                self.s.echo_cancellation, self.s.auto_gain)
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
        holdoff = self.s.typing_holdoff_ms / 1000
        if time.monotonic() - self.keyboard.last_typed < holdoff:
            listener.pause_for_typing(holdoff)
        listener.feed(frame)

    def _recognizer(self) -> None:
        while True:
            audio = self.jobs.get()
            if self.model is None or not self.enabled:
                continue
            try:
                text = self.model.transcribe(audio)
            except Exception:
                log.exception("Transcription failed")
                continue
            text = self._apply_activation(text)
            if not text:
                continue
            self.writing.emit(True)
            type_text(text + (" " if self.s.trailing_space else ""))
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    if already_running():
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    app._cotorreando = Cotorreando(app)  # noqa: SLF001 - keep it alive
    return app.exec()
