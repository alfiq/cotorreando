"""The logo: the hand-drawn parrot, one glazed tile per pixel, no anti-aliasing."""

from __future__ import annotations

import random

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .paths import PACKAGE_DIR

SOURCE = PACKAGE_DIR / "assets" / "parrot.png"


def _tile(p: QPainter, x: int, y: int, size: int, color: QColor) -> None:
    """A tile with raised edges: light on top and left, shadow on the bottom and right."""
    side, edge = size - 1, max(size // 6, 1)
    p.fillRect(x, y, side, side, color)
    p.fillRect(x, y, side, edge, color.lighter(135))
    p.fillRect(x, y, edge, side, color.lighter(120))
    p.fillRect(x, y + side - edge, side, edge, color.darker(150))
    p.fillRect(x + side - edge, y, edge, side, color.darker(130))


def _background(image: QImage) -> set[tuple[int, int]]:
    """The white paper around the drawing: white pixels connected to the border."""
    w, h = image.width(), image.height()
    pending = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    seen: set[tuple[int, int]] = set()
    while pending:
        x, y = pending.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h):
            continue
        color = image.pixelColor(x, y)
        if color.alpha() > 127 and color.lightness() < 245:
            continue
        seen.add((x, y))
        pending += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return seen


class Mosaic(QWidget):
    """Draws the logo. ``set_progress`` lays the tiles one by one, in a fixed random order."""

    def __init__(self, tile: int = 6, progress: float = 1.0, parent=None):
        super().__init__(parent)
        image = QImage(str(SOURCE)).convertToFormat(QImage.Format_ARGB32)
        self.tile, self.progress = tile, progress
        hidden = _background(image)
        self.cells = [
            (x, y, image.pixelColor(x, y))
            for y in range(image.height())
            for x in range(image.width())
            if (x, y) not in hidden
        ]
        random.Random(32).shuffle(self.cells)
        self.setFixedSize(QSize(image.width(), image.height()) * tile)

    def set_progress(self, progress: float) -> None:
        self.progress = progress
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        laid = round(len(self.cells) * self.progress)
        for i, (x, y, color) in enumerate(self.cells):
            if i >= laid:
                grey = color.lightness() // 5 + 34
                color = QColor(grey, grey, grey + 3)
            _tile(p, x * self.tile, y * self.tile, self.tile, color)
        p.end()


def logo_pixmap(tile: int = 6) -> QPixmap:
    mosaic = Mosaic(tile)
    pixmap = QPixmap(mosaic.size())
    pixmap.fill(QColor(0, 0, 0, 0))
    mosaic.render(pixmap, renderFlags=QWidget.RenderFlag.DrawChildren)  # no window background
    return pixmap
