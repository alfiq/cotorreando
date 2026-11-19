"""Model download and model error dialogs."""

from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .. import (
    model_store,
)
from ..i18n import tr
from ..mosaic import Mosaic
from .base import Prompt, Window

log = logging.getLogger(__name__)


def model_error_text(err: Exception) -> str:
    if isinstance(err, model_store.ModelError):
        return tr(err.key, **err.kw)
    return str(err)


def choose_model_folder(parent=None, start: str = "") -> str | None:
    """Ask for the folder of the user's own model; None unless it holds one we can run."""
    path = QFileDialog.getExistingDirectory(parent, tr("own_model_pick"), start)
    if not path:
        return None
    problem = None
    QApplication.setOverrideCursor(Qt.WaitCursor)  # loading the graphs takes a few seconds
    try:
        model_store.validate(path)
    except model_store.InvalidModel as err:
        problem = model_error_text(err)
    finally:
        QApplication.restoreOverrideCursor()
    if problem:
        Prompt(parent, tr("model_invalid", reason=problem), ok="OK", cancel=False).exec()
        return None
    return path


def _size(n: float) -> str:
    return f"{n / 1024**2:,.0f} MB"


def _duration(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds >= 90 else f"{seconds:.0f} s"


class DownloadDialog(Window):
    """The first download of the model: the parrot's tiles light up as the bytes arrive.

    ``download(progress, cancelled)`` runs on a thread and raises a ModelError on failure.
    The result is accepted on success; otherwise ``error`` says why (Cancelled included).
    """

    _progress = Signal(int, int)
    _ended = Signal(object)

    def __init__(self, download, parent=None):
        super().__init__(parent)
        self.download, self.error = download, None
        self._cancel, self._last = threading.Event(), 0.0
        self._started = self._running = False
        self._rate = model_store.Rate()
        self.setWindowTitle(tr("dl_title"))
        self.setFixedWidth(460)
        self.mosaic = Mosaic(5, 0.0)
        self.label = QLabel(tr("dl_starting"), objectName="note", alignment=Qt.AlignCenter)
        self.cancel = QPushButton(tr("cancel"), objectName="ghost", clicked=self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(self.mosaic, 0, Qt.AlignCenter)
        layout.addWidget(QLabel(tr("dl_intro"), wordWrap=True))
        layout.addWidget(self.label)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        layout.addLayout(buttons)
        self._progress.connect(self._show)
        self._ended.connect(self._finish)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = self._running = True
            threading.Thread(target=self._run, daemon=True, name="download").start()

    def _run(self):
        try:
            self.download(self._report, self._cancel.is_set)
        except model_store.ModelError as err:
            self._ended.emit(err)
        except Exception as err:  # never leave the dialog spinning
            log.exception("Model download failed")
            self._ended.emit(model_store.DownloadFailed(str(err)))
        else:
            self._ended.emit(None)

    def _report(self, done: int, total: int) -> None:
        now = time.monotonic()
        if now - self._last >= 0.1 or done == total:  # ~10 updates a second is plenty
            self._last = now
            self._progress.emit(done, total)

    def _show(self, done: int, total: int) -> None:
        speed = self._rate.update(done)
        if not total:
            self.label.setText(tr("dl_progress_unknown", done=_size(done)))
            return
        self.mosaic.set_progress(min(done / total, 1.0))
        text = tr("dl_progress", done=_size(done), total=_size(total), pct=done * 100 // total)
        if speed > 0 and done < total:
            text += tr("dl_speed", speed=_size(speed), left=_duration((total - done) / speed))
        elif done >= total:
            text = tr("dl_verifying")
        self.label.setText(text)

    def _finish(self, error) -> None:
        self._running, self.error = False, error
        if error is None:
            super().accept()
        else:
            super().reject()

    def reject(self):
        """Cancel and close: the worker notices between chunks and keeps the .part to resume."""
        if self._running:
            self._cancel.set()
            self.cancel.setEnabled(False)
            self.label.setText(tr("dl_cancelled"))
        else:
            super().reject()


class ModelErrorDialog(Window):
    """What went wrong with the model, and what can be done: ``options`` are (choice, label),
    the last one the default. ``choice`` is "quit" unless another button was pressed."""

    def __init__(self, text, options, parent=None):
        super().__init__(parent)
        self.choice = "quit"
        self.setWindowTitle(tr("model_problem"))
        self.setFixedWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(QLabel(text, wordWrap=True))
        buttons = QHBoxLayout()
        buttons.addWidget(QPushButton(tr("quit"), objectName="ghost", clicked=self.reject))
        buttons.addStretch()
        for i, (choice, label) in enumerate(options):
            last = i == len(options) - 1
            button = QPushButton(label, objectName="" if last else "ghost", default=last)
            button.clicked.connect(lambda _=False, c=choice: self._pick(c))
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self.accept()
