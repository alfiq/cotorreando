"""Draws the app icon from the parrot: cotorreando/icon.ico (every size Windows asks for)
and cotorreando/icon.png (256 px).

    python scripts/icon.py

At 256 px it uses the glazed tiles of the logo (mosaic.py); below that the gaps between
tiles wash the colours out, so it uses the drawing's own pixels.
"""

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cotorreando.mosaic import SOURCE, _background, logo_pixmap  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def pixel_art() -> QImage:
    """The drawing itself, with the white paper around it made transparent."""
    image = QImage(str(SOURCE)).convertToFormat(QImage.Format_ARGB32)
    for x, y in _background(image):
        image.setPixelColor(x, y, QColor(0, 0, 0, 0))
    return image


def render(size: int, art: QImage) -> QImage:
    if size < 256:
        source = art
    else:
        tile = max(size // art.width(), 2)
        source = logo_pixmap(tile).toImage()
    mode = Qt.FastTransformation if size % art.width() == 0 else Qt.SmoothTransformation
    scaled = source.scaled(size, size, Qt.KeepAspectRatio, mode)
    out = QImage(size, size, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[QImage]) -> None:
    """An ICO whose entries are PNGs, which Windows Vista and later read at every size."""
    blobs = [png_bytes(i) for i in images]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = len(header) + 16 * len(blobs)
    entries = b""
    for image, blob in zip(images, blobs):
        side = image.width() if image.width() < 256 else 0      # 0 means 256
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + entries + b"".join(blobs))


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 - pixmaps need it
    art = pixel_art()
    images = [render(size, art) for size in SIZES]
    write_ico(ROOT / "cotorreando" / "icon.ico", images)
    images[-1].save(str(ROOT / "cotorreando" / "icon.png"))


if __name__ == "__main__":
    main()
