"""The pages of the settings dialog: each builds its controls and, later, reads them back."""

from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import languages
from ..audio import list_microphones
from ..config import Settings
from ..i18n import tr
from ..paths import MODELS_DIR
from .base import ghost_button, inline_row, note_label, privacy_link, scroll_area
from .hotkey import HotkeyEdit
from .model import choose_model_folder
from .welcome import LanguagesDialog


def adapters() -> list[str]:
    root = MODELS_DIR / "adapters"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


def combo(items, current) -> QComboBox:
    """A drop-down of ``(value, label)``; the value is what ``currentData()`` gives back."""
    box = QComboBox()
    for value, label in items:
        box.addItem(label, value)
    box.setCurrentIndex(max(box.findData(current), 0))
    return box


def page(title: str, content: QWidget) -> QWidget:
    """A scrollable page: its title, then the groups in ``content``."""
    inner = QWidget(objectName="content")
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(28, 24, 28, 24)
    layout.setSpacing(10)
    layout.addWidget(QLabel(title, objectName="pageTitle"))
    layout.addSpacing(8)
    layout.addWidget(content)
    layout.addStretch()
    return scroll_area(inner)


def groups(*groups) -> QWidget:
    """``groups``: (title or None, rows); a row is (label, widget) or a lone widget."""
    w = QWidget(objectName="content")
    outer = QVBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(8)
    for title, rows in groups:
        if title:
            outer.addSpacing(8)
            outer.addWidget(QLabel(title.upper(), objectName="groupTitle"))
        outer.addWidget(_card(rows))
    return w


def _card(rows) -> QFrame:
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
    return card


class SettingsPages:
    """The pages of SettingsDialog, as a mixin: the controls stay attributes of the dialog.

    The dialog provides ``s`` (the settings), ``listener``, ``actions`` (PrivacyActions) and the
    handlers ``_calibrate`` and ``_import``.
    """

    # General

    def _general(self):
        self._general_controls()
        return groups(
            (
                tr("listening"),
                [
                    (tr("mode"), self.mode),
                    (tr("activation"), self.activation),
                    (tr("keyword"), self.keyword),
                    (tr("hotkey"), self._hotkey_row()),
                    (tr("spoken_languages"), self.spoken),
                ],
            ),
            (
                tr("appearance"),
                [(tr("language"), self.language), (tr("blob_size"), self.blob_size)],
            ),
            (tr("system"), [self.use_gpu, self.autostart]),
        )

    def _general_controls(self) -> None:
        self.language = combo([("es", "Español"), ("en", "English")], self.s.ui_language)
        self.mode = combo(
            [("open", tr("mode_open")), ("ptt", tr("mode_ptt")), ("activation", tr("mode_activation"))], self.s.mode
        )
        self.activation = combo([("voice", tr("act_voice")), ("keyword", tr("act_keyword"))], self.s.activation)
        self.keyword = QLineEdit(self.s.keyword)
        self.hotkey = HotkeyEdit(self.s.hotkey)
        self.blob_size = combo([(k, tr(k)) for k in ("small", "medium", "large")], self.s.blob_size)
        # Edited on a copy, applied with the rest of the options: Cancel leaves them as they were.
        self.spoken_settings = dataclasses.replace(self.s, languages=list(self.s.languages))
        self.spoken_changed = False  # else accepting would undo a calibration choice made meanwhile
        self.spoken = QPushButton(objectName="ghost", clicked=self._choose_languages)
        self._show_languages()
        self.use_gpu = QCheckBox(tr("use_gpu"), checked=self.s.use_gpu)
        self.autostart = QCheckBox(tr("autostart"), checked=self.s.autostart)

    def _hotkey_row(self) -> QWidget:
        reset = ghost_button(tr("hotkey_reset"), clicked=lambda: self.hotkey.setValue(Settings().hotkey))
        return inline_row((self.hotkey, 1), reset)

    def _show_languages(self) -> None:
        names = [languages.LANGUAGES[code][0] for code in self.spoken_settings.languages]
        self.spoken.setText(", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else ""))

    def _choose_languages(self) -> None:
        if LanguagesDialog(self.spoken_settings, self, required=False, save=False).exec():
            self.spoken_changed = True
            self._show_languages()

    def _apply_general(self, s: Settings) -> None:
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

    # Audio

    def _audio(self):
        self.mic = combo([("", tr("default"))] + [(m, m) for m in list_microphones()], self.s.microphone)
        self.noise = QCheckBox(tr("noise"), checked=self.s.noise_suppression)
        self.echo = QCheckBox(tr("echo"), checked=self.s.echo_cancellation)
        self.agc = QCheckBox(tr("agc"), checked=self.s.auto_gain)
        self._detection_controls()
        return groups(
            (tr("capture"), [(tr("microphone"), self.mic), self.noise, self.echo, self.agc]),
            (
                tr("detection"),
                [
                    self.auto,
                    (tr("threshold"), self.threshold),
                    (tr("vad_threshold"), self.vad),
                    (tr("silence"), self.silence),
                    (tr("session"), self.session),
                    self._meter_row(),
                ],
            ),
        )

    def _detection_controls(self) -> None:
        self.auto = QCheckBox(tr("auto_threshold"), checked=self.s.auto_threshold)
        self.threshold = QDoubleSpinBox(minimum=-90, maximum=-5, value=self.s.energy_threshold_db)
        self.auto.toggled.connect(lambda on: self.threshold.setEnabled(not on))
        self.threshold.setEnabled(not self.s.auto_threshold)
        self.vad = QDoubleSpinBox(minimum=0.05, maximum=0.95, singleStep=0.05, value=self.s.vad_threshold)
        self.silence = QSpinBox(minimum=200, maximum=5000, singleStep=100, value=self.s.silence_ms)
        self.session = QDoubleSpinBox(minimum=1, maximum=120, value=self.s.session_timeout_s)

    def _meter_row(self) -> QWidget:
        """The live level, and the button that measures the room."""
        self.meter = QLabel(objectName="note")
        calibrate = ghost_button(tr("calibrate"))
        calibrate.clicked.connect(lambda: self.listener and self.listener.calibrate())
        return inline_row((self.meter, 1), calibrate)

    def _apply_audio(self, s: Settings) -> None:
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

    # Typing

    def _typing(self):
        self.holdoff = QSpinBox(minimum=0, maximum=10000, singleStep=100, value=self.s.typing_holdoff_ms)
        self.trailing = QCheckBox(tr("trailing"), checked=self.s.trailing_space)
        self.streaming = QCheckBox(tr("streaming"), checked=self.s.streaming)
        return groups((None, [(tr("holdoff"), self.holdoff), self.trailing, self.streaming]))

    def _apply_typing(self, s: Settings) -> None:
        s.typing_holdoff_ms, s.trailing_space = self.holdoff.value(), self.trailing.isChecked()
        s.streaming = self.streaming.isChecked()

    # Model

    def _model(self):
        own, own_help = self._own_model_rows()
        self.unload = QSpinBox(
            minimum=0,
            maximum=240,
            singleStep=5,
            value=min(self.s.model_unload_min, 240),
            specialValueText=tr("unload_never"),
        )
        unload_help = note_label(tr("unload_help"))
        self.adapter = combo([("", tr("stock"))] + [(a, a) for a in adapters()], self.s.lora_adapter)
        self.boost = combo(
            [("auto", tr("boost_auto")), ("on", tr("boost_on")), ("off", tr("boost_off"))], self.s.boost_mode
        )
        boost_note = note_label(tr("boost_note"))
        return groups(
            (tr("own_model"), [own, own_help]),
            (None, [(tr("adapter"), self.adapter), self._calibrate_row(), (tr("boost"), self.boost), boost_note]),
            (None, [(tr("unload_after"), self.unload), unload_help]),
        )

    def _own_model_rows(self) -> tuple[QWidget, QLabel]:
        """The folder of the user's own model, with its buttons, and the note under it."""
        self.custom_model = self.s.custom_model
        self.model_label = QLabel(wordWrap=True)
        choose = ghost_button(tr("own_model_choose"), clicked=self._choose_model)
        self.stock_button = ghost_button(tr("use_stock_model"), clicked=lambda: self._set_model(""))
        own = inline_row((self.model_label, 1), self.stock_button, choose)
        self._set_model(self.custom_model)
        return own, note_label(tr("own_model_help"))

    def _calibrate_row(self) -> QWidget:
        calibrate = QPushButton(tr("calibrate_voice"))
        calibrate.clicked.connect(self._calibrate)
        return inline_row((note_label(tr("calibrate_help")), 1), calibrate, spacing=16)

    def _set_model(self, path: str) -> None:
        self.custom_model = path
        self.model_label.setText(path or tr("own_model_stock"))
        self.stock_button.setVisible(bool(path))

    def _choose_model(self):
        path = choose_model_folder(self, self.custom_model)
        if path:
            self._set_model(path)

    def _apply_model(self, s: Settings) -> None:
        s.lora_adapter = self.adapter.currentData()
        s.custom_model = self.custom_model
        s.model_unload_min = self.unload.value()
        s.boost_mode = self.boost.currentData()

    # Privacy

    def _privacy(self):
        self.learning = QCheckBox(tr("learning"), checked=self.s.learning)
        self.excluded = QLineEdit(self.s.excluded_apps)
        self.retention = QSpinBox(minimum=1, maximum=3650, value=self.s.retention_days)
        note = note_label(tr("privacy_note"))
        self.updates = QCheckBox(tr("check_updates"), checked=self.s.check_updates)
        updates_note = note_label(tr("check_updates_note"))
        row = self._vault_buttons()
        self._show_password_state()
        return groups(
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

    def _vault_buttons(self) -> QWidget:
        """Password, view, export and import: what can be done with what the app keeps."""
        actions = self.actions
        self.password = ghost_button("", clicked=actions.change_password)
        return inline_row(
            self.password,
            ghost_button(tr("data_view"), clicked=actions.view_data),
            ghost_button(tr("export"), clicked=actions.export_data),
            ghost_button(tr("import"), clicked=self._import),
            trailing_stretch=True,
        )

    def _show_password_state(self) -> None:
        self.password.setText(tr("password_change") if self.learner.vault.ready else tr("password_set"))

    def _apply_privacy(self, s: Settings) -> None:
        s.learning, s.excluded_apps = self.learning.isChecked(), self.excluded.text().strip()
        s.retention_days = self.retention.value()
        s.check_updates = self.updates.isChecked()
