"""Settings and About dialogs, plus the shared look of menus and windows."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import AUTHOR_URL, REPO_URL, __author__, __version__
from .audio import list_microphones
from .credits import CREDITS, TRAINING_CREDITS
from .i18n import tr
from .keyboard import parse_hotkey
from .paths import MODELS_DIR

STYLE = """
QMenu { background: rgba(28,28,32,235); color: #eee; border: 1px solid #3a3a42;
        border-radius: 10px; padding: 6px; font-size: 10pt; }
QMenu::item { padding: 7px 26px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: #2f6fdc; }
QMenu::separator { height: 1px; background: #3a3a42; margin: 5px 8px; }
QDialog { background: #1d1d22; color: #e6e6e6; }
QLabel, QCheckBox { color: #e6e6e6; }
QTabWidget::pane { border: 1px solid #33333b; border-radius: 6px; }
QTabBar::tab { background: #26262c; color: #bbb; padding: 6px 14px; border-radius: 6px; margin: 2px; }
QTabBar::tab:selected { background: #2f6fdc; color: white; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextBrowser {
        background: #26262c; color: #eee; border: 1px solid #3a3a42; border-radius: 5px; padding: 3px; }
QPushButton { background: #2f6fdc; color: white; border: none; border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { background: #3d7ef0; }
QPushButton:disabled { background: #444; color: #999; }
a { color: #6fb2ff; }
"""


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
        self.setWindowTitle("Cotorreando · " + tr("settings").rstrip("…"))
        self.setMinimumWidth(520)
        tabs = QTabWidget()
        tabs.addTab(self._general(), tr("general"))
        tabs.addTab(self._audio(), tr("audio"))
        tabs.addTab(self._typing(), tr("typing"))
        tabs.addTab(self._model(), tr("model"))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        note = QLabel(tr("restart"))
        note.setStyleSheet("color:#888")
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(note)
        layout.addWidget(buttons)
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

    def _general(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.language = self._combo([("es", "Español"), ("en", "English")], self.s.ui_language)
        self.mode = self._combo([("open", tr("mode_open")), ("ptt", tr("mode_ptt")),
                                 ("activation", tr("mode_activation"))], self.s.mode)
        self.activation = self._combo([("voice", tr("act_voice")), ("keyword", tr("act_keyword"))],
                                      self.s.activation)
        self.keyword = QLineEdit(self.s.keyword)
        self.hotkey = QLineEdit(self.s.hotkey)
        self.use_gpu = QCheckBox(tr("use_gpu"), checked=self.s.use_gpu)
        self.autostart = QCheckBox(tr("autostart"), checked=self.s.autostart)
        f.addRow(tr("language"), self.language)
        f.addRow(tr("mode"), self.mode)
        f.addRow(tr("activation"), self.activation)
        f.addRow(tr("keyword"), self.keyword)
        f.addRow(tr("hotkey"), self.hotkey)
        f.addRow(self.use_gpu)
        f.addRow(self.autostart)
        return w

    def _audio(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
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
        self.meter = QLabel()
        calibrate = QPushButton(tr("calibrate"))
        calibrate.clicked.connect(lambda: self.listener and self.listener.calibrate())
        row = QHBoxLayout()
        row.addWidget(self.meter, 1)
        row.addWidget(calibrate)
        f.addRow(tr("microphone"), self.mic)
        for box in (self.noise, self.echo, self.agc, self.auto):
            f.addRow(box)
        f.addRow(tr("threshold"), self.threshold)
        f.addRow(tr("vad_threshold"), self.vad)
        f.addRow(tr("silence"), self.silence)
        f.addRow(tr("session"), self.session)
        f.addRow(row)
        return w

    def _typing(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.holdoff = QSpinBox(minimum=0, maximum=10000, singleStep=100, value=self.s.typing_holdoff_ms)
        self.trailing = QCheckBox(tr("trailing"), checked=self.s.trailing_space)
        f.addRow(tr("holdoff"), self.holdoff)
        f.addRow(self.trailing)
        return w

    def _model(self):
        w, f = QWidget(), QFormLayout()
        w.setLayout(f)
        self.adapter = self._combo([("", tr("stock"))] + [(a, a) for a in adapters()], self.s.lora_adapter)
        f.addRow(tr("adapter"), self.adapter)
        return w

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
        s.microphone = self.mic.currentData()
        s.noise_suppression, s.echo_cancellation, s.auto_gain = (
            self.noise.isChecked(), self.echo.isChecked(), self.agc.isChecked())
        s.auto_threshold, s.energy_threshold_db = self.auto.isChecked(), self.threshold.value()
        s.vad_threshold, s.silence_ms, s.session_timeout_s = (
            self.vad.value(), self.silence.value(), self.session.value())
        s.typing_holdoff_ms, s.trailing_space = self.holdoff.value(), self.trailing.isChecked()
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
