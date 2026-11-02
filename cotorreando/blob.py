"""The floating blob: a frameless, always-on-top window that reacts to your voice.

Visual states
-------------
disabled   soft grey disc, no animation at all
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
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

# Window size and orb radius in pixels for each size the user can pick. The
# window is much larger than the orb to leave room for ripples and the drag
# trail; its transparent pixels let clicks through.
SIZES = {"small": (110, 13), "medium": (170, 20), "large": (250, 30)}
GOO_STIFFNESS, GOO_DAMPING = 60.0, 7.0   # the sticky tail: softer than the drag spring
POINTS = 72
STIFFNESS, DAMPING = 220.0, 16.0   # spring used while dragging
ACCENT = QColor(64, 196, 255)
# (hue, orbit radius, feather size) relative to the radius, drifting inside the orb.
CLOUDS = ((320, 0.45, 0.75), (200, 0.35, 0.85), (140, 0.5, 0.7), (265, 0.3, 0.6), (45, 0.55, 0.45))
GREY = QColor(128, 128, 134)
EDGE_FADE = 0.8      # share of the way from the outline to the centre spent fading in
MIN_RINGS = 24


class Blob(QWidget):
    moved = Signal(int, int)
    menu_requested = Signal(object)

    def __init__(self, size: str = "medium"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.set_size(size)
        self.enabled = True
        self.writing = False
        self.loading: float | None = None   # None, -1 = busy, 0..1 = progress
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
        self._tail = QPointF()      # where the gooey tail lags behind, relative to the centre
        self._tail_vel = QPointF()
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._timer.start()

    # -- state ----------------------------------------------------------------

    def set_size(self, name: str) -> None:
        self.side, self.radius = SIZES.get(name, SIZES["medium"])
        self.setFixedSize(self.side, self.side)
        self.update()

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.level = self._target_level = 0.0
        self.ripples.clear()
        self._wake()

    def set_loading(self, progress: float | None) -> None:
        """Show a spinning ring while the model loads; ``progress`` 0..1 fills it."""
        self.loading = progress
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
            x, y = screen.right() - self.side - 40, screen.bottom() - self.side - 40
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
        if not self.enabled and not moving and not self.writing and self.loading is None:
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
        """Move the window towards the target; returns False once all is at rest."""
        delta = self._target - self._pos
        tail_moving = _norm(self._tail) > 0.3 or _norm(self._tail_vel) > 3
        if self._drag_offset is None and _norm(delta) < 0.5 and _norm(self._vel) < 5 \
                and not tail_moving:
            return False
        accel = delta * STIFFNESS - self._vel * DAMPING
        self._vel += accel * dt
        step = self._vel * dt
        self._pos += step
        self.move(round(self._pos.x()), round(self._pos.y()))
        # The tail stays where it was in the world, then is pulled back like goo.
        self._tail -= step
        self._tail_vel += (-self._tail * GOO_STIFFNESS - self._tail_vel * GOO_DAMPING) * dt
        self._tail += self._tail_vel * dt
        limit = self.side / 2 - self.radius - 4
        if _norm(self._tail) > limit:
            self._tail *= limit / _norm(self._tail)
        return True

    # -- painting -------------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.side / 2, self.side / 2)
        t = time.monotonic() - self._t0

        if not self.enabled and not self.writing:
            layer = self._layer()
            layer.fill(GREY.rgba())
            self._fade_edges(layer, self._shape(c, self.radius, t, 0.0), c)
            p.drawImage(0, 0, layer)
            if self.loading is not None:
                self._paint_loading(p, c, t)
            return

        for birth in self.ripples:
            age = (time.monotonic() - birth) / 1.4
            color = QColor.fromHsv(int(200 + self._hue + age * 120) % 360, 220, 255)
            color.setAlphaF(max(0.0, 0.55 * math.sin(math.pi * age)))   # born and gone invisible
            p.setPen(QPen(color, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self._shape(c, self.radius * (1 + age * 1.4), t, 0.4))

        layer = self._layer()
        self._paint_orb(layer, c)
        self._fade_edges(layer, self._shape(c, self.radius, t, 1.0), c)
        p.drawImage(0, 0, layer)

    def _layer(self) -> QImage:
        ratio = self.devicePixelRatioF()
        layer = QImage(round(self.side * ratio), round(self.side * ratio), QImage.Format_ARGB32_Premultiplied)
        layer.setDevicePixelRatio(ratio)
        layer.fill(Qt.transparent)
        return layer

    def _fade_edges(self, layer: QImage, path: QPainterPath, c: QPointF) -> None:
        """Fades ``layer`` to nothing exactly on the outline, whatever shape it has.

        The mask is the outline shrunk towards the centre, ring after ring, so
        the opacity depends on how far along the way to the edge a pixel is.
        """
        mask = self._layer()
        p = QPainter(mask)
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.setPen(Qt.NoPen)
        rings = max(self.radius, MIN_RINGS)
        for k in range(1, rings):
            scale = 1 - k / rings
            p.resetTransform()
            p.translate(c)
            p.scale(scale, scale)
            p.translate(-c)
            p.setBrush(QColor(0, 0, 0, round(255 * _edge_curve(k / rings))))
            p.drawPath(path)
        p.end()
        p = QPainter(layer)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(0, 0, mask)
        p.end()

    def _paint_loading(self, p: QPainter, c: QPointF, t: float) -> None:
        """A ring around the bubble: spinning while busy, filling while downloading."""
        r = self.radius + 5
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        track = QColor(GREY)
        track.setAlphaF(0.35)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(track, 3))
        p.drawEllipse(rect)
        pen = QPen(QColor.fromHsv(int(t * 60) % 360, 200, 255), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        if self.loading >= 0:
            p.drawArc(rect, 90 * 16, -int(360 * 16 * self.loading))
        else:
            p.drawArc(rect, -int(t * 300 * 16) % (360 * 16), 90 * 16)

    def _paint_orb(self, layer: QImage, c: QPointF) -> None:
        """A translucent glass bubble with glowing colour clouds drifting inside it."""
        shift = self._hue if self.writing else 0.0
        # An even fill: _fade_edges gives it its shape, sticky tail included.
        layer.fill(QColor.fromHsv(int(220 + shift) % 360, 215, 200, 170))
        p = QPainter(layer)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        glow = 0.75 + 0.25 * self.level
        for i, (hue, orbit, size) in enumerate(CLOUDS):
            a = self._drift * (0.6 + 0.17 * i) + i * 2.1
            pos = c + QPointF(math.cos(a), math.sin(a * 1.3)) * self.radius * orbit
            color = QColor.fromHsv(int(hue + shift) % 360, 255, 255)
            g = QRadialGradient(pos, self.radius * size)
            color.setAlphaF(glow * 0.45)   # a faint halo behind each feather
            g.setColorAt(0, color)
            color.setAlphaF(0)
            g.setColorAt(1, color)
            p.setBrush(g)
            p.drawEllipse(pos, self.radius * size, self.radius * size)
            # Each feather drifts along its orbit, turning and swaying gently.
            angle = math.degrees(a) * 0.5 + 25 * math.sin(self._drift * 1.7 + i)
            color.setAlphaF(glow)
            _feather(p, pos, angle, self.radius * size * 1.5, color)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        gloss_at = c + QPointF(-self.radius * 0.4, -self.radius * 0.45)
        gloss = QRadialGradient(gloss_at, self.radius * 0.55)
        gloss.setColorAt(0, QColor(255, 255, 255, 90))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(gloss)
        p.drawEllipse(gloss_at, self.radius * 0.55, self.radius * 0.55)
        p.end()

    def _shape(self, c: QPointF, radius: float, t: float, gain: float) -> QPainterPath:
        """A closed wobbly curve; amplitude grows with voice level."""
        amp = (0.03 + 0.28 * self.level) * gain
        tail = self._tail * (radius / self.radius)
        length = _norm(tail)
        direction = tail / length if length > 0.5 else QPointF()
        path = QPainterPath()
        for i in range(POINTS + 1):
            a = 2 * math.pi * i / POINTS
            wobble = (math.sin(3 * a + t * 2.1) * 0.5 + math.sin(5 * a - t * 3.3) * 0.3
                      + math.sin(7 * a + t * 5.0) * 0.2)
            r = radius * (1 + amp * wobble)
            dx, dy = math.cos(a), math.sin(a)
            # The side facing the tail is pulled out into a sticky, tapering drop;
            # the leading side flattens slightly as if pushing through syrup.
            facing = dx * direction.x() + dy * direction.y()
            pull = max(facing, 0.0) ** 3
            r *= 1 - 0.12 * max(-facing, 0.0) * min(length / radius, 1.0)
            pt = QPointF(c.x() + dx * r + tail.x() * pull, c.y() + dy * r + tail.y() * pull)
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


def _feather(p: QPainter, pos: QPointF, angle: float, length: float, color: QColor) -> None:
    """A bird feather drawn from scratch: curved shaft, tapered vane and barbs.

    It glows in ``color`` at the quill end and fades out towards the tip.
    """
    p.save()
    p.translate(pos)
    p.rotate(angle)
    p.translate(0, length / 2)   # the feather is centred on ``pos``, tip pointing up

    def shaft(u: float) -> QPointF:
        return QPointF(length * 0.08 * math.sin(math.pi * u), -length * u)

    def width(u: float) -> float:
        # The vane starts above the bare quill and is rounded at both ends.
        v = (u - 0.18) / 0.82
        return length * 0.11 * math.sin(math.pi * v) ** 0.5 if 0 < v < 1 else 0.0

    steps = 24
    # Feathers are asymmetric: one side of the vane is narrower than the other.
    left = [shaft(k / steps) + QPointF(-0.75 * width(k / steps), 0) for k in range(steps + 1)]
    right = [shaft(k / steps) + QPointF(width(k / steps), 0) for k in range(steps + 1)]
    vane = QPainterPath(left[0])
    for pt in left[1:] + right[::-1]:
        vane.lineTo(pt)
    vane.closeSubpath()

    fill = QLinearGradient(QPointF(0, 0), QPointF(0, -length))
    solid, clear = QColor(color), QColor(color)
    solid.setAlphaF(color.alphaF() * 0.8)
    clear.setAlphaF(0)
    fill.setColorAt(0.1, solid)
    fill.setColorAt(1, clear)
    p.setPen(Qt.NoPen)
    p.setBrush(fill)
    p.drawPath(vane)

    # Barbs angle up towards the tip, and the shaft runs down the middle.
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(fill, max(0.6, length * 0.012)))
    for k in range(5, steps, 2):
        u = k / steps
        base, w = shaft(u), width(u)
        for side, scale in ((-1, 0.75), (1, 1.0)):
            p.drawLine(base, base + QPointF(side * w * scale, -w * 0.7))
    spine = QPainterPath(shaft(0))
    for k in range(1, steps + 1):
        spine.lineTo(shaft(k / steps))
    p.setPen(QPen(fill, max(0.8, length * 0.025)))
    p.drawPath(spine)
    p.restore()


def _edge_curve(depth: float) -> float:
    """Opacity at ``depth`` from the outline (0) to the centre (1): starts flat, so no edge shows."""
    u = min(depth / EDGE_FADE, 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


def _norm(v: QPointF) -> float:
    return math.hypot(v.x(), v.y())
