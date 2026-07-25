"""Animated gradient / image background widget."""

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPixmap, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from .paths import asset_path_or_empty

_asset_path = asset_path_or_empty


class GradientBackground(QWidget):
    """Adaptive background widget.

    Three rendering modes (mutually exclusive):
      1. Image theme (highest priority) — a user-selected photographic
         background (from the theme catalog) is drawn edge-to-edge. Used for
         the 7 new image themes (Mist, Azure, Snow, Lavender, Fog, Sand,
         Midnight). The same image is used on EVERY tab — Home, Settings,
         Strategy, Games, Telegram — so the app feels cohesive.
      2. Flat dark/light — Windows 11-like solid fill for the existing
         "dark" and "light" preset themes.
      3. Procedural purple gradient — the original "purple" theme, with
         separate Home / Settings photographic backgrounds.

    The image-theme mode takes priority; if set, dark/light/home/settings
    modes are ignored.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._home_mode = False
        self._settings_mode = False
        self._home_pixmap = None       # lazily loaded background image
        self._home_loaded = False
        self._scaled = None            # cached scaled pixmap
        self._scaled_size = None
        self._settings_pixmap = None
        self._settings_loaded = False
        self._settings_scaled = None
        self._settings_scaled_size = None
        self._dark_mode = False
        self._light_mode = False
        # Dark-theme background image cache (dark preset only).
        self._dark_pixmap = None
        self._dark_loaded = False
        self._dark_scaled = None
        self._dark_scaled_size = None
        # Image-theme state.
        self._theme_image_path: str = ""  # absolute path to the theme bg
        self._theme_pixmap = None
        self._theme_loaded = False
        self._theme_scaled = None
        self._theme_scaled_size = None

    def set_theme_image(self, path: str) -> None:
        """Switch to image-theme mode using the given background file path.

        Pass an empty string to disable image-theme mode and fall back to
        the procedural/flat rendering.
        """
        path = path or ""
        if path != self._theme_image_path:
            self._theme_image_path = path
            # Invalidate cache so the new image is loaded on next paint.
            self._theme_pixmap = None
            self._theme_loaded = False
            self._theme_scaled = None
            self._theme_scaled_size = None
            self.update()

    def set_dark_mode(self, enabled: bool) -> None:
        """Use a flat Windows 11-like dark background without images/gradients."""
        enabled = bool(enabled)
        if enabled != self._dark_mode:
            self._dark_mode = enabled
            if enabled:
                self._light_mode = False
            self.update()

    def set_light_mode(self, enabled: bool) -> None:
        """Use a flat Windows 11-like light background without images/gradients."""
        enabled = bool(enabled)
        if enabled != self._light_mode:
            self._light_mode = enabled
            if enabled:
                self._dark_mode = False
            self.update()

    def set_home_mode(self, enabled: bool) -> None:
        """Use the photographic background (Home page) or the procedural one.

        Ignored when an image theme is active — image themes use the same
        background on every tab."""
        enabled = bool(enabled)
        if self._dark_mode or self._light_mode or self._theme_image_path:
            enabled = False
        if enabled != self._home_mode or (enabled and self._settings_mode):
            self._home_mode = enabled
            if enabled:
                self._settings_mode = False
            self.update()

    def set_settings_mode(self, enabled: bool) -> None:
        """Use the attached photographic background only for Settings.

        Ignored when an image theme is active — image themes use the same
        background on every tab."""
        enabled = bool(enabled)
        if self._dark_mode or self._light_mode or self._theme_image_path:
            enabled = False
        if enabled != self._settings_mode or (enabled and self._home_mode):
            self._settings_mode = enabled
            if enabled:
                self._home_mode = False
            self.update()

    def _home_image(self):
        if not self._home_loaded:
            self._home_loaded = True
            path = _asset_path("bg_home.png")
            if path:
                pm = QPixmap(path)
                self._home_pixmap = pm if not pm.isNull() else None
        return self._home_pixmap

    def _settings_image(self):
        if not self._settings_loaded:
            self._settings_loaded = True
            path = _asset_path("settings_bg.png")
            if path:
                pm = QPixmap(path)
                self._settings_pixmap = pm if not pm.isNull() else None
        return self._settings_pixmap

    def _dark_image(self):
        """Lazily load the dark-theme background image (dark preset only)."""
        if not self._dark_loaded:
            self._dark_loaded = True
            path = _asset_path("bg_dark.png")
            if path:
                pm = QPixmap(path)
                self._dark_pixmap = pm if not pm.isNull() else None
        return self._dark_pixmap

    def _theme_image(self):
        """Lazily load the theme background pixmap."""
        if not self._theme_loaded:
            self._theme_loaded = True
            if self._theme_image_path:
                pm = QPixmap(self._theme_image_path)
                self._theme_pixmap = pm if not pm.isNull() else None
        return self._theme_pixmap

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        w = rect.width()
        h = rect.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        # === Priority 1: image theme — same background on every tab. ===
        if self._theme_image_path:
            pm = self._theme_image()
            if pm is not None:
                key = (w, h)
                if self._theme_scaled is None or self._theme_scaled_size != key:
                    self._theme_scaled = pm.scaled(
                        w, h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._theme_scaled_size = key
                painter.drawPixmap(0, 0, self._theme_scaled)
                painter.end()
                return
            # If the image failed to load, fall through to the procedural
            # gradient as a graceful fallback.

        if self._dark_mode:
            pm = self._dark_image()
            if pm is not None:
                key = (w, h)
                if self._dark_scaled is None or self._dark_scaled_size != key:
                    self._dark_scaled = pm.scaled(
                        w, h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._dark_scaled_size = key
                painter.drawPixmap(0, 0, self._dark_scaled)
                painter.end()
                return
            # Fallback to the flat dark fill if the image failed to load.
            painter.fillRect(rect, QColor("#0f0f0f"))
            painter.end()
            return
        if self._light_mode:
            painter.fillRect(rect, QColor("#f3f3f3"))
            painter.end()
            return

        # Home page uses a photographic "liquid glass" background: the brighter
        # upper part hosts the top panel / power button / status indicator, the
        # darker lower part hosts the remaining controls.
        if self._home_mode:
            pm = self._home_image()
            if pm is not None:
                key = (w, h)
                if self._scaled is None or self._scaled_size != key:
                    self._scaled = pm.scaled(
                        w, h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._scaled_size = key
                painter.drawPixmap(0, 0, self._scaled)
                painter.end()
                return

        # Settings page has its own attached image background, separate from
        # Home and all other tabs.
        if self._settings_mode:
            pm = self._settings_image()
            if pm is not None:
                key = (w, h)
                if self._settings_scaled is None or self._settings_scaled_size != key:
                    self._settings_scaled = pm.scaled(
                        w, h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._settings_scaled_size = key
                painter.drawPixmap(0, 0, self._settings_scaled)
                painter.end()
                return

        def col(hex_or_rgb, alpha=255):
            if isinstance(hex_or_rgb, tuple):
                r, g, b = hex_or_rgb
                c = QColor(r, g, b)
            else:
                c = QColor(hex_or_rgb)
            c.setAlpha(alpha)
            return c

        def radial(cx, cy, radius, stops):
            grad = QRadialGradient(cx, cy, radius)
            for pos, color in stops:
                grad.setColorAt(pos, color)
            painter.fillRect(rect, QBrush(grad))

        # 1) Base diagonal gradient (top-left -> bottom-right).
        base = QLinearGradient(0.0, 0.0, float(w), float(h))
        base.setColorAt(0.0, QColor("#7A1DCC"))
        base.setColorAt(0.20, QColor("#2A1556"))
        base.setColorAt(0.55, QColor("#050022"))
        base.setColorAt(1.0, QColor("#030017"))
        painter.fillRect(rect, base)

        # 1b) Right-side cool tint (#2F247E) fading in towards the right edge.
        right = QLinearGradient(0.0, 0.0, float(w), 0.0)
        right.setColorAt(0.0, col("#2F247E", 0))
        right.setColorAt(1.0, col("#2F247E", 130))
        painter.fillRect(rect, right)

        # 2) Top-left magenta glow.
        radial(-0.05 * w, 0.02 * h, 0.65 * w, [
            (0.0, col("#E24CFF", 235)),
            (0.5, col("#9B2CFF", 150)),
            (1.0, col("#9B2CFF", 0)),
        ])

        # 3) Left blue-purple blob.
        radial(0.15 * w, 0.40 * h, 0.38 * w, [
            (0.0, col("#6E2CFF", 220)),
            (0.45, col("#842BFF", 170)),
            (0.8, col("#2410B8", 110)),
            (1.0, col("#2410B8", 0)),
        ])

        # 4) Right pink-purple blob.
        radial(0.86 * w, 0.50 * h, 0.52 * w, [
            (0.0, col("#E377FF", 225)),
            (0.4, col("#C96CFF", 175)),
            (0.8, col("#9B1DFF", 110)),
            (1.0, col("#9B1DFF", 0)),
        ])

        # 5) Top-right white/lavender highlight.
        radial(1.05 * w, -0.05 * h, 0.34 * w, [
            (0.0, col("#FFFFFF", 240)),
            (0.4, col("#E8E2FF", 180)),
            (0.8, col("#7664D8", 90)),
            (1.0, col("#7664D8", 0)),
        ])

        # 6) Dark center overlay (creates the dark vertical area upper-center).
        radial(0.50 * w, 0.25 * h, 0.48 * w, [
            (0.0, col("#030017", 175)),
            (0.55, col("#030017", 95)),
            (1.0, col("#030017", 0)),
        ])

        # 7) Bottom dark overlay (from 60% height down to the bottom).
        top_y = int(0.60 * h)
        bottom = QLinearGradient(0.0, float(top_y), 0.0, float(h))
        bottom.setColorAt(0.0, col((10, 0, 45), int(0.70 * 255)))
        bottom.setColorAt(1.0, col((3, 0, 23), int(0.95 * 255)))
        painter.fillRect(QRect(0, top_y, w, h - top_y), bottom)

        # 8) Bottom subtle violet glow.
        radial(0.53 * w, 0.74 * h, 0.40 * w, [
            (0.0, col("#5C18E8", 55)),
            (1.0, col("#5C18E8", 0)),
        ])

        painter.end()
