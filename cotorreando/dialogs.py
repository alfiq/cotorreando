"""Settings and About dialogs, plus the shared look of menus and windows."""

from __future__ import annotations

import ctypes
import logging
import secrets

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QStackedWidget, QTabBar, QTextBrowser, QVBoxLayout, QWidget)

from . import AUTHOR_URL, REPO_URL, __author__, __version__
from .audio import RATE, Player, list_microphones
from .credits import CREDITS, TRAINING_CREDITS
from .i18n import tr
from .keyboard import parse_hotkey
from .learning import phrase_alpha
from .mosaic import logo_pixmap
from .paths import MODELS_DIR, PACKAGE_DIR
from . import vault_legacy
from .vault import WrongPassword, password_problem

log = logging.getLogger(__name__)

TITLE_BAR_HEIGHT = 36
MAX_FAILURES, COOLDOWN_S = 5, 60
NOTICE_MS = 20000
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
_ASSETS = (PACKAGE_DIR / "assets").as_posix()
STYLE = """
* { font-family: "Segoe UI"; font-size: 10pt; }
QMenu { background: rgba(26,27,31,240); color: #e8e9ec; border: 1px solid #30323a;
        border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 28px 8px 14px; border-radius: 8px; }
QMenu::item:selected { background: #2a2d34; }
QMenu::separator { height: 1px; background: #2c2e35; margin: 5px 10px; }
QDialog, QStackedWidget, QStackedWidget > QWidget, QScrollArea, #content { background: #16171b; color: #e8e9ec; }
QDialog { border: 1px solid #30323a; }
#titleBar { background: #16171b; }
#titleText { color: #8b8f99; font-size: 9pt; }
QPushButton#titleClose { background: transparent; color: #a4a7b0; border-radius: 0; padding: 0; font-weight: 400; }
QPushButton#titleClose:hover { background: #c42b1c; color: #ffffff; }
QPushButton#titleClose:pressed { background: #a32417; color: #ffffff; }
QLabel, QCheckBox { color: #e8e9ec; background: transparent; }
#sidebar { background: #16171b; border: none; border-right: 1px solid #26282e; outline: 0; padding: 8px; }
#sidebar::item { color: #a4a7b0; padding: 9px 12px; border-radius: 8px; margin: 1px 0; }
#sidebar::item:hover { background: #22242a; }
#sidebar::item:selected { background: #2a2d34; color: #f3f4f6; }
#sideLogo { background: #16171b; border-right: 1px solid #26282e; padding: 18px 0 8px 0; }
#pageTitle { font-size: 16pt; font-weight: 600; color: #f3f4f6; }
#groupTitle { color: #8b8f99; font-size: 9pt; font-weight: 600; }
#card { background: #1d1f24; border: 1px solid #292b32; border-radius: 12px; }
#rowLine { background: #292b32; border: none; max-height: 1px; }
#footer { background: #16171b; border-top: 1px solid #26282e; }
#title { font-size: 18pt; font-weight: 600; color: #f3f4f6; }
#body { color: #b6b9c2; font-size: 11pt; }
#note, #caption { color: #8b8f99; font-size: 9pt; }
#cheer { color: #a9dcc2; font-size: 12pt; font-weight: 600; }
#panel { font-size: 18pt; padding: 8px 12px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #25272d; color: #e8e9ec; border: 1px solid #33353d; border-radius: 8px;
        padding: 6px 10px; min-height: 18px; selection-background-color: #3f9d78; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #3f9d78; }
QLineEdit:disabled, QDoubleSpinBox:disabled { color: #6d717b; background: #1f2126; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(%(assets)s/chevron.png); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: #25272d; color: #e8e9ec; border: 1px solid #33353d;
        selection-background-color: #33363e; outline: 0; padding: 4px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; background: #25272d; border: 1px solid #3a3c45; }
QCheckBox::indicator:checked { background: #3f9d78; border-color: #3f9d78; image: url(%(assets)s/check.png); }
QPushButton { background: #3f9d78; color: #ffffff; border: none; border-radius: 8px; padding: 8px 18px; font-weight: 600; }
QPushButton:hover { background: #4aae87; }
QPushButton:pressed { background: #378a69; }
QPushButton:disabled { background: #33353d; color: #7b7f88; }
QPushButton#ghost { background: transparent; color: #b6b9c2; border: 1px solid #383a43; font-weight: 400; }
QPushButton#ghost:hover { background: #24262c; color: #e8e9ec; }
QProgressBar#meter { background: #25272d; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar#meter::chunk { background: #3f9d78; border-radius: 3px; }
QPlainTextEdit { background: #25272d; color: #e8e9ec; border: 1px solid #33353d; border-radius: 8px;
        padding: 6px; selection-background-color: #3f9d78; }
QPlainTextEdit:focus { border-color: #3f9d78; }
QTextBrowser { background: #1d1f24; color: #e8e9ec; border: 1px solid #292b32; border-radius: 12px; padding: 12px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a3c45; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTabBar { background: #16171b; }
QTabBar::tab { background: transparent; color: #a4a7b0; padding: 8px 16px; border: none;
        border-bottom: 2px solid transparent; }
QTabBar::tab:hover { color: #e8e9ec; }
QTabBar::tab:selected { color: #f3f4f6; border-bottom-color: #3f9d78; }
a { color: #7fd1a8; }
""" % {"assets": _ASSETS}


def styled_menu() -> QMenu:
    menu = QMenu()
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


class Window(QDialog):
    """A dialog with our own title bar: same colour as the window, and only a close button."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.bar = QFrame(self, objectName="titleBar")
        self.bar.setFixedHeight(TITLE_BAR_HEIGHT)
        caption = QLabel(objectName="titleText")
        self.windowTitleChanged.connect(caption.setText)
        close = QPushButton("✕", objectName="titleClose", clicked=self.close)
        close.setFixedSize(TITLE_BAR_HEIGHT + 6, TITLE_BAR_HEIGHT)
        close.setFocusPolicy(Qt.NoFocus)
        row = QHBoxLayout(self.bar)
        row.setContentsMargins(14, 0, 0, 0)
        row.addWidget(caption, 1)
        row.addWidget(close)
        self.bar.installEventFilter(self)
        caption.installEventFilter(self)
        # The layouts subclasses put on this dialog stay below the bar and inside the border.
        self.setContentsMargins(1, TITLE_BAR_HEIGHT + 1, 1, 1)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.windowHandle().startSystemMove()
            return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        self.bar.setGeometry(1, 1, self.width() - 2, TITLE_BAR_HEIGHT)
        super().resizeEvent(event)

    def showEvent(self, event):
        # Windows 11 rounds frameless windows only when asked; older versions just decline.
        corner = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), DWMWA_WINDOW_CORNER_PREFERENCE,
                                                   ctypes.byref(corner), ctypes.sizeof(corner))
        super().showEvent(event)


class Prompt(Window):
    """A short message, optionally asking for a password."""

    def __init__(self, parent, text, ok=None, cancel=True, password=False):
        super().__init__(parent)
        self.setWindowTitle("Cotorreando")
        self.setFixedWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(QLabel(text, wordWrap=True))
        self.field = QLineEdit(echoMode=QLineEdit.Password)
        self.field.setVisible(password)
        layout.addWidget(self.field)
        buttons = QHBoxLayout()
        buttons.addStretch()
        if cancel:
            buttons.addWidget(QPushButton(tr("cancel"), objectName="ghost", clicked=self.reject))
        buttons.addWidget(QPushButton(ok or tr("cal_finish"), clicked=self.accept, default=True))
        layout.addLayout(buttons)


def ask_password(parent, text) -> str | None:
    prompt = Prompt(parent, text, ok="OK", password=True)
    return prompt.field.text() if prompt.exec() else None


class NewPassword(QWidget):
    """Two fields for a new password, plus one that makes up a strong one to save in a manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.first = QLineEdit(echoMode=QLineEdit.Password, placeholderText=tr("password_new_hint"))
        self.second = QLineEdit(echoMode=QLineEdit.Password, placeholderText=tr("password_again"))
        generate = QPushButton(tr("password_generate"), objectName="ghost", clicked=self._generate)
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

    def __init__(self, parent, text, ok):
        super().__init__(parent)
        self.setWindowTitle(tr("password_prompt"))
        self.setFixedWidth(460)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24, 8, 24, 20)
        self.body.setSpacing(12)
        self.body.addWidget(QLabel(text, wordWrap=True))
        self.error = QLabel(objectName="note", wordWrap=True)
        self.error.hide()
        self.buttons = QHBoxLayout()
        self.buttons.addStretch()
        self.buttons.addWidget(QPushButton(tr("cancel"), objectName="ghost", clicked=self.reject))
        self.ok = QPushButton(ok, clicked=self._submit, default=True)
        self.buttons.addWidget(self.ok)

    def _finish_layout(self):
        self.body.addWidget(self.error)
        self.body.addLayout(self.buttons)

    def _show_error(self, text):
        self.error.setText(text)
        self.error.show()


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
        problem = self.new.problem()
        if problem:
            self._show_error(problem)
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
            except Exception:    # the new key exists, so the code must still be shown; tried again on unlock
                log.exception("Could not move the old data to the new key")
        vault.migrate_readings()
        self.learner.activate()
        vault.lock()
        show_recovery_code(self, code)
        self.accept()


class UnlockDialog(_Form):
    """Accepted means the vault is unlocked; whoever opened it locks it again."""

    failures = 0

    def __init__(self, learner, parent=None):
        super().__init__(parent, tr("password_current"), "OK")
        self.learner = learner
        self.field = QLineEdit(echoMode=QLineEdit.Password)
        self.body.addWidget(self.field)
        self.buttons.insertWidget(0, QPushButton(tr("password_forgot"), objectName="ghost", clicked=self._forgot))
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
        problem = self.new.problem()
        if problem:
            self._show_error(problem)
            return
        try:
            self.learner.recover(self.code.text(), self.new.password())
        except WrongPassword:
            self._show_error(tr("recovery_wrong"))
            return
        self.accept()


class Notice(QWidget):
    """A note that comes out of the bubble. It never takes the keyboard from what you are doing."""

    def __init__(self, text, action, on_action):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("notice")
        self.setStyleSheet("#notice { background: #16171b; border: 1px solid #30323a; }")
        self.setAttribute(Qt.WA_StyledBackground)
        button = QPushButton(action, clicked=lambda: (self.close(), on_action()))
        button.setFocusPolicy(Qt.NoFocus)
        later = QPushButton(tr("later"), objectName="ghost", clicked=self.close)
        later.setFocusPolicy(Qt.NoFocus)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(later)
        row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(text, wordWrap=True))
        layout.addLayout(row)
        self.setFixedWidth(320)
        QTimer.singleShot(NOTICE_MS, self.close)

    def show_near(self, anchor: QRect, area: QRect) -> None:
        self.adjustSize()
        x = anchor.right() + 12
        if x + self.width() > area.right():
            x = anchor.left() - self.width() - 12
        y = min(max(anchor.center().y() - self.height() // 2, area.top()), area.bottom() - self.height())
        self.move(max(x, area.left()), y)
        self.show()


def adapters() -> list[str]:
    root = MODELS_DIR / "adapters"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


class SettingsDialog(Window):
    def __init__(self, settings, listener=None, learner=None, parent=None):
        super().__init__(parent)
        self.s, self.listener, self.learner = settings, listener, learner
        self.calibrate_requested = False
        self.setWindowTitle("Cotorreando · " + tr("settings").rstrip("…"))
        self.resize(780, 560)

        self.pages = QStackedWidget()
        self.nav = QListWidget(objectName="sidebar")
        for title, page in ((tr("general"), self._general()), (tr("audio"), self._audio()),
                            (tr("typing"), self._typing()), (tr("model"), self._model()),
                            (tr("privacy"), self._privacy())):
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
        self.mode = self._combo([("open", tr("mode_open")), ("ptt", tr("mode_ptt")),
                                 ("activation", tr("mode_activation"))], self.s.mode)
        self.activation = self._combo([("voice", tr("act_voice")), ("keyword", tr("act_keyword"))],
                                      self.s.activation)
        self.keyword = QLineEdit(self.s.keyword)
        self.hotkey = QLineEdit(self.s.hotkey)
        self.blob_size = self._combo([(k, tr(k)) for k in ("small", "medium", "large")], self.s.blob_size)
        self.use_gpu = QCheckBox(tr("use_gpu"), checked=self.s.use_gpu)
        self.autostart = QCheckBox(tr("autostart"), checked=self.s.autostart)
        return self._groups(
            (tr("listening"), [(tr("mode"), self.mode), (tr("activation"), self.activation),
                               (tr("keyword"), self.keyword), (tr("hotkey"), self.hotkey)]),
            (tr("appearance"), [(tr("language"), self.language), (tr("blob_size"), self.blob_size)]),
            (tr("system"), [self.use_gpu, self.autostart]))

    def _audio(self):
        self.mic = self._combo([("", tr("default"))] + [(m, m) for m in list_microphones()],
                               self.s.microphone)
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
            (tr("detection"), [self.auto, (tr("threshold"), self.threshold),
                               (tr("vad_threshold"), self.vad), (tr("silence"), self.silence),
                               (tr("session"), self.session), row]))

    def _typing(self):
        self.holdoff = QSpinBox(minimum=0, maximum=10000, singleStep=100, value=self.s.typing_holdoff_ms)
        self.trailing = QCheckBox(tr("trailing"), checked=self.s.trailing_space)
        self.streaming = QCheckBox(tr("streaming"), checked=self.s.streaming)
        return self._groups((None, [(tr("holdoff"), self.holdoff), self.trailing, self.streaming]))

    def _model(self):
        self.adapter = self._combo([("", tr("stock"))] + [(a, a) for a in adapters()], self.s.lora_adapter)
        help_text = QLabel(tr("calibrate_help"), objectName="note", wordWrap=True)
        calibrate = QPushButton(tr("calibrate_voice"))
        calibrate.clicked.connect(self._calibrate)
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(16)
        line.addWidget(help_text, 1)
        line.addWidget(calibrate)
        return self._groups((None, [(tr("adapter"), self.adapter), row]))

    def _privacy(self):
        self.learning = QCheckBox(tr("learning"), checked=self.s.learning)
        self.excluded = QLineEdit(self.s.excluded_apps)
        self.retention = QSpinBox(minimum=1, maximum=3650, value=self.s.retention_days)
        note = QLabel(tr("privacy_note"), objectName="note", wordWrap=True)
        self.password = QPushButton(objectName="ghost", clicked=self._change_password)
        view = QPushButton(tr("data_view"), objectName="ghost", clicked=self._view_data)
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.password)
        line.addWidget(view)
        line.addStretch()
        self._show_password_state()
        return self._groups((None, [self.learning, (tr("excluded"), self.excluded),
                                    (tr("retention"), self.retention), row, note]))

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

    def _calibrate(self):
        self.calibrate_requested = True
        self.reject()

    def _update_meter(self):
        lvl = getattr(self.listener, "last_level", -90.0)
        self.meter.setText(tr("level", lvl=lvl, thr=self.listener.threshold_db))

    def _accept(self):
        try:
            parse_hotkey(self.hotkey.text())
        except ValueError:
            self.hotkey.setFocus()
            self.hotkey.selectAll()
            return
        s = self.s
        s.ui_language, s.mode, s.activation = (self.language.currentData(), self.mode.currentData(),
                                               self.activation.currentData())
        s.keyword, s.hotkey = self.keyword.text().strip().lower(), self.hotkey.text().strip().lower()
        s.use_gpu, s.autostart = self.use_gpu.isChecked(), self.autostart.isChecked()
        s.blob_size = self.blob_size.currentData()
        s.microphone = self.mic.currentData()
        s.noise_suppression, s.echo_cancellation, s.auto_gain = (
            self.noise.isChecked(), self.echo.isChecked(), self.agc.isChecked())
        s.auto_threshold, s.energy_threshold_db = self.auto.isChecked(), self.threshold.value()
        s.vad_threshold, s.silence_ms, s.session_timeout_s = (
            self.vad.value(), self.silence.value(), self.session.value())
        s.typing_holdoff_ms, s.trailing_space = self.holdoff.value(), self.trailing.isChecked()
        s.streaming = self.streaming.isChecked()
        s.lora_adapter = self.adapter.currentData()
        s.learning, s.excluded_apps = self.learning.isChecked(), self.excluded.text().strip()
        s.retention_days = self.retention.value()
        self.accept()


class _ChangePassword(_Form):
    def __init__(self, vault, parent=None):
        super().__init__(parent, tr("password_new"), "OK")
        self.vault = vault
        self.new = NewPassword()
        self.body.addWidget(self.new)
        self._finish_layout()

    def _submit(self):
        problem = self.new.problem()
        if problem:
            self._show_error(problem)
            return
        self.vault.change_password(self.new.password())
        self.accept()


class DataDialog(Window):
    """What has been kept, to read, listen to and delete. The vault must be unlocked."""

    playback_ended = Signal(str)

    def __init__(self, learner, parent=None):
        super().__init__(parent)
        self.learner = learner
        self.vault = learner.vault
        self.player = Player()
        self.playing = ""
        self.cards: dict[str, tuple[QFrame, QPushButton]] = {}
        self.setWindowTitle(tr("data_title"))
        self.resize(720, 560)
        self.playback_ended.connect(self._on_ended)

        inner = QWidget(objectName="content")
        self.rows = QVBoxLayout(inner)
        self.rows.setContentsMargins(28, 16, 28, 24)
        self.rows.setSpacing(10)
        for rid in reversed(self.vault.record_ids()):
            meta, samples = self.vault.read_record(rid)
            self.rows.addWidget(self._card(rid, meta, samples.size / RATE))
        self.empty = QLabel(tr("data_empty"), objectName="note")
        self.empty.setVisible(not self.cards)
        self.rows.addWidget(self.empty)
        self.rows.addStretch()

        pages = QStackedWidget()
        pages.addWidget(self._scroll(inner))
        pages.addWidget(self._scroll(self._words_page()))
        tabs = QTabBar(drawBase=False, expanding=False)
        tabs.addTab(tr("data_tab_dictations"))
        tabs.addTab(tr("data_tab_words"))
        header = QWidget(objectName="content")
        top = QVBoxLayout(header)
        top.setContentsMargins(28, 24, 28, 0)
        top.setSpacing(8)
        top.addWidget(QLabel(tr("data_title"), objectName="pageTitle"))
        top.addWidget(tabs)

        self.delete_all = QPushButton(tr("data_delete_all"), objectName="ghost", clicked=self._delete_all)
        self.delete_all.setEnabled(bool(self.cards))
        tabs.currentChanged.connect(pages.setCurrentIndex)
        tabs.currentChanged.connect(lambda i: self.delete_all.setVisible(i == 0))
        close = QPushButton(tr("cal_finish"), clicked=self.accept, default=True)
        footer = QFrame(objectName="footer")
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(24, 12, 24, 12)
        bottom.addWidget(self.delete_all)
        bottom.addStretch()
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(pages, 1)
        layout.addWidget(footer)

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _words_page(self) -> QWidget:
        """What has been learnt word by word: replacements, corrections on their way, hard words."""
        page = QWidget(objectName="content")
        rows = QVBoxLayout(page)
        rows.setContentsMargins(28, 16, 28, 24)
        rows.setSpacing(10)
        pairs = self.learner.corrections()
        drop = self.learner.drop_correction
        sections = (
            (tr("words_boost"), tr("words_boost_note"),
             [(f"{old}  →  {new}", tr("words_boost_detail", n=n, alpha=phrase_alpha(n)),
               lambda o=old, w=new: drop(o, w))
              for old, new, n in pairs]),
            (tr("words_hard"), tr("words_hard_note"),
             [(e["word"], tr("words_hard_times", n=e["count"], read=e["read"]),
               lambda w=e["word"]: self.learner.drop_hard_word(w))
              for e in self.learner.hard_words()]),
        )
        for title, note, items in sections:
            rows.addSpacing(6)
            rows.addWidget(QLabel(title, objectName="groupTitle"))
            rows.addWidget(self._text(note, "note"))
            if not items:
                rows.addWidget(self._text(tr("words_none"), "note"))
            for text, detail, forget in items:
                rows.addWidget(self._word_row(text, detail, forget))
        rows.addStretch()
        return page

    def _word_row(self, text: str, detail: str, forget) -> QFrame:
        row = QFrame(objectName="card")
        line = QHBoxLayout(row)
        line.setContentsMargins(16, 8, 10, 8)
        line.addWidget(self._text(text), 1)
        line.addWidget(QLabel(detail, objectName="caption"))

        def delete() -> None:
            forget()
            row.deleteLater()

        line.addWidget(QPushButton(tr("data_delete"), objectName="ghost", clicked=delete))
        return row

    def _card(self, rid: str, meta: dict, seconds: float) -> QFrame:
        date = f"{rid[6:8]}/{rid[4:6]}/{rid[:4]} {rid[9:11]}:{rid[11:13]}"
        card = QFrame(objectName="card")
        column = QVBoxLayout(card)
        column.setContentsMargins(16, 12, 16, 12)
        column.setSpacing(8)
        column.addWidget(QLabel(f"{tr('kind_' + meta['kind'])} · {date} · {seconds:.0f} s", objectName="caption"))
        label = self._text(meta["text"])
        editor = QPlainTextEdit(tabChangesFocus=True, visible=False)
        editor.setFixedHeight(96)
        column.addWidget(label)
        column.addWidget(editor)
        if meta.get("old"):
            column.addWidget(self._text(tr("data_old", text=meta["old"]), "note"))
        play = QPushButton(tr("data_play"), clicked=lambda: self._toggle(rid))
        edit = QPushButton(tr("data_edit"), objectName="ghost")
        delete = QPushButton(tr("data_delete"), objectName="ghost", clicked=lambda: self._delete(rid))
        save = QPushButton(tr("save"), visible=False)
        cancel = QPushButton(tr("cancel"), objectName="ghost", visible=False)

        def editing(on: bool) -> None:
            for widget in (editor, save, cancel):
                widget.setVisible(on)
            for widget in (label, edit, delete):
                widget.setVisible(not on)

        def begin() -> None:
            editor.setPlainText(label.text())
            editing(True)
            editor.setFocus()

        def finish() -> None:
            text = editor.toPlainText().strip()
            self._save_text(rid, text)
            label.setText(text)
            editing(False)

        edit.clicked.connect(begin)
        save.clicked.connect(finish)
        cancel.clicked.connect(lambda: editing(False))
        editor.textChanged.connect(lambda: save.setEnabled(bool(editor.toPlainText().strip())))
        line = QHBoxLayout()
        for widget in (play, edit, delete, save, cancel):
            line.addWidget(widget)
        line.addStretch()
        column.addLayout(line)
        self.cards[rid] = (card, play)
        return card

    def _save_text(self, rid: str, text: str) -> None:
        # Your own word counts as verified: training must not throw it away. Untrained again, so it gets learnt.
        self.vault.update_record(rid, {"text": text, "verified": True})
        self.vault.set_trained_ids([i for i in self.vault.trained_ids() if i != rid])

    @staticmethod
    def _text(text: str, name: str = "") -> QLabel:
        label = QLabel(text, objectName=name, wordWrap=True, textFormat=Qt.PlainText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def _toggle(self, rid: str) -> None:
        same = rid == self.playing
        self._stop()
        if same:
            return
        _, samples = self.vault.read_record(rid)
        self.playing = rid
        self.cards[rid][1].setText(tr("data_stop"))
        self.player.play(samples, lambda: self.playback_ended.emit(rid))

    def _stop(self) -> None:
        self.player.stop()
        if self.playing in self.cards:
            self.cards[self.playing][1].setText(tr("data_play"))
        self.playing = ""

    def _on_ended(self, rid: str) -> None:
        if rid == self.playing:      # not one that was stopped to play another
            self._stop()

    def _delete(self, rid: str) -> None:
        if rid == self.playing:
            self._stop()
        self.vault.delete_record(rid)
        self.cards.pop(rid)[0].deleteLater()
        self.empty.setVisible(not self.cards)
        self.delete_all.setEnabled(bool(self.cards))

    def _delete_all(self):
        if Prompt(self, tr("data_confirm"), ok=tr("data_delete_all")).exec():
            self._stop()
            self.vault.delete_all_records()
            for card, _ in self.cards.values():
                card.deleteLater()
            self.cards.clear()
            self.empty.show()
            self.delete_all.setEnabled(False)

    def done(self, result):
        self._stop()
        super().done(result)


class AboutDialog(Window):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.resize(560, 520)
        rows = "".join(
            f"<p><b><a href='{url}'>{name}</a></b> — {purpose}<br>"
            f"<a href='{lic_url}'>{lic}</a> · <span style='color:#999'>{note}</span></p>"
            for name, purpose, lic, url, lic_url, note in CREDITS + TRAINING_CREDITS)
        html = (
            f"<h2>Cotorreando {__version__}</h2><p>{tr('tagline')}</p>"
            f"<p>{tr('author')}: <b>{__author__}</b> · <a href='{AUTHOR_URL}'>{AUTHOR_URL}</a><br>"
            f"Repo: <a href='{REPO_URL}'>{REPO_URL}</a> · MIT</p>"
            f"<h3>{tr('credits')}</h3>{rows}")
        text = QTextBrowser(openExternalLinks=True)
        text.setHtml(html)
        close = QHBoxLayout()
        close.addStretch()
        close.addWidget(QPushButton(tr("cal_finish"), clicked=self.accept))
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addLayout(close)
