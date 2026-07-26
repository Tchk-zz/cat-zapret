"""Navigation panel frame and the games column icon."""
from __future__ import annotations

from typing import List, Optional
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QSize
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QPushButton, QWidget,
)
from .effects import apply_effect
from .icons import nav_icon_size, themed_icon


class _GlassNav(QFrame):
    """iOS-26-style frosted segmented control with an animated sliding
    highlight pill and a soft glow."""

    def __init__(self, labels: List[str], on_select=None, parent=None,
                 icon_names: Optional[List[str]] = None):
        super().__init__(parent)
        self.setObjectName("navPanel")
        self._on_select = on_select
        self._active = 0
        self._buttons: List[QPushButton] = []
        # SVG section icons, tinted to match the active theme. Names map 1:1 to
        # files in ui/assets/icons; a missing file degrades to a text-only tab.
        self._icon_names: List[str] = list(icon_names or [])
        self._icon_color = "#ffffff"
        # Logical size that maps onto whole device pixels -- see ui/icons.py.
        self._icon_size = nav_icon_size()

        # Sliding highlight that animates between sections.
        self._indicator = QFrame(self)
        self._indicator.setObjectName("navIndicator")
        self._indicator.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._base_blur = 26
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(self._base_blur)
        self._glow.setOffset(0, 0)
        self._glow.setColor(QColor(150, 120, 255, 180))
        apply_effect(self._indicator, self._glow)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(7, 7, 7, 7)  # uniform inset around the pills
        lay.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, idx=i: self._handle_click(idx))
            if i < len(self._icon_names):
                btn.setIcon(themed_icon(self._icon_names[i], self._icon_color))
                btn.setIconSize(QSize(self._icon_size, self._icon_size))
            self._group.addButton(btn, i)
            lay.addWidget(btn)
            self._buttons.append(btn)
        if self._buttons:
            self._buttons[0].setChecked(True)

        self._anim = QPropertyAnimation(self._indicator, b"geometry", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        # Motion-blur-like bloom: the glow swells while the pill is travelling
        # and settles back once it arrives, softening the movement.
        self._blur_anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._blur_anim.setDuration(420)
        self._blur_anim.setKeyValueAt(0.0, self._base_blur)
        self._blur_anim.setKeyValueAt(0.5, self._base_blur * 2.4)
        self._blur_anim.setKeyValueAt(1.0, self._base_blur)

    def _handle_click(self, index: int) -> None:
        if self._on_select:
            self._on_select(index)

    def set_labels(self, labels: List[str]) -> None:
        for btn, text in zip(self._buttons, labels):
            btn.setText(text)
        self.updateGeometry()
        self._snap()

    def set_icon_color(self, color: str) -> None:
        """Re-tint the section icons after a theme switch.

        Light presets need dark icons; the dark/purple presets need light ones.
        themed_icon() caches per (name, colour, size), so switching back and
        forth is free after the first render.
        """
        if not self._icon_names or color == self._icon_color:
            return
        self._icon_color = color
        for i, btn in enumerate(self._buttons):
            if i < len(self._icon_names):
                btn.setIcon(themed_icon(self._icon_names[i], color))

    def set_active(self, index: int, animate: bool = True) -> None:
        if not (0 <= index < len(self._buttons)):
            return
        self._active = index
        self._buttons[index].setChecked(True)
        target = self._buttons[index].geometry()
        if target.width() <= 1:
            return  # layout not ready yet; showEvent/resizeEvent will snap it
        if animate and self._indicator.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._indicator.geometry())
            self._anim.setEndValue(target)
            self._anim.start()
            self._blur_anim.stop()
            self._blur_anim.start()
        else:
            self._indicator.setGeometry(target)
        self._indicator.lower()

    def _snap(self) -> None:
        if 0 <= self._active < len(self._buttons):
            g = self._buttons[self._active].geometry()
            if g.width() > 1:
                self._indicator.setGeometry(g)
                self._indicator.lower()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._snap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._snap()


class GamesColumnIcon(QWidget):
    """Anti-aliased vector check/cross icon for Games/Services columns."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("gamesColumnIcon")
        self.setFixedSize(34, 34)

    def sizeHint(self):  # noqa: N802
        return QSize(34, 34)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(255, 255, 255, 235), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1.0, 1.0, 32.0, 32.0))
        pen = QPen(QColor(255, 255, 255), 2.1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if self.kind == "include":
            painter.drawLine(QPointF(9.3, 17.7), QPointF(14.5, 23.0))
            painter.drawLine(QPointF(14.5, 23.0), QPointF(24.8, 10.8))
        else:
            painter.drawLine(QPointF(11.0, 11.0), QPointF(23.0, 23.0))
            painter.drawLine(QPointF(23.0, 11.0), QPointF(11.0, 23.0))
        painter.end()
