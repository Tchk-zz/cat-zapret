"""Power button and its shimmer plate."""
from __future__ import annotations

import math
from typing import Optional
from PyQt6.QtCore import Qt, QVariantAnimation, QRectF, QPointF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QWidget


class _ShimmerPlate(QWidget):
    """Matte frosted plate placed behind the power button. A soft multi-colour
    gradient slowly drifts across it so the backing gently "\u043f\u0435\u0440\u0435\u043b\u0438\u0432\u0430\u0435\u0442\u0441\u044f"."""

    def __init__(self, size: int = 200, radius: int = 46, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._phase = 0.0
        self._running = False
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(6000)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_phase)
        self._anim.start()

    def _on_phase(self, value) -> None:
        try:
            self._phase = float(value)
        except (TypeError, ValueError):
            self._phase = 0.0
        self.update()

    def set_running(self, running: bool) -> None:
        self._running = bool(running)
        self.update()

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, float(self._radius), float(self._radius))
        painter.setClipPath(path)
        # 1) Matte translucent base.
        painter.fillRect(rect, QColor(255, 255, 255, 16))
        # 2) Slowly drifting shimmer: green family when running, red when off.
        p = self._phase
        base_hue = 135 if self._running else 358
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        stops = 6
        for j in range(stops + 1):
            t = j / stops
            hue = int(base_hue + 22 * math.sin(2 * math.pi * (t + p))) % 360
            val = max(150, min(255, int(225 + 30 * math.sin(2 * math.pi * (t + p) + 1.0))))
            grad.setColorAt(t, QColor.fromHsv(hue, 175, val, 90))
        painter.fillRect(rect, grad)
        # 3) Soft top highlight for the glassy feel.
        sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 42))
        sheen.setColorAt(0.4, QColor(255, 255, 255, 0))
        painter.fillRect(rect, sheen)
        # Edges deliberately fill the full widget rect so the plate contour
        # coincides exactly with the power button (both 160px / radius 32).
        painter.end()


class PowerButton(QPushButton):
    """Round power button that paints its own frosted gradient backing, the
    contour around it, and the IEC power glyph.

    The gradient "plate" is painted by the button itself (not a separate
    widget behind it), so the gradient backing and the contour are always the
    same rounded rect -- there can never be a gap between them. The gradient
    slowly drifts and is green while running / red while stopped.

    Relying on a font glyph (U+23FB) is unreliable -- many Windows machines
    have no font covering it -- so we draw the symbol with QPainter.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._phase = 0.0
        self._running = False
        # Theme colour overrides. None = use default (green/purple).
        self._running_color: Optional[str] = None
        self._stopped_color: Optional[str] = None
        self._running_hue: Optional[int] = None
        self._stopped_hue: Optional[int] = None
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(6000)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_phase)
        self._anim.start()

    def _on_phase(self, value) -> None:
        try:
            self._phase = float(value)
        except (TypeError, ValueError):
            self._phase = 0.0
        self.update()

    def set_running(self, running: bool) -> None:
        self._running = bool(running)
        self.update()

    def set_theme_colors(self, running_color=None, stopped_color=None, running_hue=None, stopped_hue=None):
        self._running_color = running_color
        self._stopped_color = stopped_color
        self._running_hue = running_hue
        self._stopped_hue = stopped_hue
        self.update()

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 32.0
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # --- frosted gradient backing (the "plate"), painted by the button
        #     itself so it can never drift apart from the contour ---
        p.save()
        p.setClipPath(path)
        p.fillRect(rect, QColor(255, 255, 255, 9))
        if self._running and self._running_hue is not None:
            base_hue = self._running_hue
        elif not self._running and self._stopped_hue is not None:
            base_hue = self._stopped_hue
        else:
            base_hue = 135 if self._running else 358
        ph = self._phase
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        stops = 6
        # Dark-theme OFF state: animate only between bright red and deep red.
        # This avoids the previous red/orange hue swing and matches the
        # attached red-gradient reference more closely.
        if (not self._running) and self._stopped_hue == -1:
            for j in range(stops + 1):
                t = j / stops
                wave = (math.sin(2 * math.pi * (t + ph)) + 1.0) / 2.0
                red = int(105 + 150 * wave)
                grad.setColorAt(t, QColor(red, 0, 0, 78))
        else:
            for j in range(stops + 1):
                t = j / stops
                hue = int(base_hue + 22 * math.sin(2 * math.pi * (t + ph))) % 360
                val = max(150, min(255, int(225 + 30 * math.sin(2 * math.pi * (t + ph) + 1.0))))
                grad.setColorAt(t, QColor.fromHsv(hue, 175, val, 65))
        p.fillRect(rect, grad)
        sheen = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 26))
        sheen.setColorAt(0.4, QColor(255, 255, 255, 0))
        p.fillRect(rect, sheen)
        p.restore()

        # --- contour, drawn right on the edge of the gradient backing ---
        if self._running and self._running_color:
            border_col = QColor(self._running_color); border_col.setAlpha(170)
        elif not self._running and self._stopped_color:
            border_col = QColor(self._stopped_color); border_col.setAlpha(60)
        else:
            border_col = QColor(120, 240, 170, 170) if self._running else QColor(255, 255, 255, 60)
        bpen = QPen(border_col)
        bpen.setWidthF(1.5)
        p.setPen(bpen)
        p.drawPath(path)

        # --- IEC power glyph (original size) ---
        if self._running and self._running_color:
            color = QColor(self._running_color)
        elif not self._running and self._stopped_color:
            color = QColor(self._stopped_color)
        else:
            color = QColor("#8af0b0") if self._running else QColor("#d9ccff")
        side = float(min(self.width(), self.height()))
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        r = side * 0.23
        pen = QPen(color)
        pen.setWidthF(max(3.0, side * 0.05))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        # Open circle with a gap at the very top (centred on 90 degrees).
        arc = QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r)
        p.drawArc(arc, 118 * 16, 304 * 16)
        # Vertical bar passing through the gap.
        p.drawLine(QPointF(cx, cy - r * 1.18), QPointF(cx, cy - r * 0.08))
        p.end()
