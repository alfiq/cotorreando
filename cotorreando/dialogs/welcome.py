"""First-run, languages and About dialogs."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .. import (
    AUTHOR_URL,
    REPO_URL,
    __author__,
    __version__,
    languages,
    palette,
)
from ..credits import CREDITS, TRAINING_CREDITS
from ..i18n import tr
from .base import Window, privacy_link

log = logging.getLogger(__name__)


class WelcomeDialog(Window):
    """First-run notice: what stays on this PC, what is saved, and the learning switch."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle(tr("welcome_title"))
        self.setFixedWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(QLabel(tr("welcome_text"), wordWrap=True))
        layout.addWidget(privacy_link())
        self.learning = QCheckBox(tr("welcome_learning"), checked=settings.learning)
        layout.addWidget(self.learning)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(QPushButton(tr("welcome_exit"), objectName="ghost", clicked=self.reject))
        buttons.addWidget(QPushButton(tr("welcome_accept"), clicked=self.accept, default=True))
        layout.addLayout(buttons)

    def accept(self):
        self.s.learning = self.learning.isChecked()
        self.s.welcome_accepted = True
        self.s.save()
        super().accept()


class LanguagesDialog(Window):
    """First run: which of the model's languages the user speaks, with the PC's own first."""

    def __init__(self, settings, parent=None, detected=None, required=True, save=True):
        super().__init__(parent)
        self.s, self.persist = settings, save
        self.required = required  # at startup: closing it accepts; from the options it cancels
        self.setWindowTitle(tr("langs_title"))
        self.setFixedWidth(420)
        detected = languages.system_languages() if detected is None else detected
        chosen = set(settings.languages or detected or [settings.ui_language])
        ui = settings.ui_language
        rest = sorted((c for c in languages.LANGUAGES if c not in detected), key=lambda c: languages.label(c, ui))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel(tr("langs_text"), wordWrap=True))
        self.search = QLineEdit(placeholderText=tr("langs_search"), clearButtonEnabled=True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumHeight(280)
        for code in [*detected, *rest]:
            item = QListWidgetItem(languages.label(code, ui))
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)  # a click toggles it once, below
            item.setCheckState(Qt.Checked if code in chosen else Qt.Unchecked)
            self.list.addItem(item)
        # Not user-checkable: Qt would flip a click on the box and itemClicked would flip it back.
        self.list.itemClicked.connect(self._toggle)
        self.list.installEventFilter(self)  # and the space bar, which itemClicked does not cover
        layout.addWidget(self.list)
        self.warning = QLabel(tr("langs_none"), objectName="note", visible=False)
        layout.addWidget(self.warning)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(QPushButton(tr("welcome_accept"), clicked=self.accept, default=True))
        layout.addLayout(buttons)

    def _toggle(self, item) -> None:
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.list and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            item = self.list.currentItem()
            if item is not None and not item.isHidden():
                self._toggle(item)
                return True
        return super().eventFilter(watched, event)

    def _filter(self, query: str) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(not languages.matches(item.data(Qt.UserRole), query))

    def chosen(self) -> list[str]:
        items = (self.list.item(row) for row in range(self.list.count()))
        return [item.data(Qt.UserRole) for item in items if item.checkState() == Qt.Checked]

    def accept(self):
        codes = self.chosen()
        if not codes:
            self.warning.show()
            return
        self.s.languages = codes
        # Keep a calibration choice that still fits. A new one reads every chosen language if there
        # are one or two (3-6 minutes), or else just the first: reading eight would take 24.
        old = self.s.lora_language
        if not (old in codes or (old == "both" and {"es", "en"} <= set(codes))):
            self.s.lora_language = "all" if len(codes) <= 2 else codes[0]
        if self.persist:
            self.s.save()
        super().accept()

    def reject(self):
        """At startup, closing it keeps what is ticked, or the interface language: the app must not
        stay shut. Opened from the options, it just cancels."""
        if not self.required:
            super().reject()
            return
        if not self.chosen():
            for row in range(self.list.count()):
                item = self.list.item(row)
                if item.data(Qt.UserRole) == self.s.ui_language:
                    item.setCheckState(Qt.Checked)
        self.accept()


class AboutDialog(Window):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.resize(560, 520)
        rows = "".join(
            f"<p><b><a href='{url}'>{name}</a></b> — {purpose}<br>"
            f"<a href='{lic_url}'>{lic}</a> · <span style='color:{palette.MUTED}'>{note}</span></p>"
            for name, purpose, lic, url, lic_url, note in CREDITS + TRAINING_CREDITS
        )
        html = (
            f"<h2>Cotorreando {__version__}</h2><p>{tr('tagline')}</p>"
            f"<p>{tr('author')}: <b>{__author__}</b> · <a href='{AUTHOR_URL}'>{AUTHOR_URL}</a><br>"
            f"Repo: <a href='{REPO_URL}'>{REPO_URL}</a> · MIT<br>"
            f"<a href='{tr('privacy_url')}'>{tr('privacy_link')}</a></p>"
            f"<h3>{tr('credits')}</h3>{rows}"
        )
        text = QTextBrowser(openExternalLinks=True)
        text.setHtml(html)
        close = QHBoxLayout()
        close.addStretch()
        close.addWidget(QPushButton(tr("cal_finish"), clicked=self.accept))
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addLayout(close)
