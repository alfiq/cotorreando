"""Draws the installer's still background: the bubble's feathers, on the windows' colour.

Run by build.ps1. Usage: python scripts/installer_art.py <output.bmp>
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient

from cotorreando.blob import _feather

WIDTH, HEIGHT = 1440, 920     # twice the window, so it stays sharp on scaled screens
BACKGROUND = QColor("#16171b")
# (hue, x, y, angle, length, strength): gathered on the right, away from the text.
FEATHERS = ((320, 1120, 300, 28, 620, 0.62), (200, 1290, 520, -22, 700, 0.66),
            (140, 1010, 660, 50, 520, 0.48), (265, 1340, 180, 62, 470, 0.5),
            (45, 1180, 780, -58, 400, 0.4), (200, 860, 180, -35, 300, 0.22))


def main(path: str) -> None:
    image = QImage(WIDTH, HEIGHT, QImage.Format_RGB32)
    image.fill(BACKGROUND)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for hue, x, y, angle, length, strength in FEATHERS:
        pos = QPointF(x, y)
        color = QColor.fromHsv(hue, 235, 255)
        halo = QRadialGradient(pos, length * 0.65)
        color.setAlphaF(strength * 0.22)
        halo.setColorAt(0, color)
        color.setAlphaF(0)
        halo.setColorAt(1, color)
        p.setBrush(halo)
        p.drawRect(image.rect())
        color.setAlphaF(strength)
        _feather(p, pos, angle, length, color)
    p.end()
    if not image.save(path, "BMP"):
        raise SystemExit(f"Could not write {path}")


if __name__ == "__main__":
    main(sys.argv[1])
