"""Draws the installer's still background: the bubble's feathers, on the windows' colour.
Next to it writes palette.iss, the colours installer.iss includes, from cotorreando/palette.py.

Run by build.ps1. Usage: python scripts/installer_art.py <output.bmp>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient

from cotorreando import palette
from cotorreando.blob import _feather

WIDTH, HEIGHT = 1440, 920  # twice the window, so it stays sharp on scaled screens
BACKGROUND = QColor(palette.BACKGROUND)
# (plumage colour, x, y, angle, length, strength): gathered on the right, away from the text.
FEATHERS = (
    (palette.MINT, 1120, 300, 28, 620, 0.62),
    (palette.GREEN, 1290, 520, -22, 700, 0.66),
    (palette.LIME, 1010, 660, 50, 520, 0.48),
    (palette.ORANGE, 1340, 180, 62, 470, 0.5),
    (palette.RED, 1180, 780, -58, 400, 0.4),
    (palette.YELLOW, 860, 180, -35, 300, 0.22),
)
# installer.iss name -> colour. Inno Setup takes colours as $BBGGRR.
ISS_COLOURS = {
    "WINDOW_BACK": palette.BACKGROUND,
    "CAPTION_TEXT": palette.MUTED,
    "TITLE_TEXT": palette.TITLE,
    "BODY_TEXT": palette.BODY,
    "CLOSE_TEXT": palette.SECONDARY,
    "LINK_TEXT": palette.LINK,
}


def iss_colour(hex_colour: str) -> str:
    r, g, b = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    return f"${b}{g}{r}".upper()


def main(path: str) -> None:
    image = QImage(WIDTH, HEIGHT, QImage.Format_RGB32)
    image.fill(BACKGROUND)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    for colour, x, y, angle, length, strength in FEATHERS:
        pos = QPointF(x, y)
        color = QColor(colour)
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
    lines = [f'#define {name} "{iss_colour(c)}"' for name, c in ISS_COLOURS.items()]
    header = "; Written by scripts/installer_art.py from cotorreando/palette.py"
    (Path(path).parent / "palette.iss").write_text("\n".join([header, *lines, ""]), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
