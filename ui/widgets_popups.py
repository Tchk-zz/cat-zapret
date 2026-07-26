"""Dialogs and popups: bypass test, styled popup, progress bars, their QSS."""
from __future__ import annotations

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QVariantAnimation, QRect, QRectF,
)
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QDialog, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout,
)
from .effects import apply_effect
from .i18n import tr_text
from .paths import asset_path


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
            # Theme-aware: white would be invisible on the light popup card.
            icon.setStyleSheet(
                "color: %s; font-size: 18px;" % ("#000000" if self._light_theme else "#ffffff")
            )
        label = QLabel(name)
        label.setObjectName("serviceName")
        state = QLabel(tr_text(self._lang, "Работает!") if ok else tr_text(self._lang, "Не работает"))
        state.setObjectName("serviceState")
        mark = QLabel("✓" if ok else "×")
        mark.setObjectName("serviceMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Theme-aware: the "ok" tick must not be white on the light popup card.
        if ok:
            mark.setStyleSheet("color: #000000;" if self._light_theme else "color: #ffffff;")
        else:
            mark.setStyleSheet("color: #c0392b;" if self._light_theme else "color: #ff8fa3;")
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
