"""What the privacy page does with the vault: set or change the password, view, export and import."""

from __future__ import annotations

import logging
import time

from PySide6.QtWidgets import QFileDialog

from .. import transfer
from ..i18n import tr
from .base import inform
from .data import DataDialog
from .passwords import SetupDialog, UnlockDialog, _ChangePassword, _Export, _Import

log = logging.getLogger(__name__)


class PrivacyActions:
    """Each action opens its dialogs over ``window`` and leaves the vault locked again.

    ``password_set`` is called after the password has been created, so the page can update its button.
    """

    def __init__(self, window, learner, settings, password_set):
        self.window, self.learner, self.s = window, learner, settings
        self.password_set = password_set

    def unlock(self) -> bool:
        """True when the vault is open. Without a password yet, it offers to create one and says no."""
        vault = self.learner.vault
        if not vault.ready:
            SetupDialog(self.learner, self.window).exec()
            self.password_set()
            return False
        return not vault.locked or bool(UnlockDialog(self.learner, self.window).exec())

    def change_password(self) -> None:
        if not self.unlock():
            return
        dialog = _ChangePassword(self.learner.vault, self.window)
        dialog.exec()
        self.learner.vault.lock()

    def view_data(self) -> None:
        if self.unlock():
            DataDialog(self.learner, self.window).exec()
            self.learner.vault.lock()

    def export_data(self) -> None:
        if not self.unlock():
            return
        dialog = _Export(self.window)
        if dialog.exec():
            self._write_export(dialog)
        self.learner.vault.lock()

    def _write_export(self, dialog: _Export) -> None:
        name = f"cotorreando-{time.strftime('%Y%m%d')}.cotorreando"
        path, _ = QFileDialog.getSaveFileName(self.window, tr("export"), name, "Cotorreando (*.cotorreando)")
        if not path:
            return
        try:
            transfer.export(self.learner.vault, self.s, path, dialog.new.password(), dialog.dictations.isChecked())
            inform(self.window, tr("export_done"))
        except Exception:
            log.exception("Could not export")
            inform(self.window, tr("export_failed"))

    def import_data(self) -> bool:
        """True when the file's settings were applied: the caller then closes as if saved."""
        if not self.unlock():
            return False
        path, _ = QFileDialog.getOpenFileName(self.window, tr("import"), "", "Cotorreando (*.cotorreando)")
        dialog = _Import(path, self.window) if path else None
        applied = bool(dialog and dialog.exec() and self._merge(dialog))
        self.learner.vault.lock()
        return applied

    def _merge(self, dialog: _Import) -> bool:
        learner = self.learner
        applied = False
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
            inform(self.window, tr("import_done", words=words, corrections=corrections, records=records))
        except Exception:
            log.exception("Could not import")
            inform(self.window, tr("import_failed"))
        return applied
