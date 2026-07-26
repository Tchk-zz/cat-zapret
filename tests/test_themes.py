"""Theme catalog, generated QSS and theme related config round trips."""
from pathlib import Path
import tempfile
import unittest


class ThemesTests(unittest.TestCase):

    def test_theme_catalog_has_10_themes(self):
        """The catalog must contain exactly 10 themes: 3 presets + 7 image."""
        from ui.themes_catalog import THEMES
        self.assertEqual(len(THEMES), 10)
        presets = [t for t in THEMES if t.group == "preset"]
        images = [t for t in THEMES if t.group == "image"]
        self.assertEqual(len(presets), 3, "Expected 3 preset themes (purple/dark/light)")
        self.assertEqual(len(images), 7, "Expected 7 image themes")

    def test_theme_catalog_presets_have_no_bg_image(self):
        """The 3 preset themes (purple/dark/light) must have bg_image=None —
        they use the procedural gradient / flat fill, not a photo."""
        from ui.themes_catalog import THEMES
        for t in THEMES:
            if t.group == "preset":
                self.assertIsNone(t.bg_image,
                                  f"Preset theme '{t.id}' must not have a bg_image")

    def test_theme_catalog_image_themes_have_bg_image(self):
        """Each of the 7 image themes must reference a non-None bg_image file."""
        from ui.themes_catalog import THEMES
        for t in THEMES:
            if t.group == "image":
                self.assertIsNotNone(t.bg_image,
                                     f"Image theme '{t.id}' must have a bg_image")
                self.assertTrue(t.bg_image.endswith(".jpg"),
                                f"Image theme '{t.id}' bg_image must be a .jpg file")

    def test_theme_catalog_unique_ids(self):
        """All theme ids must be unique (no duplicates)."""
        from ui.themes_catalog import theme_ids
        ids = theme_ids()
        self.assertEqual(len(ids), len(set(ids)),
                         f"Duplicate theme ids: {ids}")

    def test_theme_catalog_get_theme_falls_back_to_purple(self):
        """get_theme('unknown') must return the purple theme, not raise."""
        from ui.themes_catalog import get_theme
        t = get_theme("nonexistent-theme-id")
        self.assertEqual(t.id, "purple")

    def test_theme_catalog_image_themes_have_palette(self):
        """Each image theme must have a complete palette (text, accent,
        card_bg, etc.) so that get_theme_qss() can generate a full QSS
        from DARK_QSS + colour substitution."""
        from ui.themes_catalog import THEMES
        required_palette_fields = [
            "text", "text_on_accent", "text_muted",
            "card_bg", "card_border", "card_hover",
            "accent", "accent_2", "nav_glow",
        ]
        for t in THEMES:
            if t.group == "image":
                for field in required_palette_fields:
                    val = getattr(t, field, "")
                    self.assertTrue(val,
                                    f"Image theme '{t.id}' must have non-empty palette field '{field}'")

    def test_theme_catalog_image_themes_have_accent_colors(self):
        """Each image theme must define non-empty accent colours (used for
        buttons, links, focus outlines). Both accent and accent_2 must be
        hex colours."""
        from ui.themes_catalog import THEMES
        for t in THEMES:
            if t.group == "image":
                self.assertTrue(t.accent.startswith("#"),
                                f"Image theme '{t.id}' accent must be a hex colour")
                self.assertTrue(t.accent_2.startswith("#"),
                                f"Image theme '{t.id}' accent_2 must be a hex colour")

    def test_theme_catalog_all_background_files_exist(self):
        """Every image theme's bg_image file must exist on disk under
        ui/assets/themes/. A missing file would silently fall back to the
        purple gradient, which is not what the user selected."""
        from ui.themes_catalog import THEMES
        themes_dir = Path(__file__).resolve().parent.parent / "ui" / "assets" / "themes"
        for t in THEMES:
            if t.group == "image" and t.bg_image:
                p = themes_dir / t.bg_image
                self.assertTrue(p.exists(),
                                f"Theme '{t.id}' background image not found: {p}")

    def test_image_theme_qss_uses_theme_text_color_not_purple(self):
        """CRITICAL: LIGHT image themes must NOT contain the hardcoded purple
        text colour '#ece8ff' from DARK_QSS after colour substitution.
        DARK image themes (like 'midnight') legitimately use a light text
        colour because their background is dark."""
        from ui.themes_catalog import THEMES, get_theme_qss
        # Use a minimal DARK_QSS that contains the purple colours we test for.
        fake_dark = "QWidget { color: #ece8ff; } QLabel { color: #9b93c0; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                # The theme's own text colour must be present.
                self.assertIn(t.text, qss,
                              f"Image theme '{t.id}' qss must use its own text colour {t.text}")
                if not t.is_dark:
                    self.assertNotIn("#ece8ff", qss,
                                     f"Light image theme '{t.id}' still has purple #ece8ff")
                    self.assertNotIn("#9b93c0", qss,
                                     f"Light image theme '{t.id}' still has purple #9b93c0")

    def test_image_theme_qss_preserves_power_button_dimensions(self):
        """powerBtn must keep 160px + border-radius: 32px from DARK_QSS."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QPushButton#powerBtn { min-width: 160px; max-width: 160px; min-height: 160px; max-height: 160px; border-radius: 32px; background: rgba(255,255,255,0.05); }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        import re
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                m = re.search(r"QPushButton#powerBtn\s*\{([^}]*)\}", qss)
                self.assertIsNotNone(m, f"Image theme '{t.id}' must have powerBtn rule")
                block = m.group(1)
                self.assertIn("160px", block)
                self.assertIn("border-radius: 32px", block)

    def test_image_theme_qss_preserves_nav_panel_radius(self):
        """navPanel must keep border-radius: 18px from DARK_QSS."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QFrame#navPanel { background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.24); border-radius: 18px; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        import re
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                m = re.search(r"QFrame#navPanel\s*\{([^}]*)\}", qss)
                self.assertIsNotNone(m)
                self.assertIn("border-radius: 18px", m.group(1))

    def test_image_theme_qss_preserves_nav_button_padding(self):
        """navBtn must keep padding: 12px 46px from DARK_QSS."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QPushButton#navBtn { background: transparent; color: #cfc7ee; padding: 12px 46px; border: 1px solid transparent; border-radius: 12px; font-size: 19px; font-weight: 500; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        import re
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                m = re.search(r"QPushButton#navBtn\s*\{([^}]*)\}", qss)
                self.assertIsNotNone(m)
                self.assertIn("padding: 12px 46px", m.group(1))

    def test_image_theme_qss_covers_settings_card(self):
        """Settings card must be recoloured — the purple rgba(16,8,56,...)
        from DARK_QSS must be replaced with the theme's card_bg."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QFrame#settingsCard { background: rgba(16, 8, 56, 0.42); border: 1px solid rgba(255,255,255,0.10); border-radius: 28px; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                self.assertIn("QFrame#settingsCard", qss)
                self.assertNotIn("rgba(16, 8, 56, 0.42)", qss,
                                 f"Theme '{t.id}' still has purple settings card bg")
                self.assertIn(t.card_bg, qss,
                              f"Theme '{t.id}' must use its card_bg")

    def test_get_theme_qss_image_theme_substitutes_colours(self):
        """get_theme_qss() for an image theme must return DARK_QSS with
        colours substituted — NOT the raw DARK_QSS."""
        from ui.themes_catalog import get_theme_qss, THEMES
        fake_dark = "QWidget { color: #ece8ff; } QPushButton#primary { background: #7d52ff; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                # The purple colours must be gone (for light themes).
                if not t.is_dark:
                    self.assertNotIn("#ece8ff", qss)
                self.assertNotIn("#7d52ff", qss)
                # The theme's accent must be present.
                self.assertIn(t.accent, qss)

    def test_get_theme_qss_preset_uses_prebuilt_strings(self):
        """get_theme_qss() for preset themes must return the pre-built QSS
        strings from theme.py (DARK / WIN11_DARK / WIN11_LIGHT)."""
        from ui.themes_catalog import get_theme_qss
        base_qss = {
            "DARK": "DARK_QSS_BODY",
            "WIN11_DARK": "WIN11_DARK_BODY",
            "WIN11_LIGHT": "WIN11_LIGHT_BODY",
        }
        self.assertEqual(get_theme_qss("purple", base_qss), "DARK_QSS_BODY")
        self.assertEqual(get_theme_qss("dark", base_qss), "WIN11_DARK_BODY")
        self.assertEqual(get_theme_qss("light", base_qss), "WIN11_LIGHT_BODY")

    # --- Auto-start bypass on launch ---

    def test_config_has_autostart_strategy_field(self):
        """AppConfig must have an 'autostart_strategy' field defaulting to
        False. This controls whether the bypass engine auto-starts on launch."""
        from app.config import AppConfig
        cfg = AppConfig()
        self.assertFalse(cfg.autostart_strategy,
                         "autostart_strategy must default to False")
        # Must be settable and saveable.
        cfg.autostart_strategy = True
        self.assertTrue(cfg.autostart_strategy)

    def test_config_autostart_strategy_persists(self):
        """autostart_strategy must survive a save/load cycle."""
        with tempfile.TemporaryDirectory() as td:
            import os
            os.environ["LOCALAPPDATA"] = td
            from app.config import AppConfig
            cfg = AppConfig()
            cfg.autostart_strategy = True
            cfg.last_working_strategy = "General — ALT"
            cfg.save()
            # Load a fresh instance.
            cfg2 = AppConfig.load()
            self.assertTrue(cfg2.autostart_strategy)
            self.assertEqual(cfg2.last_working_strategy, "General — ALT")

    # --- Theme persistence regression ---

    def test_image_theme_id_surives_config_round_trip(self):
        """AppConfig accepts any string for `theme` — but the GUI used to
        filter it against only ('purple','light','dark') at startup, silently
        resetting any of the 7 image themes (mist/azure/snow/lavender/fog/
        sand/midnight) back to 'purple'. This test pins the catalog so the
        regression can't sneak back in: every theme id returned by the catalog
        MUST be a valid save value that the GUI will honour on reload."""
        from ui.themes_catalog import THEMES, theme_ids
        # Catalog must contain all 10 themes — the 3 presets + 7 image themes.
        self.assertEqual(len(THEMES), 10)
        # Every theme id must be unique and non-empty.
        ids = theme_ids()
        self.assertEqual(len(ids), len(set(ids)))
        for tid in ids:
            self.assertTrue(tid and isinstance(tid, str))
        # The 7 image themes MUST be in the catalog. If any are missing, the
        # GUI's "validate saved theme against catalog" check would silently
        # fall back to 'purple' even though the user picked a real theme.
        image_ids = {t.id for t in THEMES if t.group == "image"}
        expected_image_ids = {
            "mist", "azure", "snow", "lavender", "fog", "sand", "midnight"
        }
        self.assertEqual(image_ids, expected_image_ids)

    def test_theme_validation_accepts_all_image_themes(self):
        """The validation logic in MainWindow.__init__ must accept every
        theme id from the catalog. We simulate the same check here against
        a config that has each image theme set."""
        from ui.themes_catalog import theme_ids
        valid = set(theme_ids())
        for tid in ["mist", "azure", "snow", "lavender", "fog", "sand", "midnight"]:
            self.assertIn(tid, valid,
                          f"Image theme '{tid}' must be in the valid set")

    # --- SHA-256 integrity check for zapret bundle downloads ---
