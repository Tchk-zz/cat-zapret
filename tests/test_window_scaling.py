"""Tests for the Full HD fit: UI scale factor and fitted window size."""
import unittest

import main as app_main


class ScaleFactorTests(unittest.TestCase):

    def test_1440p_keeps_the_design_size(self):
        # 2560x1440 with a taskbar: plenty of room, no shrinking.
        self.assertEqual(app_main.scale_factor_for(2560, 1400), 1.0)

    def test_full_hd_is_scaled_down(self):
        factor = app_main.scale_factor_for(1920, 1040)
        self.assertLess(factor, 1.0)
        self.assertGreaterEqual(factor, app_main._MIN_SCALE)
        # The scaled window must fit the usable height with room to spare.
        self.assertLess(app_main.DESIGN_HEIGHT * factor, 1040)

    def test_small_laptop_never_goes_below_the_floor(self):
        factor = app_main.scale_factor_for(1366, 700)
        self.assertEqual(factor, app_main._MIN_SCALE)

    def test_invalid_work_area_falls_back_to_one(self):
        self.assertEqual(app_main.scale_factor_for(0, 0), 1.0)
        self.assertEqual(app_main.scale_factor_for(-100, 500), 1.0)

    def test_factor_grows_with_screen_size(self):
        small = app_main.scale_factor_for(1600, 900)
        big = app_main.scale_factor_for(1920, 1080)
        self.assertLessEqual(small, big)


class _FakeGeometry:
    def __init__(self, w, h):
        self._w = w
        self._h = h

    def width(self):
        return self._w

    def height(self):
        return self._h


class _FakeScreen:
    def __init__(self, w, h):
        self._geo = _FakeGeometry(w, h)

    def availableGeometry(self):
        return self._geo


class _FakeWindow:
    """Just enough of MainWindow for _fitted_window_size to run."""

    def __init__(self, screen):
        self._screen = screen

    def screen(self):
        return self._screen


class FittedWindowSizeTests(unittest.TestCase):

    def _fit(self, screen_w, screen_h, width=1240, height=900):
        from ui.main_window import MainWindow

        win = _FakeWindow(_FakeScreen(screen_w, screen_h))
        return MainWindow._fitted_window_size(win, width, height)

    def test_large_screen_keeps_design_size(self):
        self.assertEqual(self._fit(2560, 1400), (1240, 900))

    def test_full_hd_work_area_still_fits_the_design_height(self):
        # 1080p minus the taskbar leaves 970 usable px, so the 900 px design
        # height still fits here -- shrinking on 1080p is done by the global
        # UI scale factor in main.py, this method is only the safety net.
        w, h = self._fit(1920, 1040)
        self.assertEqual((w, h), (1240, 900))

    def test_short_screen_shrinks_and_fits(self):
        w, h = self._fit(1920, 900)
        self.assertLessEqual(w, 1920 - 40)
        self.assertLessEqual(h, 900 - 70)
        self.assertLess(h, 900)

    def test_aspect_ratio_is_preserved(self):
        w, h = self._fit(1920, 900)
        self.assertAlmostEqual(w / h, 1240 / 900, places=2)

    def test_missing_screen_falls_back_to_design_size(self):
        from ui.main_window import MainWindow

        class _NoScreen:
            def screen(self):
                return None

        size = MainWindow._fitted_window_size(_NoScreen(), 1240, 900)
        self.assertEqual(len(size), 2)
        self.assertGreater(size[0], 0)

    def test_never_returns_a_larger_window(self):
        w, h = self._fit(3840, 2160)
        self.assertEqual((w, h), (1240, 900))


if __name__ == "__main__":
    unittest.main()
