"""Draws docs/assets/banner.png, the README's header: the tiled parrot and the name.

    python scripts/banner.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cotorreando import palette as P  # noqa: E402
from cotorreando.mosaic import logo_pixmap  # noqa: E402

W, H, SCALE = 1200, 300, 2          # drawn at twice the size, for sharp text on high-DPI screens
BACKGROUND, TITLE, TAGLINE = QColor(P.BACKGROUND), QColor(P.TITLE), QColor(P.LINK)
PLUMAGE = [QColor(c) for c in P.PLUMAGE]


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 - fonts and pixmaps need it
    image = QImage(W * SCALE, H * SCALE, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(SCALE, SCALE)
    card = QPainterPath()
    card.addRoundedRect(QRectF(0, 0, W, H), 24, 24)
    p.fillPath(card, BACKGROUND)
    p.setClipPath(card)
    stripe = W / len(PLUMAGE)         # the plumage along the bottom edge
    for i, color in enumerate(PLUMAGE):
        p.fillRect(QRectF(i * stripe, H - 10, stripe + 1, 10), color)
    logo = logo_pixmap(7 * SCALE)
    logo.setDevicePixelRatio(SCALE)
    p.drawPixmap(64, (H - 10 - logo.height() / SCALE) / 2, logo)
    left = 64 + logo.width() / SCALE + 56
    p.setPen(TITLE)
    p.setFont(QFont("Segoe UI", 54, QFont.DemiBold))
    p.drawText(QRectF(left, 60, W - left, 100), Qt.AlignLeft | Qt.AlignBottom, "Cotorreando")
    p.setPen(TAGLINE)
    p.setFont(QFont("Segoe UI", 21))
    p.drawText(QRectF(left, 172, W - left, 60), Qt.AlignLeft | Qt.AlignTop, "Dictado por voz para todo Windows")
    p.end()
    out = ROOT / "docs" / "assets" / "banner.png"
    image.save(str(out))
    print(out)


if __name__ == "__main__":
    main()
