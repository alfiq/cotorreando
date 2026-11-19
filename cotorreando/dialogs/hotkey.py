"""The field that records the hotkey."""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QLineEdit, QToolTip

from .. import keyboard
from ..i18n import tr
from ..keyboard import HotkeyRecorder, hotkey_label


class HotkeyEdit(QLineEdit):
    """Shows a hotkey and records a new one: click, press the combination, release.

    Recording polls the keys (see keyboard.down_keys) and pauses the real hotkey; it
    ends on its own, with Esc, or when the field loses focus or hides.
    """

    changed = Signal(str)

    def __init__(self, value: str):
        self.recorder = None  # set first: Qt may call event() during construction
        self._value, self._win_down = "", False
        self._esc_swallow, self._cancel_at = False, 0.0
        super().__init__(readOnly=True)
        self._timer = QTimer(self, interval=15, timeout=self._tick)
        self.setToolTip(tr("hotkey_hint"))
        self.setCursor(Qt.PointingHandCursor)
        self.setValue(value)

    def value(self) -> str:
        return self._value

    def setValue(self, text: str) -> None:
        self.stop()
        self._value = text.strip().lower()
        self.setText(hotkey_label(self._value))

    def recording(self) -> bool:
        return self.recorder is not None

    def start(self) -> None:
        if self.recording():
            return
        self.recorder, self._win_down = HotkeyRecorder(), False
        keyboard.hotkey_paused.set()
        self.setText(tr("hotkey_press"))
        self.setProperty("recording", True)
        self.style().polish(self)
        self._timer.start()

    def stop(self) -> None:
        """Ends the recording (if any) and always lets the real hotkey work again."""
        self._timer.stop()
        keyboard.hotkey_paused.clear()
        if self.recording():
            self.recorder = None
            self.setProperty("recording", False)
            self.style().polish(self)
            self.setText(hotkey_label(self._value))

    def _tick(self) -> None:
        down = keyboard.down_keys()
        win = bool(down & keyboard.WIN_VKS)
        if win and not self._win_down:
            keyboard.cancel_start_menu()  # releasing Win would open the Start menu
        self._win_down = win
        state = self.recorder.feed(down)
        if state == "live":
            self.setText(hotkey_label(self.recorder.text))
        elif state == "idle":
            self.setText(tr("hotkey_press"))
        elif state == "invalid":
            self.setText(tr("hotkey_press"))
            QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), tr("hotkey_invalid"), self)
        elif state == "cancel":
            self._cancel()
        elif state == "done":
            result = self.recorder.result
            self.setValue(result)
            self.changed.emit(result)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.start()

    def _cancel(self) -> None:
        """Esc ended the recording: its key events must not reach the dialog and close it."""
        self._esc_swallow, self._cancel_at = True, time.monotonic()
        self.stop()

    def _owns_escape(self, event) -> bool:
        if self.recording():
            return True
        if not self._esc_swallow:
            return False
        return event.isAutoRepeat() or time.monotonic() - self._cancel_at < 0.2

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._owns_escape(event):
            event.accept()
            if self.recording():
                self._cancel()
        elif self.recording():
            event.accept()  # Enter belongs to the recording, not to the dialog
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            event.accept()
            self.start()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        esc = event.key() == Qt.Key_Escape
        owned = esc and self._owns_escape(event)
        if esc and not event.isAutoRepeat():
            self._esc_swallow = False
        if self.recording() or owned:
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride:
            if self.recording() or (event.key() == Qt.Key_Escape and self._owns_escape(event)):
                event.accept()
                return True
        return super().event(event)

    def focusNextPrevChild(self, next_):
        return False if self.recording() else super().focusNextPrevChild(next_)

    def focusOutEvent(self, event):
        self.stop()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)
