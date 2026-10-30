"""Settings and About dialogs, plus the shared look of menus and windows."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMenu,
                               QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from . import AUTHOR_URL, REPO_URL, __author__, __version__
from .audio import list_microphones
from .credits import CREDITS, TRAINING_CREDITS
from .i18n import tr
from .keyboard import parse_hotkey
from .mosaic import logo_pixmap
from .paths import MODELS_DIR, PACKAGE_DIR

_ASSETS = (PACKAGE_DIR / "assets").as_posix()
STYLE = """
* { font-family: "Segoe UI"; font-size: 10pt; }
QMenu { background: rgba(26,27,31,240); color: #e8e9ec; border: 1px solid #30323a;
        border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 28px 8px 14px; border-radius: 8px; }
QMenu::item:selected { background: #2a2d34; }
QMenu::separator { height: 1px; background: #2c2e35; margin: 5px 10px; }
QDialog, QStackedWidget, QStackedWidget > QWidget, QScrollArea, #content { background: #16171b; color: #e8e9ec; }
QLabel, QCheckBox { color: #e8e9ec; background: transparent; }
#sidebar { background: #1b1c21; border: none; border-right: 1px solid #26282e; outline: 0; padding: 8px; }
#sidebar::item { color: #a4a7b0; padding: 9px 12px; border-radius: 8px; margin: 1px 0; }
#sidebar::item:hover { background: #22242a; }
#sidebar::item:selected { background: #2a2d34; color: #f3f4f6; }
#sideLogo { background: #1b1c21; border-right: 1px solid #26282e; padding: 18px 0 8px 0; }
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
QTextBrowser { background: #1d1f24; color: #e8e9ec; border: 1px solid #292b32; border-radius: 12px; padding: 12px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a3c45; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
a { color: #7fd1a8; }
""" % {"assets": _ASSETS}


def styled_menu() -> QMenu:
    menu = QMenu()
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def adapters() -> list[str]:
    root = MODELS_DIR / "adapters"
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


class SettingsDialog(QDialog):
    def __init__(self, settings, listener=None, parent=None):
        super().__init__(parent)
        self.s, self.listener = settings, listener
        self.calibrate_requested = False
        self.setWindowTitle("Cotorreando · " + tr("settings").rstrip("…"))
        self.resize(780, 560)

        self.pages = QStackedWidget()
        self.nav = QListWidget(objectName="sidebar")
        for title, page in ((tr("general"), self._general()), (tr("audio"), self._audio()),
                            (tr("typing"), self._typing()), (tr("model"), self._model())):
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
        self.accept()


class AboutDialog(QDialog):
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
        ok = QDialogButtonBox(QDialogButtonBox.Ok)
        ok.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(ok)
