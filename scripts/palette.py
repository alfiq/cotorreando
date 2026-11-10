"""Draws docs/assets/paleta.png, the palette sheet of docs/IDENTIDAD.md: each colour with its
name, hex value and WCAG contrast against the windows' background.

    python scripts/palette.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

W, SCALE = 1200, 2                  # drawn at twice the size, for sharp text on high-DPI screens
BACKGROUND, TITLE, MUTED = QColor("#161b17"), QColor("#f3f6f4"), QColor("#8b998e")
DARK_TEXT, LIGHT_TEXT = QColor("#0b1a10"), QColor("#ffffff")
COLUMNS, SWATCH_H, GAP, MARGIN = 6, 120, 16, 48
GROUPS = (
    ("Plumaje (assets/parrot.png)", (
        ("Verde cotorra", "#22b14c"), ("Menta", "#54d7a3"), ("Oliva", "#629a1f"), ("Lima", "#b5e61d"),
        ("Amarillo", "#fff200"), ("Naranja", "#ff7f27"), ("Rojo teja", "#cb4426"), ("Rojo", "#ed1c24"),
        ("Granate", "#9f1d29"), ("Rosa", "#ffaec9"), ("Marrón", "#64442b"), ("Pico", "#000000"))),
    ("Interfaz (dialogs.py)", (
        ("Fondo", "#161b17"), ("Tarjeta", "#1d241f"), ("Campo", "#252d27"), ("Texto", "#e8ece9"),
        ("Título", "#f3f6f4"), ("Cuerpo", "#b6c2b9"), ("Secundario", "#a4b0a7"), ("Nota", "#8b998e"),
        ("Texto en botón", "#0b1a10"), ("Botón hover", "#2cc45a"), ("Botón pulsado", "#1d9a42"),
        ("Borde casilla", "#6b7a6f"))),
    ("Insignias del README (texto blanco)", (
        ("Licencia", "#157f35"), ("Windows", "#0f6b4a"), ("Privacidad", "#5a7d0e"), ("Versión", "#cb4426"))),
)


def luminance(c: QColor) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(c.redF()) + 0.7152 * channel(c.greenF()) + 0.0722 * channel(c.blueF())


def contrast(a: QColor, b: QColor) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 - fonts need it
    width = (W - 2 * MARGIN - (COLUMNS - 1) * GAP) / COLUMNS
    rows = sum(-(-len(colours) // COLUMNS) for _, colours in GROUPS)
    height = MARGIN * 2 + len(GROUPS) * 56 + rows * (SWATCH_H + GAP)
    image = QImage(W * SCALE, height * SCALE, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(SCALE, SCALE)
    card = QPainterPath()
    card.addRoundedRect(QRectF(0, 0, W, height), 24, 24)
    p.fillPath(card, BACKGROUND)
    y = MARGIN
    for title, colours in GROUPS:
        p.setPen(TITLE)
        p.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        p.drawText(QRectF(MARGIN, y, W, 40), Qt.AlignLeft | Qt.AlignVCenter, title)
        y += 56
        for i, (name, hex_value) in enumerate(colours):
            x = MARGIN + (i % COLUMNS) * (width + GAP)
            top = y + (i // COLUMNS) * (SWATCH_H + GAP)
            color = QColor(hex_value)
            swatch = QPainterPath()
            swatch.addRoundedRect(QRectF(x, top, width, SWATCH_H), 12, 12)
            p.fillPath(swatch, color)
            if hex_value == BACKGROUND.name():
                p.setPen(QColor("#303a32"))
                p.drawPath(swatch)
            ink = max((DARK_TEXT, LIGHT_TEXT), key=lambda c: contrast(c, color))
            p.setPen(ink)
            p.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
            p.drawText(QRectF(x + 12, top + 10, width - 24, 24), Qt.AlignLeft, name)
            p.setFont(QFont("Consolas", 11))
            p.drawText(QRectF(x + 12, top + 36, width - 24, 24), Qt.AlignLeft, hex_value)
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(x + 12, top + SWATCH_H - 54, width - 24, 20), Qt.AlignLeft,
                       f"{contrast(ink, color):.1f}:1 con {'texto oscuro' if ink == DARK_TEXT else 'blanco'}")
            p.drawText(QRectF(x + 12, top + SWATCH_H - 32, width - 24, 20), Qt.AlignLeft,
                       f"{contrast(color, BACKGROUND):.1f}:1 sobre el fondo")
        y += -(-len(colours) // COLUMNS) * (SWATCH_H + GAP)
    p.setPen(MUTED)
    p.setFont(QFont("Segoe UI", 9))
    p.drawText(QRectF(MARGIN, height - MARGIN + 8, W - 2 * MARGIN, 24), Qt.AlignLeft,
               "Contraste WCAG 2.x. Texto: 4,5:1 como mínimo; texto grande y controles: 3:1. Fondo: #161b17.")
    p.end()
    out = ROOT / "docs" / "assets" / "paleta.png"
    image.save(str(out))
    print(out)


if __name__ == "__main__":
    main()
