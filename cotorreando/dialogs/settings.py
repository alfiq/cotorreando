"""The settings dialog: the frame around its pages, and saving them."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ..i18n import tr
from ..keyboard import parse_hotkey
from ..mosaic import logo_pixmap
from .base import Window, footer_bar, ghost_button
from .privacy_actions import PrivacyActions
from .settings_pages import SettingsPages, page


class SettingsDialog(SettingsPages, Window):
    def __init__(self, settings, listener=None, learner=None, parent=None):
        super().__init__(parent)
        self.s, self.listener, self.learner = settings, listener, learner
        self.actions = PrivacyActions(self, learner, settings, self._show_password_state)
        self.calibrate_requested = False
        self.setWindowTitle("Cotorreando · " + tr("settings").rstrip("…"))
        self.resize(780, 560)

        self.pages = QStackedWidget()
        self.nav = QListWidget(objectName="sidebar")
        for title, content in (
            (tr("general"), self._general()),
            (tr("audio"), self._audio()),
            (tr("typing"), self._typing()),
            (tr("model"), self._model()),
            (tr("privacy"), self._privacy()),
        ):
            self.nav.addItem(title)
            self.pages.addWidget(page(title, content))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.addWidget(self.pages, 1)
        right.addWidget(self._footer())
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())
        layout.addLayout(right, 1)
        if listener:
            self._meter_timer = QTimer(self, interval=200, timeout=self._update_meter)
            self._meter_timer.start()

    def _sidebar(self) -> QWidget:
        """The logo above the list of pages."""
        logo = QLabel(objectName="sideLogo", alignment=Qt.AlignCenter)
        logo.setPixmap(logo_pixmap(4))
        side_widget = QWidget()
        side_widget.setFixedWidth(190)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)
        side.addWidget(logo)
        side.addWidget(self.nav, 1)
        return side_widget

    def _footer(self) -> QWidget:
        footer, bottom = footer_bar()
        bottom.addWidget(QLabel(tr("restart"), objectName="note"), 1)  # no wrapping: it sets the minimum width
        bottom.addWidget(ghost_button(tr("cancel"), clicked=self.reject))
        bottom.addWidget(QPushButton(tr("save"), clicked=self._accept, default=True))
        return footer

    def _import(self):
        """Applied settings close the dialog as if saved, so the app applies and stores them."""
        if self.actions.import_data():
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
        for apply in (
            self._apply_general,
            self._apply_audio,
            self._apply_typing,
            self._apply_model,
            self._apply_privacy,
        ):
            apply(self.s)
        self.accept()
