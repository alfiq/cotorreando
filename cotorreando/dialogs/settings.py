"""Settings dialog and the hotkey field."""

from __future__ import annotations

import dataclasses
import logging
import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .. import (
    keyboard,
    languages,
    transfer,
)
from ..audio import list_microphones
from ..config import Settings
from ..i18n import tr
from ..keyboard import HotkeyRecorder, hotkey_label, parse_hotkey
from ..mosaic import logo_pixmap
from ..paths import MODELS_DIR
from .base import Prompt, Window, privacy_link
from .data import DataDialog
from .model import choose_model_folder
from .passwords import SetupDialog, UnlockDialog, _ChangePassword, _Export, _Import
from .welcome import LanguagesDialog

log = logging.getLogger(__name__)


def adapters() -> list[str]:
    root = MODELS_DIR / "adapters"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


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


class SettingsDialog(Window):
    def __init__(self, settings, listener=None, learner=None, parent=None):
        super().__init__(parent)
        self.s, self.listener, self.learner = settings, listener, learner
        self.calibrate_requested = False
        self.setWindowTitle("Cotorreando · " + tr("settings").rstrip("…"))
        self.resize(780, 560)

        self.pages = QStackedWidget()
        self.nav = QListWidget(objectName="sidebar")
        for title, page in (
            (tr("general"), self._general()),
            (tr("audio"), self._audio()),
            (tr("typing"), self._typing()),
            (tr("model"), self._model()),
            (tr("privacy"), self._privacy()),
        ):
            self.nav.addItem(title)
            self.pages.addWidget(self._page(title, page))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        logo = QLabel(objectName="sideLogo", alignment=Qt.AlignCenter)
        logo.setPixmap(logo_pixmap(4))
        side_widget = QWidget()
        side_widget.setFixedWidth(190)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        side.addWidget(logo)
        side.addWidget(self.nav, 1)

        note = QLabel(tr("restart"), objectName="note")
        cancel = QPushButton(tr("cancel"), objectName="ghost", clicked=self.reject)
        save = QPushButton(tr("save"), clicked=self._accept, default=True)
        footer = QFrame(objectName="footer")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(24, 12, 24, 12)
        bottom.addWidget(note, 1)
        bottom.addWidget(cancel)
        bottom.addWidget(save)
        right = QVBoxLayout()
        right.setSpacing(0)
        right.addWidget(self.pages, 1)
        right.addWidget(footer)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side_widget)
        layout.addLayout(right, 1)
        if listener:
            self._meter_timer = QTimer(self, interval=200, timeout=self._update_meter)
            self._meter_timer.start()

    @staticmethod
    def _combo(items, current):
        box = QComboBox()
        for value, label in items:
            box.addItem(label, value)
        box.setCurrentIndex(max(box.findData(current), 0))
        return box

    @staticmethod
    def _page(title, content):
        """A scrollable page: its title, then the groups in ``content``."""
        inner = QWidget(objectName="content")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(QLabel(title, objectName="pageTitle"))
        layout.addSpacing(8)
        layout.addWidget(content)
        layout.addStretch()
        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(inner)
        return scroll

    @staticmethod
    def _groups(*groups):
        """``groups``: (title or None, rows); a row is (label, widget) or a lone widget."""
        w = QWidget(objectName="content")
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        for title, rows in groups:
            if title:
                outer.addSpacing(8)
                outer.addWidget(QLabel(title.upper(), objectName="groupTitle"))
            card = QFrame(objectName="card")
            column = QVBoxLayout(card)
            column.setContentsMargins(16, 6, 16, 6)
            column.setSpacing(0)
            for i, row in enumerate(rows):
                if i:
                    column.addWidget(QFrame(objectName="rowLine"))
                line = QHBoxLayout()
                line.setContentsMargins(0, 8, 0, 8)
                if isinstance(row, tuple):
                    line.addWidget(QLabel(row[0], wordWrap=True), 1)
                    row[1].setMinimumWidth(220)
                    line.addWidget(row[1])
                else:
                    line.addWidget(row, 1)
                column.addLayout(line)
            outer.addWidget(card)
        return w

    def _general(self):
        self.language = self._combo([("es", "Español"), ("en", "English")], self.s.ui_language)
        self.mode = self._combo(
            [("open", tr("mode_open")), ("ptt", tr("mode_ptt")), ("activation", tr("mode_activation"))], self.s.mode
        )
        self.activation = self._combo([("voice", tr("act_voice")), ("keyword", tr("act_keyword"))], self.s.activation)
        self.keyword = QLineEdit(self.s.keyword)
        self.hotkey = HotkeyEdit(self.s.hotkey)
        reset = QPushButton(
            tr("hotkey_reset"), objectName="ghost", clicked=lambda: self.hotkey.setValue(Settings().hotkey)
        )
        hotkey_row = QWidget()
        line = QHBoxLayout(hotkey_row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.hotkey, 1)
        line.addWidget(reset)
        self.blob_size = self._combo([(k, tr(k)) for k in ("small", "medium", "large")], self.s.blob_size)
        # Edited on a copy, applied with the rest of the options: Cancel leaves them as they were.
        self.spoken_settings = dataclasses.replace(self.s, languages=list(self.s.languages))
        self.spoken_changed = False  # else accepting would undo a calibration choice made meanwhile
        self.spoken = QPushButton(objectName="ghost", clicked=self._choose_languages)
        self._show_languages()
        self.use_gpu = QCheckBox(tr("use_gpu"), checked=self.s.use_gpu)
        self.autostart = QCheckBox(tr("autostart"), checked=self.s.autostart)
        return self._groups(
            (
                tr("listening"),
                [
                    (tr("mode"), self.mode),
                    (tr("activation"), self.activation),
                    (tr("keyword"), self.keyword),
                    (tr("hotkey"), hotkey_row),
                    (tr("spoken_languages"), self.spoken),
                ],
            ),
            (
                tr("appearance"),
                [(tr("language"), self.language), (tr("blob_size"), self.blob_size)],
            ),
            (tr("system"), [self.use_gpu, self.autostart]),
        )

    def _show_languages(self) -> None:
        names = [languages.LANGUAGES[code][0] for code in self.spoken_settings.languages]
        self.spoken.setText(", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else ""))

    def _choose_languages(self) -> None:
        if LanguagesDialog(self.spoken_settings, self, required=False, save=False).exec():
            self.spoken_changed = True
            self._show_languages()

    def _audio(self):
        self.mic = self._combo([("", tr("default"))] + [(m, m) for m in list_microphones()], self.s.microphone)
        self.noise = QCheckBox(tr("noise"), checked=self.s.noise_suppression)
        self.echo = QCheckBox(tr("echo"), checked=self.s.echo_cancellation)
        self.agc = QCheckBox(tr("agc"), checked=self.s.auto_gain)
        self.auto = QCheckBox(tr("auto_threshold"), checked=self.s.auto_threshold)
        self.threshold = QDoubleSpinBox(minimum=-90, maximum=-5, value=self.s.energy_threshold_db)
        self.auto.toggled.connect(lambda on: self.threshold.setEnabled(not on))
        self.threshold.setEnabled(not self.s.auto_threshold)
        self.vad = QDoubleSpinBox(minimum=0.05, maximum=0.95, singleStep=0.05, value=self.s.vad_threshold)
        self.silence = QSpinBox(minimum=200, maximum=5000, singleStep=100, value=self.s.silence_ms)
        self.session = QDoubleSpinBox(minimum=1, maximum=120, value=self.s.session_timeout_s)
        self.meter = QLabel(objectName="note")
        calibrate = QPushButton(tr("calibrate"), objectName="ghost")
        calibrate.clicked.connect(lambda: self.listener and self.listener.calibrate())
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.meter, 1)
        line.addWidget(calibrate)
        return self._groups(
            (tr("capture"), [(tr("microphone"), self.mic), self.noise, self.echo, self.agc]),
            (
                tr("detection"),
                [
                    self.auto,
                    (tr("threshold"), self.threshold),
                    (tr("vad_threshold"), self.vad),
                    (tr("silence"), self.silence),
                    (tr("session"), self.session),
                    row,
                ],
            ),
        )

    def _typing(self):
        self.holdoff = QSpinBox(minimum=0, maximum=10000, singleStep=100, value=self.s.typing_holdoff_ms)
        self.trailing = QCheckBox(tr("trailing"), checked=self.s.trailing_space)
        self.streaming = QCheckBox(tr("streaming"), checked=self.s.streaming)
        return self._groups((None, [(tr("holdoff"), self.holdoff), self.trailing, self.streaming]))

    def _model(self):
        self.custom_model = self.s.custom_model
        self.model_label = QLabel(wordWrap=True)
        choose = QPushButton(tr("own_model_choose"), objectName="ghost", clicked=self._choose_model)
        self.stock_button = QPushButton(tr("use_stock_model"), objectName="ghost", clicked=lambda: self._set_model(""))
        own = QWidget()
        line = QHBoxLayout(own)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.model_label, 1)
        line.addWidget(self.stock_button)
        line.addWidget(choose)
        self._set_model(self.custom_model)
        own_help = QLabel(tr("own_model_help"), objectName="note", wordWrap=True)
        self.unload = QSpinBox(
            minimum=0,
            maximum=240,
            singleStep=5,
            value=min(self.s.model_unload_min, 240),
            specialValueText=tr("unload_never"),
        )
        unload_help = QLabel(tr("unload_help"), objectName="note", wordWrap=True)
        self.adapter = self._combo([("", tr("stock"))] + [(a, a) for a in adapters()], self.s.lora_adapter)
        self.boost = self._combo(
            [("auto", tr("boost_auto")), ("on", tr("boost_on")), ("off", tr("boost_off"))], self.s.boost_mode
        )
        boost_note = QLabel(tr("boost_note"), objectName="note", wordWrap=True)
        help_text = QLabel(tr("calibrate_help"), objectName="note", wordWrap=True)
        calibrate = QPushButton(tr("calibrate_voice"))
        calibrate.clicked.connect(self._calibrate)
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(16)
        line.addWidget(help_text, 1)
        line.addWidget(calibrate)
        return self._groups(
            (tr("own_model"), [own, own_help]),
            (None, [(tr("adapter"), self.adapter), row, (tr("boost"), self.boost), boost_note]),
            (None, [(tr("unload_after"), self.unload), unload_help]),
        )

    def _set_model(self, path: str) -> None:
        self.custom_model = path
        self.model_label.setText(path or tr("own_model_stock"))
        self.stock_button.setVisible(bool(path))

    def _choose_model(self):
        path = choose_model_folder(self, self.custom_model)
        if path:
            self._set_model(path)

    def _privacy(self):
        self.learning = QCheckBox(tr("learning"), checked=self.s.learning)
        self.excluded = QLineEdit(self.s.excluded_apps)
        self.retention = QSpinBox(minimum=1, maximum=3650, value=self.s.retention_days)
        note = QLabel(tr("privacy_note"), objectName="note", wordWrap=True)
        self.updates = QCheckBox(tr("check_updates"), checked=self.s.check_updates)
        updates_note = QLabel(tr("check_updates_note"), objectName="note", wordWrap=True)
        self.password = QPushButton(objectName="ghost", clicked=self._change_password)
        view = QPushButton(tr("data_view"), objectName="ghost", clicked=self._view_data)
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.password)
        line.addWidget(view)
        line.addWidget(QPushButton(tr("export"), objectName="ghost", clicked=self._export))
        line.addWidget(QPushButton(tr("import"), objectName="ghost", clicked=self._import))
        line.addStretch()
        self._show_password_state()
        return self._groups(
            (
                None,
                [
                    self.learning,
                    (tr("excluded"), self.excluded),
                    (tr("retention"), self.retention),
                    row,
                    note,
                    self.updates,
                    updates_note,
                    privacy_link(),
                ],
            )
        )

    def _show_password_state(self):
        self.password.setText(tr("password_change") if self.learner.vault.ready else tr("password_set"))

    def _unlock(self) -> bool:
        vault = self.learner.vault
        if not vault.ready:
            SetupDialog(self.learner, self).exec()
            self._show_password_state()
            return False
        return not vault.locked or bool(UnlockDialog(self.learner, self).exec())

    def _change_password(self):
        if not self._unlock():
            return
        dialog = _ChangePassword(self.learner.vault, self)
        dialog.exec()
        self.learner.vault.lock()

    def _view_data(self):
        if self._unlock():
            DataDialog(self.learner, self).exec()
            self.learner.vault.lock()

    def _export(self):
        if not self._unlock():
            return
        dialog = _Export(self)
        if dialog.exec():
            name = f"cotorreando-{time.strftime('%Y%m%d')}.cotorreando"
            path, _ = QFileDialog.getSaveFileName(self, tr("export"), name, "Cotorreando (*.cotorreando)")
            if path:
                try:
                    transfer.export(
                        self.learner.vault, self.s, path, dialog.new.password(), dialog.dictations.isChecked()
                    )
                    Prompt(self, tr("export_done"), cancel=False).exec()
                except Exception:
                    log.exception("Could not export")
                    Prompt(self, tr("export_failed"), cancel=False).exec()
        self.learner.vault.lock()

    def _import(self):
        """Applied settings close the dialog as if saved, so the app applies and stores them."""
        if not self._unlock():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("import"), "", "Cotorreando (*.cotorreando)")
        dialog = _Import(path, self) if path else None
        applied = False
        if dialog and dialog.exec():
            learner = self.learner
            try:
                words, corrections, records = transfer.merge(
                    learner.vault, dialog.head, dialog.audio, dialog.mode.currentData()
                )
                if learner.loaded:
                    learner.hard = learner.vault.load_private("hard_words", {})
                    learner.counts = learner.vault.load_private("corrections", {})
                    learner.custom = learner.vault.load_private("custom_words", [])
                if dialog.settings.isChecked():
                    transfer.apply_settings(self.s, dialog.head)
                    applied = True
                Prompt(
                    self, tr("import_done", words=words, corrections=corrections, records=records), cancel=False
                ).exec()
            except Exception:
                log.exception("Could not import")
                Prompt(self, tr("import_failed"), cancel=False).exec()
        self.learner.vault.lock()
        if applied:
            self.accept()

    def _calibrate(self):
        self.calibrate_requested = True
        self.reject()

    def _update_meter(self):
        lvl = getattr(self.listener, "last_level", -90.0)
        self.meter.setText(tr("level", lvl=lvl, thr=self.listener.threshold_db))

    def done(self, result):
        self.hotkey.stop()  # the real hotkey must never stay paused
        super().done(result)

    def _accept(self):
        self.hotkey.stop()
        try:
            parse_hotkey(self.hotkey.value())
        except ValueError:
            self.hotkey.setFocus()
            return
        s = self.s
        if self.spoken_changed:
            s.languages, s.lora_language = self.spoken_settings.languages, self.spoken_settings.lora_language
        s.ui_language, s.mode, s.activation = (
            self.language.currentData(),
            self.mode.currentData(),
            self.activation.currentData(),
        )
        s.keyword, s.hotkey = self.keyword.text().strip().lower(), self.hotkey.value()
        s.use_gpu, s.autostart = self.use_gpu.isChecked(), self.autostart.isChecked()
        s.blob_size = self.blob_size.currentData()
        s.microphone = self.mic.currentData()
        s.noise_suppression, s.echo_cancellation, s.auto_gain = (
            self.noise.isChecked(),
            self.echo.isChecked(),
            self.agc.isChecked(),
        )
        s.auto_threshold, s.energy_threshold_db = self.auto.isChecked(), self.threshold.value()
        s.vad_threshold, s.silence_ms, s.session_timeout_s = (
            self.vad.value(),
            self.silence.value(),
            self.session.value(),
        )
        s.typing_holdoff_ms, s.trailing_space = self.holdoff.value(), self.trailing.isChecked()
        s.streaming = self.streaming.isChecked()
        s.lora_adapter = self.adapter.currentData()
        s.custom_model = self.custom_model
        s.model_unload_min = self.unload.value()
        s.boost_mode = self.boost.currentData()
        s.learning, s.excluded_apps = self.learning.isChecked(), self.excluded.text().strip()
        s.retention_days = self.retention.value()
        s.check_updates = self.updates.isChecked()
        self.accept()
