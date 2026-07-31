"""Home tab widgets: 3D panels, buttons, auto-select panel, sleeping cat Z's."""
from __future__ import annotations

import math
from PyQt6.QtCore import Qt, QEasingCurve, QVariantAnimation, QRectF, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)
from .effects import apply_effect
from .i18n import tr_text


#: Fill of the reference (dark preset) card surface.
DEFAULT_SURFACE_FILL = "#1c1c1c"


def surface_fill_color(value) -> QColor:
    """Convert a stylesheet-style colour string into a QColor.

    Themes describe their card background exactly the way the stylesheets do:
    either "#rrggbb" or "rgba(r, g, b, a)" with a 0-255 alpha. QColor does not
    parse that second form, so it is handled here. Anything unparseable falls
    back to the reference dark fill rather than leaving the card invisible.
    """
    if isinstance(value, QColor):
        return QColor(value)
    text = str(value or "").strip()
    lowered = text.lower()
    if (lowered.startswith("rgba(") or lowered.startswith("rgb(")) and text.endswith(")"):
        inner = text[text.index("(") + 1: -1]
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        if len(parts) in (3, 4):
            try:
                r, g, b = (int(round(float(p))) for p in parts[:3])
                if len(parts) == 4:
                    raw_alpha = float(parts[3])
                    # Qt stylesheets use 0-255, CSS uses 0-1; accept both.
                    alpha = round(raw_alpha * 255) if raw_alpha <= 1.0 else round(raw_alpha)
                else:
                    alpha = 255
                clamp = lambda v: max(0, min(255, int(v)))  # noqa: E731
                return QColor(clamp(r), clamp(g), clamp(b), clamp(alpha))
            except ValueError:
                pass
    colour = QColor(text)
    return colour if colour.isValid() else QColor(DEFAULT_SURFACE_FILL)


def _paint_dark_3d_surface(
    widget, painter: QPainter, hovered: bool = False, pressed: bool = False, phase: float = 0.0,
    fill=None, light: bool = False,
) -> None:
    """Paint a solid card with an animated gradient rim.

    Every theme uses this same surface; only ``fill`` and the rim/highlight
    contrast differ. Previously it was painted for the dark preset only, so in
    every other theme the cards were invisible and their text floated directly
    on the background image.

    ``light`` inverts the rim and the inner highlight so the raised edge stays
    visible on light card fills, where a white highlight would disappear.
    """
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(widget.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
    radius = 20.0
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    # The surface itself is deliberately flat: no fill gradient or sheen.
    painter.fillPath(path, fill if isinstance(fill, QColor) else QColor(DEFAULT_SURFACE_FILL))

    # Rotate the rim palette around the card perimeter.
    rim = QConicalGradient(rect.center(), -360.0 * float(phase))
    if light:
        bright = QColor(96, 104, 118, 165 if hovered else 120)
        rim.setColorAt(0.0, bright)
        rim.setColorAt(0.38, QColor(140, 148, 162, 120))
        rim.setColorAt(0.72, QColor(112, 120, 134, 105))
        rim.setColorAt(0.90, QColor(60, 66, 76, 150))
        rim.setColorAt(1.0, bright)
    else:
        bright = QColor(155, 165, 180, 155 if hovered else 105)
        rim.setColorAt(0.0, bright)
        rim.setColorAt(0.38, QColor(84, 92, 105, 110))
        rim.setColorAt(0.72, QColor(49, 54, 63, 95))
        rim.setColorAt(0.90, QColor(12, 14, 18, 210))
        rim.setColorAt(1.0, bright)
    pen = QPen(QBrush(rim), 1.7)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    # Thin inner highlight along the upper edge adds the raised/3D feel.
    inner = QRectF(rect).adjusted(2.2, 2.2, -2.2, -2.2)
    inner_path = QPainterPath()
    inner_path.addRoundedRect(inner, radius - 2.0, radius - 2.0)
    if light:
        inner_pen = QPen(QColor(0, 0, 0, 30 if hovered else 20), 0.8)
    else:
        inner_pen = QPen(QColor(255, 255, 255, 22 if hovered else 13), 0.8)
    painter.setPen(inner_pen)
    painter.drawPath(inner_path)


class _Dark3DPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_3d = False
        self._hovered = False
        self._rim_phase = 0.0
        # Card fill; replaced per theme via set_surface_style().
        self._surface_fill = QColor(DEFAULT_SURFACE_FILL)
        self._surface_light = False
        self._rim_anim = QVariantAnimation(self)
        self._rim_anim.setStartValue(0.0)
        self._rim_anim.setEndValue(1.0)
        self._rim_anim.setDuration(4200)
        self._rim_anim.setLoopCount(-1)
        self._rim_anim.valueChanged.connect(self._on_rim_phase)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _on_rim_phase(self, value) -> None:
        self._rim_phase = float(value)
        self.update()

    def set_dark_3d(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled and not self._dark_3d:
            self._rim_anim.start()
        elif not enabled:
            self._rim_anim.stop()
            self._rim_phase = 0.0
        self._dark_3d = enabled
        self.update()

    def set_surface_style(self, fill, light: bool = False) -> None:
        """Set the card fill for the active theme.

        ``fill`` accepts the same colour strings the stylesheets use, so a
        theme's ``card_bg`` can be passed straight through.
        """
        self._surface_fill = surface_fill_color(fill)
        self._surface_light = bool(light)
        self.update()

    def enterEvent(self, event):  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        if not self._dark_3d:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        _paint_dark_3d_surface(
            self, painter, self._hovered, False, self._rim_phase,
            fill=self._surface_fill, light=self._surface_light,
        )
        painter.end()


class _Dark3DButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dark_3d = False
        self._hovered = False
        self._rim_phase = 0.0
        # Card fill; replaced per theme via set_surface_style().
        self._surface_fill = QColor(DEFAULT_SURFACE_FILL)
        self._surface_light = False
        self._rim_anim = QVariantAnimation(self)
        self._rim_anim.setStartValue(0.0)
        self._rim_anim.setEndValue(1.0)
        self._rim_anim.setDuration(4200)
        self._rim_anim.setLoopCount(-1)
        self._rim_anim.valueChanged.connect(self._on_rim_phase)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _on_rim_phase(self, value) -> None:
        self._rim_phase = float(value)
        self.update()

    def set_dark_3d(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled and not self._dark_3d:
            self._rim_anim.start()
        elif not enabled:
            self._rim_anim.stop()
            self._rim_phase = 0.0
        self._dark_3d = enabled
        self.update()

    def set_surface_style(self, fill, light: bool = False) -> None:
        """Set the card fill for the active theme.

        ``fill`` accepts the same colour strings the stylesheets use, so a
        theme's ``card_bg`` can be passed straight through.
        """
        self._surface_fill = surface_fill_color(fill)
        self._surface_light = bool(light)
        self.update()

    def enterEvent(self, event):  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        if not self._dark_3d:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        _paint_dark_3d_surface(
            self, painter, self._hovered, self.isDown(), self._rim_phase,
            fill=self._surface_fill, light=self._surface_light,
        )
        painter.end()


class _DarkAnimatedProgressBar(QProgressBar):
    """Dark progress bar with a looping #010101 -> #a9a9a9 shimmer.

    The soft halo around the bar is painted here by hand. It used to come from
    a QGraphicsDropShadowEffect, but QGraphicsEffect composites through an
    offscreen pixmap; at UI scales below 1 (Full HD, see ui/effects.py) that
    pixmap is undersized and the halo was clipped, which showed up as a torn
    edge on the right side of the bar. Painting it ourselves inside a padded
    widget keeps the glow and removes the artifact at any scale.
    """

    #: Free space reserved inside the widget so the halo has room to fade out.
    GLOW_PAD = 7.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self.setTextVisible(False)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1800)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._set_phase)
        self._anim.start()

    def _set_phase(self, value) -> None:
        self._phase = float(value)
        self.update()

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pad = self.GLOW_PAD
        rect = QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)
        radius = 5.0

        # Soft halo around the whole bar, drawn as a few widening strokes with
        # fading alpha. It stays inside the padded widget, so it never gets
        # cut off at the ends of the bar.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        layers = 6
        for i in range(layers, 0, -1):
            spread = pad * (i / layers)
            alpha = int(52 * (1.0 - (i - 1) / layers))
            if alpha <= 0:
                continue
            painter.setPen(QPen(QColor(190, 195, 210, alpha), 2.0))
            painter.drawRoundedRect(
                rect.adjusted(-spread, -spread, spread, spread),
                radius + spread,
                radius + spread,
            )

        painter.setPen(QPen(QColor(86, 88, 94, 210), 1.0))
        painter.setBrush(QColor(8, 8, 8, 245))
        painter.drawRoundedRect(rect, radius, radius)

        span = max(1, self.maximum() - self.minimum())
        fraction = max(0.0, min(1.0, (self.value() - self.minimum()) / span))
        if fraction <= 0.0:
            painter.end()
            return

        chunk = QRectF(rect)
        chunk.setWidth(max(radius * 2.0, rect.width() * fraction))
        chunk_path = QPainterPath()
        chunk_path.addRoundedRect(chunk, radius - 1.0, radius - 1.0)
        painter.save()
        painter.setClipPath(chunk_path)
        painter.fillRect(chunk, QColor("#010101"))

        shimmer_width = max(34.0, chunk.width() * 0.72)
        center = chunk.left() - shimmer_width + self._phase * (
            chunk.width() + 2.0 * shimmer_width
        )
        shimmer = QLinearGradient(center - shimmer_width, 0.0, center + shimmer_width, 0.0)
        shimmer.setColorAt(0.0, QColor("#010101"))
        shimmer.setColorAt(0.5, QColor("#a9a9a9"))
        shimmer.setColorAt(1.0, QColor("#010101"))
        painter.fillRect(chunk, shimmer)
        painter.restore()
        painter.end()


class _HomeAutoSelectPanel(_Dark3DPanel):
    """Embedded dark-theme autoselect progress panel for the Home page."""

    def __init__(self, owner=None):
        super().__init__(owner)
        self._owner = owner
        self._total = 1
        self.setObjectName("homeAutoSelectPanel")
        self.setStyleSheet("QFrame#homeAutoSelectPanel { background: transparent; border: none; }")
        self.setFixedHeight(175)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 16, 30, 14)
        # The progress bar carries 7 px of transparent padding on each side for
        # its halo, so the layout spacing is reduced by the same amount and the
        # panel keeps its original look and height.
        lay.setSpacing(1)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        self.title = QLabel("\u0418\u0449\u0443 \u043b\u0443\u0447\u0448\u0443\u044e \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044e \u0434\u043b\u044f \u0432\u0430\u0441!")
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title.setStyleSheet(
            "color: #ffffff; background: transparent; font-size: 20px; font-weight: 800;"
        )
        header.addWidget(self.title)
        header.addStretch(1)

        self.percent = QLabel("0%")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.percent.setStyleSheet(
            "color: #ffffff; background: transparent; font-size: 27px; font-weight: 800;"
        )
        percent_glow = QGraphicsDropShadowEffect(self.percent)
        percent_glow.setOffset(0, 0)
        percent_glow.setBlurRadius(18)
        percent_glow.setColor(QColor(220, 225, 245, 165))
        apply_effect(self.percent, percent_glow)
        header.addWidget(self.percent)
        lay.addLayout(header)

        self.bar = _DarkAnimatedProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        # 12 px bar + GLOW_PAD on both sides: the bar paints its own halo
        # inside this padding, so no QGraphicsEffect is needed and nothing is
        # clipped at the ends.
        self.bar.setFixedHeight(12 + int(2 * _DarkAnimatedProgressBar.GLOW_PAD))
        lay.addWidget(self.bar)

        self.detail = QLabel("[0/0] \u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430...")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(
            "color: rgba(255,255,255,0.72); background: transparent; "
            "font-size: 13px; font-weight: 600;"
        )
        lay.addWidget(self.detail)

        self.cancel_button = QPushButton("\u041e\u0442\u043c\u0435\u043d\u0430")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setFixedHeight(34)
        self.cancel_button.setStyleSheet(
            "QPushButton { background: #292b30; border: 1px solid #565c66; "
            "border-radius: 10px; color: #ffffff; font-size: 14px; font-weight: 700; }"
            "QPushButton:hover { background: #34373d; border-color: #858d99; }"
            "QPushButton:pressed { background: #202227; }"
        )
        lay.addWidget(self.cancel_button)
        self.hide()

    def reset(self, total: int) -> None:
        self._total = max(1, int(total))
        self.percent.setText("0%")
        self.bar.setValue(0)
        self.detail.setText(f"[0/{self._total}] \u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430...")
        self.cancel_button.setEnabled(True)

    def update_progress(self, idx: int, total: int, name: str, phase: str) -> None:
        total = max(1, int(total))
        pct = int(max(0, min(100, round((idx / total) * 100))))
        self.percent.setText(f"{pct}%")
        self.bar.setValue(pct)
        lang = getattr(self._owner, "lang", "ru")
        self.detail.setText(f"[{idx}/{total}] {tr_text(lang, phase)}...")

    def set_message(self, text: str) -> None:
        lang = getattr(self._owner, "lang", "ru")
        self.detail.setText(tr_text(lang, text))
        self.cancel_button.setEnabled(False)


class _SleepZWidget(QWidget):
    """Cartoon Z-z-z particles shown while the dark-theme cat is sleeping."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._sleeping = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(2500)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_phase)
        self.hide()

    def _on_phase(self, value) -> None:
        self._phase = float(value)
        self.update()

    def set_sleeping(self, sleeping: bool) -> None:
        sleeping = bool(sleeping)
        if sleeping and not self._sleeping:
            self._phase = 0.0
            self.show()
            self.raise_()
            self._anim.start()
        elif not sleeping:
            self._anim.stop()
            self._phase = 0.0
            self.hide()
        self._sleeping = sleeping
        self.update()

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        if not self._sleeping:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Three staggered letters travel toward the same destination while
        # gently wandering with different phases/frequencies. The oscillation
        # fades at both ends, preserving the original start/end coordinates.
        for index, delay in enumerate((0.0, 1.0 / 3.0, 2.0 / 3.0)):
            progress = (self._phase - delay) % 1.0
            fade_wave = max(0.0, math.sin(math.pi * progress))
            opacity = fade_wave ** 1.25
            if opacity <= 0.01:
                continue

            base_x = 10.0 + progress * 76.0
            base_y = float(self.height()) - 13.0 - progress * 58.0
            wander_envelope = fade_wave
            vertical_wander = wander_envelope * (
                4.2 * math.sin(2.0 * math.pi * (2.15 * progress + index * 0.37))
                + 1.8 * math.sin(2.0 * math.pi * (3.70 * progress + index * 0.61))
            )
            horizontal_wander = wander_envelope * 1.4 * math.sin(
                2.0 * math.pi * (1.65 * progress + index * 0.43)
            )
            x = base_x + horizontal_wander
            y = base_y + vertical_wander

            # Keep one fixed vector glyph and scale the painter continuously.
            # Linear growth means the letter increases during its entire path;
            # no font-size quantisation or mid-flight z -> Z replacement occurs.
            scale = 0.56 + progress * 0.52
            font = QFont("Segoe UI")
            font.setPointSizeF(24.0)
            font.setBold(True)
            painter.setFont(font)
            glyph = ("z", "z", "Z")[index]

            painter.save()
            painter.translate(x, y)
            painter.scale(scale, scale)

            # Soft blue-white glow, painted as several translucent offsets.
            glow_alpha = int(72 * opacity)
            painter.setPen(QColor(145, 185, 255, glow_alpha))
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)):
                painter.drawText(QPointF(dx, dy), glyph)

            painter.setPen(QColor(235, 241, 255, int(245 * opacity)))
            painter.drawText(QPointF(0.0, 0.0), glyph)
            painter.restore()
        painter.end()
