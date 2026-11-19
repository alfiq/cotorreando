"""Password dialogs: set up, unlock, recover, change, export and import."""

from __future__ import annotations

import logging
import secrets

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import transfer, vault_legacy
from ..i18n import tr
from ..vault import WrongPassword, password_problem
from .base import Prompt, Window, button_row, dialog_layout, ghost_button, note_label

log = logging.getLogger(__name__)

MAX_FAILURES, COOLDOWN_S = 5, 60  # wrong passwords in a row, then this many seconds of waiting


class NewPassword(QWidget):
    """Two fields for a new password, plus one that makes up a strong one to save in a manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.first = QLineEdit(echoMode=QLineEdit.Password, placeholderText=tr("password_new_hint"))
        self.second = QLineEdit(echoMode=QLineEdit.Password, placeholderText=tr("password_again"))
        generate = ghost_button(tr("password_generate"), clicked=self._generate)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.first)
        layout.addWidget(self.second)
        layout.addWidget(generate, 0, Qt.AlignLeft)

    def _generate(self):
        password = secrets.token_urlsafe(18)
        self.first.setEchoMode(QLineEdit.Normal)
        self.first.setText(password)
        self.second.setText(password)
        self.first.selectAll()
        self.first.setFocus()

    def problem(self) -> str | None:
        if self.first.text() != self.second.text():
            return tr("password_mismatch")
        problem = password_problem(self.first.text())
        return tr(problem) if problem else None

    def password(self) -> str:
        return self.first.text()


class _Form(Window):
    """Text, a body and buttons; ``_submit`` decides whether the dialog is done."""

    new: NewPassword  # the dialogs that ask for a new password set it; see _new_password_ok

    def __init__(self, parent, text, ok):
        super().__init__(parent)
        self.setWindowTitle(tr("password_prompt"))
        self.setFixedWidth(460)
        self.body = dialog_layout(self, spacing=12)
        self.body.addWidget(QLabel(text, wordWrap=True))
        self.error = note_label("")
        self.error.hide()
        self.ok = QPushButton(ok, clicked=self._submit, default=True)
        self.buttons = button_row(ghost_button(tr("cancel"), clicked=self.reject), self.ok)

    def _finish_layout(self):
        self.body.addWidget(self.error)
        self.body.addLayout(self.buttons)

    def _show_error(self, text):
        self.error.setText(text)
        self.error.show()

    def _new_password_ok(self) -> bool:
        """Whether the new password in ``self.new`` is acceptable; if not, says why."""
        problem = self.new.problem()
        if problem:
            self._show_error(problem)
        return not problem


def show_recovery_code(parent, code: str) -> None:
    prompt = Prompt(parent, tr("recovery_show"), ok=tr("recovery_saved"), cancel=False)
    field = prompt.field
    field.setEchoMode(QLineEdit.Normal)
    field.setReadOnly(True)
    field.setText(code)
    field.setVisible(True)
    prompt.exec()


class SetupDialog(_Form):
    """Creates the password, once. Without it nothing is learnt, and dictation works the same."""

    def __init__(self, learner, parent=None):
        super().__init__(parent, tr("password_setup"), tr("password_create"))
        self.learner = learner
        self.new = NewPassword()
        self.body.addWidget(self.new)
        self.old = None
        if vault_legacy.pending() and vault_legacy.needs_old_password():
            self.old = QLineEdit(echoMode=QLineEdit.Password, placeholderText=tr("password_old"))
            self.body.addWidget(self.old)
        self._finish_layout()

    def _submit(self):
        if not self._new_password_ok():
            return
        vault = self.learner.vault
        old = self.old.text() if self.old else None
        if self.old:
            try:
                vault_legacy.check_old_password(old)
            except WrongPassword:
                self._show_error(tr("password_wrong"))
                return
        code = vault.create(self.new.password())
        if vault_legacy.pending():
            try:
                vault_legacy.migrate(vault, old)
            except Exception:  # the new key exists, so the code must still be shown; tried again on unlock
                log.exception("Could not move the old data to the new key")
        vault.migrate_readings()
        self.learner.activate()
        vault.lock()
        show_recovery_code(self, code)
        self.accept()


class UnlockDialog(_Form):
    """Accepted means the vault is unlocked; whoever opened it locks it again."""

    # On the class, not the instance, on purpose: the count must survive closing and reopening the
    # dialog, or the lockout after MAX_FAILURES could be skipped by simply closing it.
    failures = 0

    def __init__(self, learner, parent=None):
        super().__init__(parent, tr("password_current"), "OK")
        self.learner = learner
        self.field = QLineEdit(echoMode=QLineEdit.Password)
        self.body.addWidget(self.field)
        self.buttons.insertWidget(0, ghost_button(tr("password_forgot"), clicked=self._forgot))
        self._finish_layout()
        self.field.setFocus()

    def _submit(self):
        try:
            self.learner.unlock(self.field.text())
        except WrongPassword:
            UnlockDialog.failures += 1
            self.field.clear()
            self._show_error(tr("password_wrong"))
            if UnlockDialog.failures >= MAX_FAILURES:
                UnlockDialog.failures = 0
                self.ok.setEnabled(False)
                self._show_error(tr("password_wait", seconds=COOLDOWN_S))
                QTimer.singleShot(COOLDOWN_S * 1000, lambda: self.ok.setEnabled(True))
            return
        UnlockDialog.failures = 0
        self.accept()

    def _forgot(self):
        if RecoverDialog(self.learner, self).exec():
            self.accept()


class RecoverDialog(_Form):
    def __init__(self, learner, parent=None):
        super().__init__(parent, tr("recovery_prompt"), "OK")
        self.learner = learner
        self.code = QLineEdit(placeholderText="ABCD-EFGH-…")
        self.new = NewPassword()
        self.body.addWidget(self.code)
        self.body.addWidget(self.new)
        self._finish_layout()

    def _submit(self):
        if not self._new_password_ok():
            return
        try:
            self.learner.recover(self.code.text(), self.new.password())
        except WrongPassword:
            self._show_error(tr("recovery_wrong"))
            return
        self.accept()


class _ChangePassword(_Form):
    def __init__(self, vault, parent=None):
        super().__init__(parent, tr("password_new"), "OK")
        self.vault = vault
        self.new = NewPassword()
        self.body.addWidget(self.new)
        self._finish_layout()

    def _submit(self):
        if not self._new_password_ok():
            return
        self.vault.change_password(self.new.password())
        self.accept()


class _Export(_Form):
    """The password of the exported file and whether it carries the dictations."""

    def __init__(self, parent=None):
        super().__init__(parent, tr("export_password"), tr("export_ok"))
        self.setWindowTitle(tr("export"))
        self.new = NewPassword()
        self.dictations = QCheckBox(tr("export_dictations"))
        self.body.addWidget(self.new)
        self.body.addWidget(self.dictations)
        self.body.addWidget(note_label(tr("export_dictations_note")))
        self._finish_layout()

    def _submit(self):
        if self._new_password_ok():
            self.accept()


class _Import(_Form):
    """The password of the file to import and whether its settings replace these."""

    def __init__(self, path, parent=None):
        super().__init__(parent, tr("import_password"), tr("import_ok"))
        self.setWindowTitle(tr("import"))
        self.path, self.head, self.audio = path, None, b""
        self.field = QLineEdit(echoMode=QLineEdit.Password)
        self.settings = QCheckBox(tr("import_settings"), checked=True)
        self.mode = QComboBox()
        self.mode.addItem(tr("import_add"), False)
        self.mode.addItem(tr("import_replace"), True)
        self.body.addWidget(self.field)
        self.body.addWidget(self.mode)
        self.body.addWidget(note_label(tr("import_mode_note")))
        self.body.addWidget(self.settings)
        self._finish_layout()
        self.field.setFocus()

    def _submit(self):
        try:
            self.head, self.audio = transfer.read(self.path, self.field.text())
        except WrongPassword:
            self.field.clear()
            self._show_error(tr("password_wrong"))
            return
        except Exception:
            log.exception("Could not read %s", self.path)
            self._show_error(tr("import_not_ours"))
            return
        self.accept()
