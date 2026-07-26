"""Custom painted widgets and popups used by the main window.

These are self-contained Qt widgets: they draw themselves and expose
small APIs, but they never reach into MainWindow. Kept apart so the
window module stays about wiring, not painting.
"""
from __future__ import annotations

import math
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QVariantAnimation, QRect, QRectF,
    QPointF, QSize,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QDialog, QProgressBar, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)

from .effects import apply_effect
from .i18n import tr_text
from .paths import asset_path


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


class _GlassNav(QFrame):
    """iOS-26-style frosted segmented control with an animated sliding
    highlight pill and a soft glow."""

    def __init__(self, labels: List[str], on_select=None, parent=None):
        super().__init__(parent)
        self.setObjectName("navPanel")
        self._on_select = on_select
        self._active = 0
        self._buttons: List[QPushButton] = []

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


class BypassTestPopup(QDialog):
    """Reference-style animated popup for the Home / Test bypass action."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self._result = result
        self._lang = getattr(parent, "lang", "ru") if parent is not None else "ru"
        self._dark_theme = getattr(parent, "current_theme", "purple") == "dark" if parent is not None else False
        self._light_theme = getattr(parent, "current_theme", "purple") == "light" if parent is not None else False
        self._neutral_theme = self._dark_theme or self._light_theme
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("bypassTestPopup")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24 if self._neutral_theme else 61, 24, 24)
        root.setSpacing(0)

        self.cat = QLabel(self)
        self.cat.setObjectName("popupCat")
        self.cat.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cat_pm = QPixmap(asset_path("settings_cat.png"))
        if not cat_pm.isNull():
            self.cat.setPixmap(cat_pm.scaled(
                148, 74,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.cat.resize(148, 74)
        else:
            self.cat.setText("ฅ^•ﻌ•^ฅ")
            self.cat.setStyleSheet("color: #ff9cff; font-size: 28px; font-weight: 800;")
            self.cat.adjustSize()
        self.cat.setVisible(not self._neutral_theme)

        self.card = QFrame()
        self.card.setObjectName("popupCard")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 80 if self._light_theme else 150) if self._neutral_theme else QColor(219, 96, 255, 170))
        apply_effect(self.card, shadow)
        root.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(30, 32, 30, 22)
        lay.setSpacing(12)

        close_row = QHBoxLayout()
        title = QLabel(tr_text(self._lang, "Тест обхода"))
        title.setObjectName("popupTitle")
        close = QPushButton("×")
        close.setObjectName("popupClose")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        close_row.addWidget(title)
        close_row.addStretch(1)
        close_row.addWidget(close)
        lay.addLayout(close_row)

        rows = QVBoxLayout()
        rows.setSpacing(12)
        rows.addLayout(self._service_row("Discord", bool(getattr(result, "discord", False)), "discord_popup_icon.png"))
        rows.addLayout(self._service_row("YouTube", bool(getattr(result, "youtube", False)), "youtube_popup_icon.png"))
        lay.addLayout(rows)

        lay.addStretch(1)

        ok_row = QHBoxLayout()
        ok_row.addStretch(1)
        ok = QPushButton("OK")
        ok.setObjectName("popupOk")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept)
        ok_row.addWidget(ok)
        ok_row.addStretch(1)
        lay.addLayout(ok_row)

        bypass_qss = """
            QDialog#bypassTestPopup { background: transparent; }
            QFrame#popupCard {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(48, 24, 96, 232),
                    stop:0.58 rgba(27, 17, 68, 238),
                    stop:1 rgba(91, 36, 156, 232));
                border: 2px solid rgba(238, 160, 255, 238);
                border-radius: 24px;
            }
            QLabel#popupTitle {
                color: #ffffff;
                font-size: 21px;
                font-weight: 700;
            }
            QTextEdit#popupBodyScroll {
                background: transparent;
                border: none;
                color: #f1dcff;
                font-size: 15px;
                font-weight: 500;
                padding: 0 8px 0 0;
            }
            QTextEdit#popupBodyScroll QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px;
            }
            QTextEdit#popupBodyScroll QScrollBar::handle:vertical {
                background: #d084ff;
                border-radius: 4px;
                min-height: 24px;
            }
            QTextEdit#popupBodyScroll QScrollBar::add-line:vertical,
            QTextEdit#popupBodyScroll QScrollBar::sub-line:vertical {
                height: 0;
            }
            QPushButton#popupClose {
                background: transparent;
                border: none;
                color: rgba(236, 210, 255, 0.92);
                font-size: 28px;
                font-weight: 500;
                min-width: 34px;
                min-height: 34px;
                max-width: 34px;
                max-height: 34px;
                padding: 0;
            }
            QPushButton#popupClose:hover { color: #ffffff; }
            QLabel#serviceIcon {
                min-width: 32px;
                min-height: 32px;
                max-width: 32px;
                max-height: 32px;
            }
            QLabel#serviceName {
                color: #ffffff;
                font-size: 16px;
                font-weight: 650;
            }
            QLabel#serviceState {
                color: #f1dcff;
                font-size: 15px;
                font-weight: 500;
            }
            QLabel#serviceMark {
                font-size: 20px;
                font-weight: 700;
                min-width: 24px;
            }
            QPushButton#popupOk {
                background: rgba(255,255,255,0.18);
                border: 1px solid rgba(228, 164, 255, 0.82);
                border-radius: 10px;
                color: #f0a8ff;
                font-size: 16px;
                font-weight: 700;
                min-width: 260px;
                padding: 9px 22px;
            }
            QPushButton#popupOk:hover {
                background: rgba(255,255,255,0.28);
                border-color: rgba(255,255,255,0.95);
                color: #ffffff;
            }
        """
        if self._dark_theme:
            bypass_qss += """
            QFrame#popupCard { background: #1f1f1f; border: 1px solid #4a4a4a; border-radius: 16px; }
            QLabel#popupTitle, QLabel#serviceName, QLabel#serviceState, QLabel#serviceMark { color: #ffffff; }
            QPushButton#popupClose { color: #ffffff; }
            QPushButton#popupOk { background: #2d2d2d; border: 1px solid #666666; border-radius: 8px; color: #ffffff; }
            QPushButton#popupOk:hover { background: #3a3a3a; border-color: #ffffff; }
            """
        elif self._light_theme:
            bypass_qss += """
            QFrame#popupCard { background: #ffffff; border: 1px solid #c8c8c8; border-radius: 16px; }
            QLabel#popupTitle, QLabel#serviceName, QLabel#serviceState, QLabel#serviceMark { color: #000000; }
            QPushButton#popupClose { color: #000000; }
            QPushButton#popupOk { background: #ffffff; border: 1px solid #777777; border-radius: 8px; color: #000000; }
            QPushButton#popupOk:hover { background: #f2f2f2; border-color: #000000; }
            """
        self.setStyleSheet(bypass_qss)

    def _service_row(self, name: str, ok: bool, icon_name: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        icon = QLabel()
        icon.setObjectName("serviceIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = QPixmap(asset_path(icon_name))
        if not pm.isNull():
            icon.setPixmap(pm.scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            icon.setText("●")
            icon.setStyleSheet("color: #ffffff; font-size: 18px;")
        label = QLabel(name)
        label.setObjectName("serviceName")
        state = QLabel(tr_text(self._lang, "Работает!") if ok else tr_text(self._lang, "Не работает"))
        state.setObjectName("serviceState")
        mark = QLabel("✓" if ok else "×")
        mark.setObjectName("serviceMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet("color: #ffffff;" if ok else "color: #ff8fa3;")
        row.addWidget(icon)
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(state)
        row.addWidget(mark)
        return row

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._resize_to_quarter_screen()
        self._place_cat()
        self._animate_in()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_cat()

    def _place_cat(self) -> None:
        if not hasattr(self, "cat") or not self.cat.isVisible():
            return
        x = (self.width() - self.cat.width()) // 2
        # The card starts at the top layout margin (61px). Place the cat so
        # its paws sit on the card's top border like in the reference.
        card_top = 61
        overlap = 15
        y = max(0, card_top - self.cat.height() + overlap)
        self.cat.move(x, y)
        self.cat.raise_()

    def _resize_to_quarter_screen(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            area = parent.frameGeometry()
        else:
            screen = self.screen()
            if screen is None:
                return
            area = screen.availableGeometry()

        # Keep the popup strictly inside the application window. The size is
        # compact and close to the reference: roughly one third of the app.
        margin = 10
        w = min(max(430, int(area.width() * 0.58)), 560, max(1, area.width() - margin * 2))
        h = min(max(285, int(area.height() * 0.43)), 360, max(1, area.height() - margin * 2))
        self.resize(w, h)
        x = area.center().x() - w // 2
        y = area.center().y() - h // 2
        x = max(area.left() + margin, min(x, area.right() - w - margin + 1))
        y = max(area.top() + margin, min(y, area.bottom() - h - margin + 1))
        self.move(x, y)

    def _animate_in(self) -> None:
        end = self.geometry()
        start = QRectF(end).adjusted(end.width() * 0.04, end.height() * 0.04, -end.width() * 0.04, -end.height() * 0.04).toRect()
        start.moveCenter(end.center())
        self.setWindowOpacity(0.0)
        self.setGeometry(start)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._geo_anim.setDuration(260)
        self._geo_anim.setStartValue(start)
        self._geo_anim.setEndValue(end)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._fade_anim.start()
        self._geo_anim.start()


class StyledPopup(QDialog):
    """Shared glass popup shell: same scale, cat placement and buttons."""

    def __init__(self, title: str, message: str = "", parent=None, *,
                 ok_text: str = "OK", cancel_text: str | None = None,
                 center_title: bool = False, show_close: bool = True,
                 error_style: bool = False,
                 cat_asset: str = "settings_cat.png",
                 cat_size: tuple[int, int] = (148, 74),
                 cat_y_offset: int = 0):
        super().__init__(parent)
        popup_lang = getattr(parent, "lang", "ru") if parent is not None else "ru"
        self._dark_theme = getattr(parent, "current_theme", "purple") == "dark" if parent is not None else False
        self._light_theme = getattr(parent, "current_theme", "purple") == "light" if parent is not None else False
        self._neutral_theme = self._dark_theme or self._light_theme
        self._title_text = tr_text(popup_lang, title)
        self._message_text = tr_text(popup_lang, message)
        self._ok_text = tr_text(popup_lang, ok_text)
        self._cancel_text = tr_text(popup_lang, cancel_text) if cancel_text else cancel_text
        self._center_title = center_title
        self._show_close = show_close
        self._error_style = error_style
        self._cat_asset = cat_asset
        self._cat_size = cat_size
        self._cat_y_offset = cat_y_offset
        # Error popups use a taller vertical layout. Add an internal scrollbar
        # only when the text is too large for that bigger error window.
        lines = message.count("\n") + 1 if message else 0
        if self._error_style:
            self._body_needs_scroll = (len(message) > 950 or lines > 15)
        else:
            self._body_needs_scroll = (len(message) > 1200 or lines > 16)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("styledPopup")
        self._result = "ok"
        self._build_shell()

    def _build_shell(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24 if self._neutral_theme else 61, 24, 24)
        root.setSpacing(0)

        self.cat = QLabel(self)
        self.cat.setObjectName("popupCat")
        self.cat.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.cat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cat_pm = QPixmap(asset_path(self._cat_asset))
        if not cat_pm.isNull():
            cat_w, cat_h = self._cat_size
            self.cat.setPixmap(cat_pm.scaled(
                cat_w, cat_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.cat.resize(cat_w, cat_h)
        else:
            self.cat.setText("ฅ^•ﻌ•^ฅ")
            self.cat.setStyleSheet("color: #ff9cff; font-size: 28px; font-weight: 800;")
            self.cat.adjustSize()
        self.cat.setVisible(not self._neutral_theme)

        self.card = QFrame()
        self.card.setObjectName("popupCard")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 80 if self._light_theme else 150) if self._neutral_theme else QColor(219, 96, 255, 170))
        apply_effect(self.card, shadow)
        root.addWidget(self.card)

        self.lay = QVBoxLayout(self.card)
        self.lay.setContentsMargins(30, 32, 30, 22)
        self.lay.setSpacing(12)

        close_row = QHBoxLayout()
        self.title_label = QLabel(self._title_text)
        self.title_label.setObjectName("popupTitle")
        if self._center_title:
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            close_row.addStretch(1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("popupClose")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self._reject)
        self.close_button.setVisible(self._show_close)
        close_row.addWidget(self.title_label)
        close_row.addStretch(1)
        close_row.addWidget(self.close_button)
        self.lay.addLayout(close_row)

        if self._body_needs_scroll:
            self.body = QTextEdit()
            self.body.setObjectName("popupBodyScroll")
            self.body.setReadOnly(True)
            self.body.setPlainText(self._message_text)
            self.body.setFrameShape(QFrame.Shape.NoFrame)
            self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.lay.addWidget(self.body, 1)
        else:
            self.body = QLabel(self._message_text)
            self.body.setObjectName("popupBody")
            self.body.setWordWrap(True)
            align_v = Qt.AlignmentFlag.AlignTop if self._error_style else Qt.AlignmentFlag.AlignVCenter
            self.body.setAlignment(Qt.AlignmentFlag.AlignLeft | align_v)
            self.lay.addWidget(self.body)
            self.lay.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        if self._cancel_text:
            cancel = QPushButton(self._cancel_text)
            cancel.setObjectName("popupCancel")
            cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel.clicked.connect(self._reject)
            btn_row.addWidget(cancel)
        ok = QPushButton(self._ok_text)
        ok.setObjectName("popupOk")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self._accept)
        btn_row.addWidget(ok)
        btn_row.addStretch(1)
        self.lay.addLayout(btn_row)
        self.setStyleSheet(POPUP_QSS + (POPUP_DARK_QSS if self._dark_theme else (POPUP_LIGHT_QSS if self._light_theme else "")))

    def _accept(self) -> None:
        self._result = "ok"
        self.accept()

    def _reject(self) -> None:
        self._result = "cancel"
        self.reject()

    def result_name(self) -> str:
        return self._result

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._resize_to_app()
        self._place_cat()
        self._animate_in()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_cat()

    def _place_cat(self) -> None:
        if not hasattr(self, "cat") or not self.cat.isVisible():
            return
        x = (self.width() - self.cat.width()) // 2
        card_top = 61
        overlap = 15
        y = card_top - self.cat.height() + overlap + self._cat_y_offset
        self.cat.move(x, y)
        self.cat.raise_()

    def _resize_to_app(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            # Center inside the visible client area of the app window.
            # Using frameGeometry() includes the OS frame/titlebar and can make
            # frameless popups look slightly shifted.
            top_left = parent.mapToGlobal(parent.rect().topLeft())
            area = QRect(top_left, parent.rect().size())
        else:
            screen = self.screen()
            if screen is None:
                return
            area = screen.availableGeometry()
        margin = 10
        if self._error_style:
            # Error windows are intentionally vertical and larger than regular
            # popups, like the reference screenshot. They still stay strictly
            # inside the app window.
            w = min(max(500, int(area.width() * 0.53)), 560, max(1, area.width() - margin * 2))
            h = min(max(455, int(area.height() * 0.58)), 560, max(1, area.height() - margin * 2))
        else:
            w = min(max(430, int(area.width() * 0.58)), 560, max(1, area.width() - margin * 2))
            h = min(max(285, int(area.height() * 0.43)), 360, max(1, area.height() - margin * 2))
        self.resize(w, h)
        x = area.center().x() - w // 2
        y = area.center().y() - h // 2
        x = max(area.left() + margin, min(x, area.right() - w - margin + 1))
        y = max(area.top() + margin, min(y, area.bottom() - h - margin + 1))
        self.move(x, y)

    def _animate_in(self) -> None:
        end = self.geometry()
        start = QRectF(end).adjusted(end.width() * 0.04, end.height() * 0.04, -end.width() * 0.04, -end.height() * 0.04).toRect()
        start.moveCenter(end.center())
        self.setWindowOpacity(0.0)
        self.setGeometry(start)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(220)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._geo_anim.setDuration(260)
        self._geo_anim.setStartValue(start)
        self._geo_anim.setEndValue(end)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._fade_anim.start()
        self._geo_anim.start()


class AnimatedGradientProgressBar(QProgressBar):
    """Progress bar with a moving purple -> pink gradient shimmer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shine = 0.0
        self.setTextVisible(False)
        self._shine_anim = QVariantAnimation(self)
        self._shine_anim.setStartValue(0.0)
        self._shine_anim.setEndValue(1.0)
        self._shine_anim.setDuration(2200)
        self._shine_anim.setLoopCount(-1)
        self._shine_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._shine_anim.valueChanged.connect(self._set_shine)
        self._shine_anim.start()

    def _set_shine(self, value) -> None:
        self._shine = float(value)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 3.0

        # Bright base, matching the previous popup progress bar frame.
        painter.setPen(QPen(QColor(255, 255, 255, 205), 1.0))
        painter.setBrush(QColor(255, 255, 255, 245))
        painter.drawRoundedRect(r, radius, radius)

        minimum = self.minimum()
        maximum = self.maximum()
        span = max(1, maximum - minimum)
        frac = max(0.0, min(1.0, (self.value() - minimum) / span))
        if frac <= 0:
            painter.end()
            return

        chunk = QRectF(r)
        chunk.setWidth(max(radius * 2.0, r.width() * frac))

        # Static purple -> pink base.
        base = QLinearGradient(chunk.left(), 0.0, chunk.right(), 0.0)
        base.setColorAt(0.00, QColor("#7d52ff"))
        base.setColorAt(0.48, QColor("#c44bff"))
        base.setColorAt(1.00, QColor("#f557ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(base))
        painter.drawRoundedRect(chunk, radius, radius)

        # Seamless shimmer: it starts and ends outside the visible chunk, so
        # the animation can loop without a visible jump.
        w = max(1.0, chunk.width())
        shine_w = max(30.0, w * 0.38)
        center = chunk.left() - shine_w + self._shine * (w + 2.0 * shine_w)
        shine = QLinearGradient(center - shine_w, 0.0, center + shine_w, 0.0)
        shine.setColorAt(0.00, QColor(255, 255, 255, 0))
        shine.setColorAt(0.38, QColor(255, 125, 255, 45))
        shine.setColorAt(0.50, QColor(255, 235, 255, 115))
        shine.setColorAt(0.62, QColor(255, 125, 255, 45))
        shine.setColorAt(1.00, QColor(255, 255, 255, 0))
        painter.setClipRect(chunk)
        painter.setBrush(QBrush(shine))
        painter.drawRoundedRect(chunk, radius, radius)
        painter.end()



class AutoSelectProgressPopup(StyledPopup):
    """Autoselect process popup from the reference."""

    def __init__(self, parent=None, *, total: int = 1):
        self._total = max(total, 1)
        super().__init__(
            "Ищу лучшую\nстратегию для вас!",
            "",
            parent,
            ok_text="Отмена",
            center_title=True,
            show_close=False,
            cat_asset="auto_select_cat.png",
            cat_size=(240, 150),
            cat_y_offset=36,
        )
        self.setModal(False)

    def _build_shell(self) -> None:
        super()._build_shell()
        self.body.hide()
        self.lay.setSpacing(13)
        self.percent = QLabel("0%")
        self.percent.setObjectName("popupPercent")
        self.percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lay.insertWidget(1, self.percent)
        self.bar = QProgressBar() if self._neutral_theme else AnimatedGradientProgressBar()
        self.bar.setObjectName("popupProgress")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.lay.insertWidget(2, self.bar)
        self.detail = QLabel("[0/0] Подготовка...")
        self.detail.setObjectName("popupDetail")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        self.lay.insertWidget(3, self.detail)
        # The single popupOk button is the cancel button for this process.
        self.setStyleSheet(POPUP_QSS + (POPUP_DARK_QSS if self._dark_theme else (POPUP_LIGHT_QSS if self._light_theme else "")))

    def update_progress(self, idx: int, total: int, name: str, phase: str) -> None:
        total = max(total, 1)
        pct = int(max(0, min(100, round((idx / total) * 100))))
        self.percent.setText(f"{pct}%")
        self.bar.setValue(pct)
        popup_lang = getattr(self.parentWidget(), "lang", "ru")
        self.detail.setText(f"[{idx}/{total}] {tr_text(popup_lang, phase)}...")

    def set_message(self, text: str) -> None:
        popup_lang = getattr(self.parentWidget(), "lang", "ru")
        self.detail.setText(tr_text(popup_lang, text))


POPUP_QSS = """
    QDialog#styledPopup, QDialog#bypassTestPopup { background: transparent; }
    QFrame#popupCard {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 rgba(48, 24, 96, 232),
            stop:0.58 rgba(27, 17, 68, 238),
            stop:1 rgba(91, 36, 156, 232));
        border: 2px solid rgba(238, 160, 255, 238);
        border-radius: 24px;
    }
    QLabel#popupTitle {
        color: #ffffff;
        font-size: 21px;
        font-weight: 700;
    }
    QLabel#popupBody {
        color: #f1dcff;
        font-size: 15px;
        font-weight: 500;
        line-height: 125%;
    }
    QPushButton#popupClose {
        background: transparent;
        border: none;
        color: rgba(236, 210, 255, 0.92);
        font-size: 28px;
        font-weight: 500;
        min-width: 34px;
        min-height: 34px;
        max-width: 34px;
        max-height: 34px;
        padding: 0;
    }
    QPushButton#popupClose:hover { color: #ffffff; }
    QLabel#serviceIcon {
        min-width: 32px;
        min-height: 32px;
        max-width: 32px;
        max-height: 32px;
    }
    QLabel#serviceName {
        color: #ffffff;
        font-size: 16px;
        font-weight: 650;
    }
    QLabel#serviceState {
        color: #f1dcff;
        font-size: 15px;
        font-weight: 500;
    }
    QLabel#serviceMark {
        font-size: 20px;
        font-weight: 700;
        min-width: 24px;
    }
    QPushButton#popupOk, QPushButton#popupCancel {
        background: rgba(255,255,255,0.18);
        border: 1px solid rgba(228, 164, 255, 0.82);
        border-radius: 10px;
        color: #f0a8ff;
        font-size: 16px;
        font-weight: 700;
        min-width: 210px;
        padding: 9px 22px;
    }
    QPushButton#popupOk:hover, QPushButton#popupCancel:hover {
        background: rgba(255,255,255,0.28);
        border-color: rgba(255,255,255,0.95);
        color: #ffffff;
    }
    QLabel#popupPercent {
        color: #ffffff;
        font-size: 20px;
        font-weight: 700;
    }
    QLabel#popupDetail {
        color: #f1dcff;
        font-size: 13px;
        font-weight: 500;
    }
    QProgressBar#popupProgress {
        background: rgba(255,255,255,0.96);
        border: 1px solid rgba(255,255,255,0.80);
        border-radius: 3px;
        min-height: 18px;
        max-height: 18px;
        text-align: center;
        color: transparent;
    }
    QProgressBar#popupProgress::chunk {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #d929ff, stop:1 #f557ff);
        border-radius: 3px;
    }

"""

POPUP_DARK_QSS = """
QFrame#popupCard {
    background: #1f1f1f;
    border: 1px solid #4a4a4a;
    border-radius: 16px;
}
QLabel#popupTitle, QLabel#popupBody, QLabel#popupPercent, QLabel#popupDetail {
    color: #ffffff;
}
QPushButton#popupClose {
    color: #ffffff;
    background: transparent;
    border: none;
}
QPushButton#popupOk, QPushButton#popupCancel {
    background: #2d2d2d;
    border: 1px solid #666666;
    border-radius: 8px;
    color: #ffffff;
}
QPushButton#popupOk:hover, QPushButton#popupCancel:hover {
    background: #3a3a3a;
    border-color: #ffffff;
}
QTextEdit#popupBodyScroll {
    background: #1f1f1f;
    border: none;
    color: #ffffff;
}
QProgressBar#popupProgress {
    background: #252525;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
}
QProgressBar#popupProgress::chunk {
    background: #ffffff;
    border-radius: 4px;
}
"""

POPUP_LIGHT_QSS = """
QFrame#popupCard { background: #ffffff; border: 1px solid #c8c8c8; border-radius: 16px; }
QLabel#popupTitle, QLabel#popupBody, QLabel#popupPercent, QLabel#popupDetail { color: #000000; }
QPushButton#popupClose { color: #000000; background: transparent; border: none; }
QPushButton#popupOk, QPushButton#popupCancel { background: #ffffff; border: 1px solid #777777; border-radius: 8px; color: #000000; }
QPushButton#popupOk:hover, QPushButton#popupCancel:hover { background: #f2f2f2; border-color: #000000; }
QTextEdit#popupBodyScroll { background: #ffffff; border: none; color: #000000; }
QProgressBar#popupProgress { background: #e8e8e8; border: 1px solid #c8c8c8; border-radius: 4px; }
QProgressBar#popupProgress::chunk { background: #000000; border-radius: 4px; }
"""


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



def _paint_dark_3d_surface(
    widget, painter: QPainter, hovered: bool = False, pressed: bool = False, phase: float = 0.0
) -> None:
    """Paint a solid dark card with an animated gradient rim."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(widget.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
    radius = 20.0
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    # The surface itself is deliberately flat: no fill gradient or sheen.
    painter.fillPath(path, QColor("#1c1c1c"))

    # Rotate the existing rim palette around the card perimeter.
    rim = QConicalGradient(rect.center(), -360.0 * float(phase))
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
    inner_pen = QPen(QColor(255, 255, 255, 22 if hovered else 13), 0.8)
    painter.setPen(inner_pen)
    painter.drawPath(inner_path)


class _Dark3DPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_3d = False
        self._hovered = False
        self._rim_phase = 0.0
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
        _paint_dark_3d_surface(self, painter, self._hovered, False, self._rim_phase)
        painter.end()


class _Dark3DButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dark_3d = False
        self._hovered = False
        self._rim_phase = 0.0
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
        _paint_dark_3d_surface(self, painter, self._hovered, self.isDown(), self._rim_phase)
        painter.end()


class _DarkAnimatedProgressBar(QProgressBar):
    """Dark progress bar with a looping #010101 -> #a9a9a9 shimmer."""

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
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 5.0

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
        lay.setSpacing(8)

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
        self.bar.setFixedHeight(12)
        bar_glow = QGraphicsDropShadowEffect(self.bar)
        bar_glow.setOffset(0, 0)
        bar_glow.setBlurRadius(16)
        bar_glow.setColor(QColor(190, 195, 210, 135))
        self.bar.setGraphicsEffect(bar_glow)
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


class _SettingsRow(QFrame):
    """A settings row whose entire outlined area toggles its checkbox."""

    def __init__(self, checkbox: QCheckBox, parent=None):
        super().__init__(parent)
        self._checkbox = checkbox
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt naming)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
            and self._checkbox.isEnabled()
        ):
            self._checkbox.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)
