"""Shared look of menus and windows: style sheet, frameless window, prompts and notices."""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import palette
from ..i18n import tr
from ..paths import PACKAGE_DIR

TITLE_BAR_HEIGHT = 36
NOTICE_MS = 20000
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
_ASSETS = (PACKAGE_DIR / "assets").as_posix()
STYLE = """
* { font-family: "Segoe UI"; font-size: 10pt; }
QMenu { background: %(MENU)s; color: %(TEXT)s; border: 1px solid %(WINDOW_BORDER)s;
        border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 28px 8px 14px; border-radius: 8px; }
QMenu::item:selected { background: %(SELECTED)s; }
QMenu::separator { height: 1px; background: %(MENU_SEPARATOR)s; margin: 5px 10px; }
QDialog, QStackedWidget, QStackedWidget > QWidget, QScrollArea, #content { background: %(BACKGROUND)s; color: %(TEXT)s; }
QDialog { border: 1px solid %(WINDOW_BORDER)s; }
#titleBar { background: %(BACKGROUND)s; }
#titleText { color: %(MUTED)s; font-size: 9pt; }
QPushButton#titleClose { background: transparent; color: %(SECONDARY)s; border-radius: 0; padding: 0; font-weight: 400; }
QPushButton#titleClose:hover { background: %(CLOSE_HOVER)s; color: %(WHITE)s; }
QPushButton#titleClose:pressed { background: %(CLOSE_PRESSED)s; color: %(WHITE)s; }
QLabel, QCheckBox { color: %(TEXT)s; background: transparent; }
#sidebar { background: %(BACKGROUND)s; border: none; border-right: 1px solid %(DIVIDER)s; outline: 0; padding: 8px; }
#sidebar::item { color: %(SECONDARY)s; padding: 9px 12px; border-radius: 8px; margin: 1px 0; }
#sidebar::item:hover { background: %(HOVER)s; }
#sidebar::item:selected { background: %(SELECTED)s; color: %(TITLE)s; }
#sideLogo { background: %(BACKGROUND)s; border-right: 1px solid %(DIVIDER)s; padding: 18px 0 8px 0; }
#pageTitle { font-size: 16pt; font-weight: 600; color: %(TITLE)s; }
#groupTitle { color: %(MUTED)s; font-size: 9pt; font-weight: 600; }
#card { background: %(CARD)s; border: 1px solid %(CARD_BORDER)s; border-radius: 12px; }
#rowLine { background: %(CARD_BORDER)s; border: none; max-height: 1px; }
#footer { background: %(BACKGROUND)s; border-top: 1px solid %(DIVIDER)s; }
#title { font-size: 18pt; font-weight: 600; color: %(TITLE)s; }
#body { color: %(BODY)s; font-size: 11pt; }
#note, #caption { color: %(MUTED)s; font-size: 9pt; }
#cheer { color: %(CHEER)s; font-size: 12pt; font-weight: 600; }
#panel { font-size: 18pt; padding: 8px 12px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: %(FIELD)s; color: %(TEXT)s; border: 1px solid %(FIELD_BORDER)s; border-radius: 8px;
        padding: 6px 10px; min-height: 18px; selection-background-color: %(ACCENT)s; selection-color: %(ON_ACCENT)s; }
QLineEdit[recording="true"] { border-color: %(RECORDING)s; color: %(RECORDING_TEXT)s; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: %(ACCENT)s; }
QLineEdit:disabled, QDoubleSpinBox:disabled { color: %(DISABLED_TEXT)s; background: %(FIELD_DISABLED)s; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(%(assets)s/chevron.png); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: %(FIELD)s; color: %(TEXT)s; border: 1px solid %(FIELD_BORDER)s;
        selection-background-color: %(LIST_SELECTED)s; outline: 0; padding: 4px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; background: %(FIELD)s; border: 1px solid %(CHECKBOX_BORDER)s; }
QCheckBox::indicator:checked { background: %(ACCENT)s; border-color: %(ACCENT)s; image: url(%(assets)s/check.png); }
QPushButton { background: %(ACCENT)s; color: %(ON_ACCENT)s; border: none; border-radius: 8px; padding: 8px 18px; font-weight: 600; }
QPushButton:hover { background: %(ACCENT_HOVER)s; }
QPushButton:pressed { background: %(ACCENT_PRESSED)s; }
QPushButton:disabled { background: %(FIELD_BORDER)s; color: %(DISABLED_BUTTON_TEXT)s; }
QPushButton#ghost { background: transparent; color: %(BODY)s; border: 1px solid %(GHOST_BORDER)s; font-weight: 400; }
QPushButton#ghost:hover { background: %(GHOST_HOVER)s; color: %(TEXT)s; }
QProgressBar#meter { background: %(FIELD)s; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar#meter::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(ACCENT)s, stop:1 %(CHEER)s); border-radius: 3px; }
QPlainTextEdit { background: %(FIELD)s; color: %(TEXT)s; border: 1px solid %(FIELD_BORDER)s; border-radius: 8px;
        padding: 6px; selection-background-color: %(ACCENT)s; selection-color: %(ON_ACCENT)s; }
QPlainTextEdit:focus { border-color: %(ACCENT)s; }
QTextBrowser { background: %(CARD)s; color: %(TEXT)s; border: 1px solid %(CARD_BORDER)s; border-radius: 12px; padding: 12px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(SCROLLBAR)s; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTabBar { background: %(BACKGROUND)s; }
QTabBar::tab { background: transparent; color: %(SECONDARY)s; padding: 8px 16px; border: none;
        border-bottom: 2px solid transparent; }
QTabBar::tab:hover { color: %(TEXT)s; }
QTabBar::tab:selected { color: %(TITLE)s; border-bottom-color: %(ACCENT)s; }
a { color: %(LINK)s; }
""" % {**palette.tokens(), "assets": _ASSETS}


def apply_theme(app) -> None:
    """The style sheet, plus the link colour: rich-text labels take it from the palette, not from CSS."""
    app.setStyleSheet(STYLE)
    qt = app.palette()
    qt.setColor(QPalette.Link, QColor(palette.LINK))
    qt.setColor(QPalette.LinkVisited, QColor(palette.LINK))
    app.setPalette(qt)


def styled_menu() -> QMenu:
    menu = QMenu()
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def ghost_button(text: str, **props) -> QPushButton:
    """The quiet button, for what is not the main action."""
    return QPushButton(text, objectName="ghost", **props)


def button_row(*buttons: QWidget) -> QHBoxLayout:
    """Buttons together at the right edge of a dialog."""
    row = QHBoxLayout()
    row.addStretch()
    for button in buttons:
        row.addWidget(button)
    return row


def dialog_layout(window: QWidget, top: int = 8, spacing: int = 14) -> QVBoxLayout:
    """The column of a small dialog: text, fields, then its buttons."""
    layout = QVBoxLayout(window)
    layout.setContentsMargins(24, top, 24, 20)
    layout.setSpacing(spacing)
    return layout


def footer_bar() -> tuple[QFrame, QHBoxLayout]:
    """The strip along the bottom of the big dialogs; the caller fills the layout."""
    footer = QFrame(objectName="footer")
    layout = QHBoxLayout(footer)
    layout.setContentsMargins(24, 12, 24, 12)
    return footer, layout


def note_label(text: str) -> QLabel:
    return QLabel(text, objectName="note", wordWrap=True)


def inline_row(*items: QWidget | tuple[QWidget, int], spacing: int | None = None, trailing_stretch=False) -> QWidget:
    """Widgets side by side; an item may be ``(widget, stretch)``."""
    row = QWidget()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    if spacing is not None:
        line.setSpacing(spacing)
    for item in items:
        widget, stretch = item if isinstance(item, tuple) else (item, 0)
        line.addWidget(widget, stretch)
    if trailing_stretch:
        line.addStretch()
    return row


def scroll_area(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
    scroll.setWidget(widget)
    return scroll


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
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(self.winId()), DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), ctypes.sizeof(corner)
        )
        super().showEvent(event)


class Prompt(Window):
    """A short message, optionally asking for a password."""

    def __init__(self, parent, text, ok=None, cancel=True, password=False):
        super().__init__(parent)
        self.setWindowTitle("Cotorreando")
        self.setFixedWidth(420)
        layout = dialog_layout(self)
        layout.addWidget(QLabel(text, wordWrap=True))
        self.field = QLineEdit(echoMode=QLineEdit.Password)
        self.field.setVisible(password)
        layout.addWidget(self.field)
        buttons = [ghost_button(tr("cancel"), clicked=self.reject)] if cancel else []
        buttons.append(QPushButton(ok or tr("cal_finish"), clicked=self.accept, default=True))
        layout.addLayout(button_row(*buttons))


def ask_password(parent, text) -> str | None:
    prompt = Prompt(parent, text, ok="OK", password=True)
    return prompt.field.text() if prompt.exec() else None


def inform(parent, text: str, ok: str | None = None) -> None:
    """A message with a single button, shown until it is dismissed."""
    Prompt(parent, text, ok=ok, cancel=False).exec()


class Notice(QWidget):
    """A note that comes out of the bubble. It never takes the keyboard from what you are doing."""

    def __init__(self, text, action, on_action, dismiss=None, on_dismiss=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("notice")
        self.setStyleSheet(
            "#notice { background: %s; border: 1px solid %s; }" % (palette.BACKGROUND, palette.WINDOW_BORDER)
        )
        self.setAttribute(Qt.WA_StyledBackground)
        button = QPushButton(action, clicked=lambda: (self.close(), on_action()))
        button.setFocusPolicy(Qt.NoFocus)
        later = ghost_button(dismiss or tr("later"), clicked=lambda: (self.close(), on_dismiss and on_dismiss()))
        later.setFocusPolicy(Qt.NoFocus)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(text, wordWrap=True))
        layout.addLayout(button_row(later, button))
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


def privacy_link() -> QLabel:
    """A link to the privacy page, in the language of the interface; opens in the browser."""
    link = QLabel(f"<a href='{tr('privacy_url')}'>{tr('privacy_link')}</a>", objectName="note")
    link.setOpenExternalLinks(True)
    return link
