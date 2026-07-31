"""Theme selection and application for the main window.

Split out of ``ui/main_window.py``: everything here answers one question —
"the user picked theme X, what has to change?". The window itself only keeps
``self.current_theme`` and calls :meth:`ThemeApplyMixin._apply_theme`.

The mixin deliberately touches widgets through ``hasattr``/``getattr`` guards:
``_apply_theme`` runs during ``__init__`` (before every tab exists) and again on
every later theme switch.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, QSize
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

from .effects import apply_effect
from .paths import asset_path
from .theme import DARK_QSS, WIN11_DARK_QSS, WIN11_LIGHT_QSS


class ThemeApplyMixin:
    """Theme menu + full theme application. Mixed into ``MainWindow``."""

    def _toggle_theme(self, theme_id: str, checked: bool = True) -> None:
        """Apply a theme by id. ``checked`` is kept for backwards-compat
        with the old checkbox wiring — the dropdown menu always passes True."""
        if not checked:
            return
        from .themes_catalog import THEMES
        # Validate the theme_id against the catalog. Unknown → fall back to purple.
        valid_ids = {t.id for t in THEMES}
        if theme_id not in valid_ids:
            theme_id = "purple"
        self.current_theme = theme_id
        self.config.theme = theme_id
        self.config.save()
        self._apply_theme()
        # Update the theme-selector button label so it shows the new theme.
        if hasattr(self, "btn_theme_select"):
            self.btn_theme_select.setText(self._current_theme_display_name())

    def _current_theme_display_name(self) -> str:
        """Display name of the current theme, localized."""
        from .themes_catalog import get_theme
        t = get_theme(self.current_theme)
        return self._t(t.name_ru) if self.lang == "en" else t.name_ru

    def _show_theme_menu(self) -> None:
        """Open a dropdown menu listing all available themes. Selecting one
        applies it immediately."""
        from .themes_catalog import THEMES
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        # Use the system font for the menu (the app-wide font is the bundled
        # display font which is too "branded" for a context menu).
        try:
            from PyQt6.QtGui import QFontDatabase
            menu.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
        except Exception:
            pass
        # Group: presets first, then image themes, with a separator.
        presets = [t for t in THEMES if t.group == "preset"]
        images = [t for t in THEMES if t.group == "image"]
        for t in presets:
            act = menu.addAction(t.name_ru if self.lang != "en" else t.name_en)
            act.setCheckable(True)
            act.setChecked(t.id == self.current_theme)
            act.triggered.connect(lambda _checked=False, tid=t.id: self._toggle_theme(tid))
        if images:
            menu.addSeparator()
            for t in images:
                act = menu.addAction(t.name_ru if self.lang != "en" else t.name_en)
                act.setCheckable(True)
                act.setChecked(t.id == self.current_theme)
                act.triggered.connect(lambda _checked=False, tid=t.id: self._toggle_theme(tid))
        # Show below the button.
        btn = self.btn_theme_select
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft() + QPoint(0, 4)))

    def _apply_theme(self) -> None:
        """Apply the current theme: QSS, background, nav glow, shadows, icons.

        For image themes (group=="image") we use the theme's FULL generated
        QSS (NOT appended on top of DARK_QSS — otherwise the purple-theme
        colours would bleed through). The generated QSS covers every widget
        with the theme's palette, so text is readable on every background.

        For the 3 preset themes we keep the original behaviour (procedural
        purple gradient / flat dark / flat light).
        """
        from .themes_catalog import get_theme, is_image_theme, get_theme_qss
        theme_id = getattr(self, "current_theme", "purple")
        theme = get_theme(theme_id)
        is_image = is_image_theme(theme_id)
        is_dark_preset = theme_id == "dark"
        is_light_preset = theme_id == "light"
        is_neutral = is_dark_preset or is_light_preset  # flat-fill presets
        # --- QSS: use the new get_theme_qss() resolver ---
        base_qss = {
            "DARK": DARK_QSS,
            "WIN11_DARK": WIN11_DARK_QSS,
            "WIN11_LIGHT": WIN11_LIGHT_QSS,
        }
        full_qss = get_theme_qss(theme_id, base_qss)
        self.setStyleSheet(full_qss)
        # Swap the home-tab layout: dark theme uses its own arrangement,
        # purple/light keep the original classic layout.
        if hasattr(self, "home_body"):
            self._apply_home_layout(is_dark_preset)
        # --- Raised 3D home surfaces (dark preset only) ---
        for home_surface in (
            getattr(self, "home_tg_card", None),
            getattr(self, "home_zap_card", None),
            getattr(self, "home_runner_card", None),
            getattr(self, "home_auto_panel", None),
            getattr(self, "btn_auto", None),
            getattr(self, "btn_check", None),
        ):
            if home_surface is None or not hasattr(home_surface, "set_dark_3d"):
                continue
            home_surface.set_dark_3d(is_dark_preset)
            if is_dark_preset:
                if home_surface.graphicsEffect() is None:
                    shadow = QGraphicsDropShadowEffect(home_surface)
                    shadow.setBlurRadius(34)
                    shadow.setOffset(0, 9)
                    shadow.setColor(QColor(0, 0, 0, 165))
                    apply_effect(home_surface, shadow)
            elif home_surface.graphicsEffect() is not None:
                home_surface.setGraphicsEffect(None)
        if hasattr(self, "home_auto_panel"):
            self._set_dark_auto_panel_active(self._auto_thread is not None)
        # --- Power button theme colours ---
        # The PowerButton is custom-painted (not styled by QSS), so we need
        # to explicitly tell it what colours to use for the glyph + gradient
        # backing. For image themes, use the theme's accent as the stopped
        # colour and green (#37c871) as the running colour. For the purple
        # preset, use the defaults (None = green/purple).
        if hasattr(self, "btn_toggle") and is_image:
            self.btn_toggle.set_theme_colors(
                running_color="#37c871",
                stopped_color=theme.accent,
                running_hue=135,
                stopped_hue=theme._stopped_hue if hasattr(theme, '_stopped_hue') else None,
            )
        elif hasattr(self, "btn_toggle"):
            if is_dark_preset:
                self.btn_toggle.set_theme_colors(
                    running_color="#37c871",
                    stopped_color="#ff1010",
                    running_hue=135,
                    stopped_hue=-1,
                )
            else:
                self.btn_toggle.set_theme_colors()  # Reset to defaults
        # --- Background ---
        if hasattr(self, "_bg"):
            if is_image and theme.bg_image:
                # Resolve the theme background image path.
                bg_path = self._resolve_theme_image_path(theme.bg_image)
                self._bg.set_theme_image(bg_path)
            else:
                # Disable image-theme mode so the procedural/flat renderer takes over.
                self._bg.set_theme_image("")
            self._update_bg_mode(self.tabs.currentIndex() if hasattr(self, "tabs") else 0)
        # --- Nav glow ---
        if hasattr(self, "_top_nav") and hasattr(self._top_nav, "_glow"):
            if is_image:
                glow_color = QColor(theme.nav_glow) if theme.nav_glow else QColor(150, 120, 255, 180)
                self._top_nav._glow.setColor(glow_color)
                self._top_nav._glow.setBlurRadius(getattr(self._top_nav, "_base_blur", 26))
            elif is_neutral:
                self._top_nav._glow.setColor(QColor(0, 0, 0, 0))
                self._top_nav._glow.setBlurRadius(0)
            else:
                self._top_nav._glow.setColor(QColor(150, 120, 255, 180))
                self._top_nav._glow.setBlurRadius(getattr(self._top_nav, "_base_blur", 26))
        # --- Nav section icons: dark glyphs on the light preset, light ones
        # everywhere else, so they never disappear into the panel. ---
        if hasattr(self, "_top_nav") and hasattr(self._top_nav, "set_icon_color"):
            self._top_nav.set_icon_color(
                "#1a1a1a" if self.current_theme == "light" else "#ffffff")
        # --- Card shadows: keep for image + purple themes; disable for flat presets ---
        if hasattr(self, "settings_card"):
            if is_neutral:
                self.settings_card.setGraphicsEffect(None)
            elif self.settings_card.graphicsEffect() is None:
                card_shadow = QGraphicsDropShadowEffect(self.settings_card)
                card_shadow.setBlurRadius(34)
                card_shadow.setOffset(0, 8)
                card_shadow.setColor(QColor(0, 0, 0, 95))
                apply_effect(self.settings_card, card_shadow)
        if hasattr(self, "status_pill"):
            if is_neutral:
                self.status_pill.setGraphicsEffect(None)
            elif self.status_pill.graphicsEffect() is None:
                pill_shadow = QGraphicsDropShadowEffect(self.status_pill)
                pill_shadow.setBlurRadius(24)
                pill_shadow.setOffset(0, 2)
                pill_shadow.setColor(QColor(0, 0, 0, 95))
                apply_effect(self.status_pill, pill_shadow)
        # Neutral themes (dark/light) remove decorative cats and action icons.
        # Image themes + purple keep them.
        show_decor = not is_neutral
        if hasattr(self, "settings_cat"):
            self.settings_cat.setVisible(show_decor)
        if hasattr(self, "btn_auto"):
            self.btn_auto.setIcon(QIcon() if not show_decor else QIcon(asset_path("auto_select_icon_256.png")))
            self.btn_auto.setIconSize(QSize(0, 0) if not show_decor else QSize(50, 50))
        if hasattr(self, "btn_check"):
            self.btn_check.setIcon(QIcon() if not show_decor else QIcon(asset_path("check_icon_256.png")))
            self.btn_check.setIconSize(QSize(0, 0) if not show_decor else QSize(50, 50))
        # Update the theme-selector button label (in case it was created
        # before the theme was applied — e.g. on first launch).
        if hasattr(self, "btn_theme_select"):
            self.btn_theme_select.setText(self._current_theme_display_name())
            if is_dark_preset:
                self.btn_theme_select.setStyleSheet(
                    "QPushButton { background: #2d2d2d; border: 1px solid #5a5a5a; "
                    "border-radius: 14px; color: #ffffff; padding: 7px 18px; "
                    "min-height: 32px; max-height: 32px; font-weight: 600; }"
                    "QPushButton:hover { background: #3a3a3a; border-color: #777777; }"
                    "QPushButton:pressed { background: #252525; border-color: #888888; }"
                )
            else:
                self.btn_theme_select.setStyleSheet("")
        self._apply_settings_density(is_dark_preset)
        self._set_power_state(self.runner.is_running() if hasattr(self, "runner") else False)

    def _apply_settings_density(self, is_dark_preset: bool) -> None:
        """Compact Settings composition is exclusive to the dark preset.

        Other themes retain their original spacing and presentation. Split out
        of ``_apply_theme`` so the two spacing variants sit side by side and
        stay easy to compare.
        """
        if not (hasattr(self, "settings_root_layout") and hasattr(self, "settings_card_layout")):
            return
        if is_dark_preset:
            self.settings_root_layout.setContentsMargins(42, 12, 42, 12)
            self.settings_card_layout.setContentsMargins(48, 14, 48, 14)
            self.settings_card_layout.setSpacing(0)
            if hasattr(self, "settings_rows_layout"):
                self.settings_rows_layout.setSpacing(12)
            if hasattr(self, "settings_updates_layout"):
                self.settings_updates_layout.setSpacing(8)
            if hasattr(self, "settings_theme_gap"):
                self.settings_theme_gap.setVisible(True)
                self.settings_theme_gap.setFixedHeight(30)
            if hasattr(self, "settings_theme_selector_gap"):
                self.settings_theme_selector_gap.setVisible(True)
                self.settings_theme_selector_gap.setFixedHeight(20)
            if hasattr(self, "settings_updates_gap"):
                self.settings_updates_gap.setVisible(True)
                self.settings_updates_gap.setFixedHeight(30)
            for row, row_lay, cb in getattr(self, "settings_rows", []):
                row.setMinimumHeight(45)
                row.setMaximumHeight(45)
                row_lay.setContentsMargins(18, 0, 18, 0)
                cb.setStyleSheet(
                    "QCheckBox#settingsCheck { padding: 0; }"
                    "QCheckBox#settingsCheck::indicator { width: 21px; height: 21px; }"
                )
        else:
            self.settings_root_layout.setContentsMargins(42, 24, 42, 16)
            self.settings_card_layout.setContentsMargins(48, 18, 48, 18)
            self.settings_card_layout.setSpacing(8)
            if hasattr(self, "settings_rows_layout"):
                self.settings_rows_layout.setSpacing(8)
            if hasattr(self, "settings_updates_layout"):
                self.settings_updates_layout.setSpacing(8)
            if hasattr(self, "settings_theme_gap"):
                self.settings_theme_gap.setVisible(False)
            if hasattr(self, "settings_theme_selector_gap"):
                self.settings_theme_selector_gap.setVisible(False)
            if hasattr(self, "settings_updates_gap"):
                self.settings_updates_gap.setVisible(True)
                self.settings_updates_gap.setFixedHeight(8)
            for row, row_lay, cb in getattr(self, "settings_rows", []):
                row.setMinimumHeight(0)
                row.setMaximumHeight(16777215)
                row_lay.setContentsMargins(18, 5, 18, 5)
                cb.setStyleSheet("")

    def _resolve_theme_image_path(self, filename: str) -> str:
        """Resolve the absolute path to a theme background image.

        Looks under ui/assets/themes/ — both from source (ui/assets/themes)
        and when frozen by PyInstaller (sys._MEIPASS/ui/assets/themes).
        """
        roots = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "ui" / "assets" / "themes")
            roots.append(Path(meipass) / "assets" / "themes")
        here = Path(__file__).resolve().parent
        roots.append(here / "assets" / "themes")
        for root in roots:
            cand = root / filename
            try:
                if cand.is_file():
                    return str(cand)
            except OSError:
                pass
        return ""
