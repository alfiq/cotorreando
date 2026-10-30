"""The floating blob: a frameless, always-on-top window that reacts to your voice.

Visual states
-------------
disabled   flat grey disc, no animation at all
idle       soft accent colour, slow breathing
speaking   surface wobbles with the voice level and ripples spread outwards
writing    iridescent (rotating hue) fill while text is being typed
Speaking and writing combine freely.

Dragging moves a target point; the window follows it through a damped
spring, which gives the elastic feel and a squash in the direction of motion.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

SIZE = 96
RADIUS = 20
POINTS = 72
STIFFNESS, DAMPING = 220.0, 16.0   # spring used while dragging
ACCENT = QColor(64, 196, 255)
# (hue, orbit radius, cloud size) relative to RADIUS, drifting inside the orb.
CLOUDS = ((320, 0.45, 0.75), (200, 0.35, 0.85), (140, 0.5, 0.7), (265, 0.3, 0.6), (45, 0.55, 0.45))
GREY = QColor(128, 128, 134)


class Blob(QWidget):
    moved = Signal(int, int)
    menu_requested = Signal(object)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(SIZE, SIZE)
        self.enabled = True
        self.writing = False
        self.level = 0.0          # smoothed 0..1
        self._target_level = 0.0
        self.ripples: list[float] = []   # birth times
        self._last_ripple = 0.0
        self._hue = 0.0
        self._drift = 0.0          # accumulated phase of the inner colour clouds
        self._t0 = time.monotonic()
        self._last_tick = self._t0
        # Spring state for elastic dragging.
        self._drag_offset: QPointF | None = None
        self._pos = QPointF()
        self._vel = QPointF()
        self._target = QPointF()
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._timer.start()

    # -- state ----------------------------------------------------------------

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.level = self._target_level = 0.0
        self.ripples.clear()
        self._wake()

    def set_writing(self, on: bool) -> None:
        self.writing = on
        self._wake()

    def set_level(self, db: float, threshold: float, voiced: bool) -> None:
        """Voice level in dBFS mapped to 0..1 above the threshold."""
        span = max(-10.0 - threshold, 10.0)
        self._target_level = min(max((db - threshold) / span, 0.0), 1.0) if voiced else 0.0
        if voiced and self._target_level > 0.25 and time.monotonic() - self._last_ripple > 0.35:
            self._last_ripple = time.monotonic()
            self.ripples.append(self._last_ripple)

    def place(self, x: int, y: int) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        if x < 0 or y < 0:
            x, y = screen.right() - SIZE - 40, screen.bottom() - SIZE - 40
        self._pos = self._target = QPointF(x, y)
        self.move(x, y)

    def _wake(self) -> None:
        if not self._timer.isActive():
            self._last_tick = time.monotonic()
            self._timer.start()
        self.update()

    # -- animation ------------------------------------------------------------

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.05)
        self._last_tick = now

        moving = self._step_spring(dt)
        if not self.enabled and not moving and not self.writing:
            self._timer.stop()     # disabled and still: no CPU spent at all
            self.update()
            return
        self.level += (self._target_level - self.level) * min(dt * 6, 1)
        # Integrate the speed so the clouds never jump when the level changes.
        self._drift += dt * (0.35 + 0.5 * self.level)
        self.ripples = [b for b in self.ripples if now - b < 1.4]
        if self.writing:
            self._hue = (self._hue + dt * 140) % 360
        self.update()

    def _step_spring(self, dt: float) -> bool:
        delta = self._target - self._pos
        if self._drag_offset is None and abs(delta.x()) + abs(delta.y()) < 0.5 \
                and abs(self._vel.x()) + abs(self._vel.y()) < 5:
            return False
        accel = delta * STIFFNESS - self._vel * DAMPING
        self._vel += accel * dt
        self._pos += self._vel * dt
        self.move(round(self._pos.x()), round(self._pos.y()))
        return True

    # -- painting -------------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(SIZE / 2, SIZE / 2)
        t = time.monotonic() - self._t0

        if not self.enabled and not self.writing:
            p.setPen(QPen(GREY.darker(130), 1.5))
            p.setBrush(GREY)
            p.drawEllipse(c, RADIUS, RADIUS)
            return

        for birth in self.ripples:
            age = (time.monotonic() - birth) / 1.4
            color = QColor.fromHsv(int(200 + self._hue + age * 120) % 360, 220, 255)
            color.setAlphaF(0.55 * (1 - age))
            p.setPen(QPen(color, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self._shape(c, RADIUS + age * (SIZE / 2 - RADIUS - 4), t, 0.4))

        path = self._shape(c, RADIUS, t, 1.0)
        self._paint_orb(p, c, path, t)

    def _paint_orb(self, p: QPainter, c: QPointF, path: QPainterPath, t: float) -> None:
        """A translucent glass bubble with glowing colour clouds drifting inside it."""
        shift = self._hue if self.writing else 0.0
        p.setPen(Qt.NoPen)
        body = QRadialGradient(c, RADIUS * 1.1)
        body.setColorAt(0, QColor.fromHsv(int(220 + shift) % 360, 200, 120, 60))
        body.setColorAt(1, QColor.fromHsv(int(220 + shift) % 360, 230, 200, 170))
        p.fillPath(path, body)
        p.setClipPath(path)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        glow = 0.75 + 0.25 * self.level
        for i, (hue, orbit, size) in enumerate(CLOUDS):
            a = self._drift * (0.6 + 0.17 * i) + i * 2.1
            pos = c + QPointF(math.cos(a), math.sin(a * 1.3)) * RADIUS * orbit
            color = QColor.fromHsv(int(hue + shift) % 360, 255, 255)
            g = QRadialGradient(pos, RADIUS * size)
            color.setAlphaF(glow)
            g.setColorAt(0, color)
            color.setAlphaF(0)
            g.setColorAt(1, color)
            p.setBrush(g)
            p.drawEllipse(pos, RADIUS * size, RADIUS * size)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setClipping(False)
        # The rim is drawn along the deformed outline so it bends with the voice.
        rim = QConicalGradient(c, self._drift * 40)
        for i in range(7):
            rim.setColorAt(i / 6, QColor.fromHsv(int(shift + i * 60) % 360, 230, 255, 220))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(rim, 1.5))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        gloss = QRadialGradient(c + QPointF(-RADIUS * 0.4, -RADIUS * 0.45), RADIUS * 0.55)
        gloss.setColorAt(0, QColor(255, 255, 255, 90))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gloss)
        p.drawPath(path)

    def _shape(self, c: QPointF, radius: float, t: float, gain: float) -> QPainterPath:
        """A closed wobbly curve; amplitude grows with voice level."""
        amp = (0.03 + 0.28 * self.level) * gain
        stretch = self._vel * 0.0006
        path = QPainterPath()
        for i in range(POINTS + 1):
            a = 2 * math.pi * i / POINTS
            wobble = (math.sin(3 * a + t * 2.1) * 0.5 + math.sin(5 * a - t * 3.3) * 0.3
                      + math.sin(7 * a + t * 5.0) * 0.2)
            r = radius * (1 + amp * wobble)
            dx, dy = math.cos(a), math.sin(a)
            # Squash and stretch along the drag velocity.
            along = dx * stretch.x() + dy * stretch.y()
            pt = QPointF(c.x() + dx * r + stretch.x() * along * r, c.y() + dy * r + stretch.y() * along * r)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        return path

    # -- mouse ----------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition() - self._pos
            self._wake()
        elif e.button() == Qt.RightButton:
            self.menu_requested.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None:
            self._target = e.globalPosition() - self._drag_offset

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.moved.emit(round(self._target.x()), round(self._target.y()))
