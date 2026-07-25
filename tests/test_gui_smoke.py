"""Smoke tests for the PyQt6 GUI layer (MainWindow).

These tests don't try to validate behaviour — they exist to catch REGRESSIONS
in code that the existing logic-only tests in ``test_core_logic.py`` cannot
reach:

  * every theme in the catalog can be applied via ``_apply_theme`` without
    raising (covers QSS substitution, image loading, palette propagation);
  * tab switching works for every tab index (covers ``_fade_current_tab``,
    ``_update_bg_mode``, lazy widget creation);
  * the language toggle (ru ↔ en) doesn't crash on a fully-built window;
  * the TG proxy tab's DC IP override field round-trips through the runner.

All tests run OFFLINE on the Linux sandbox by stubbing out:

  * ``bootstrap._ensure_ready`` — never downloads zapret;
  * ``MainWindow.check_updates_async`` / ``_tg_check_updates_async`` — no
    network calls;
  * ``QSystemTrayIcon.show`` — there is no system tray on the CI host.

We require PyQt6 + pytest-qt. The tests are skipped automatically if either
is missing, so they don't break a plain ``python -m unittest`` run on a dev
machine that hasn't installed pytest-qt yet.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:  # ``python -m unittest discover`` without dev deps.
    import unittest
    raise unittest.SkipTest("pytest is not installed; GUI smoke tests skipped")

# Skip the whole module if PyQt6 isn't importable. The runtime dependency
# is declared in requirements.txt; on a dev box without it, the GUI tests
# can't run at all.
pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import QApplication  # noqa: E402

# Make sure the project root is on sys.path so `from app...` / `from ui...`
# work even when pytest is invoked from a different cwd.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config import AppConfig  # noqa: E402
from ui.themes_catalog import THEMES, theme_ids  # noqa: E402


# --- shared fixtures --------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """A single QApplication shared across all tests in the session.

    pytest-qt provides its own ``qapp`` fixture, but only if no QApplication
    exists yet. We create one here so the tests work even when pytest-qt's
    fixture isn't picked up (e.g. when the tests are run via ``python -m
    pytest`` without the plugin loaded).
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Isolate per-user data + config so tests can't trample a real install.

    Sets ``LOCALAPPDATA`` (used by AppConfig.default_data_dir) to a temp
    dir and ensures the bundled-zapret auto-detection doesn't pick up a
    real install next to the project.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def main_window(qapp, isolated_env, monkeypatch):
    """Build a MainWindow WITHOUT triggering the first-run bootstrap
    download or any background update checks.

    The window is constructed with ``start_minimized=False`` (so it doesn't
    hide itself), and every network/background path that fires on a real
    launch is stubbed out. The fixture yields the window and properly
    tears it down (cancels timers, stops the TG runner, etc.) at the end
    so we don't leak QTimers between tests.
    """
    # Stub out the bootstrap + update paths so no network I/O happens.
    from app import bootstrap
    from ui import main_window as mw_mod

    monkeypatch.setattr(bootstrap, "is_installed", lambda *_: False)
    # _ensure_ready would normally call _start_bootstrap which spawns a
    # QThread; replace it with a no-op so the window stays in a clean
    # "no zapret installed yet" state.
    monkeypatch.setattr(mw_mod.MainWindow, "_ensure_ready", lambda self: None)
    monkeypatch.setattr(mw_mod.MainWindow, "check_updates_async", lambda self: None)
    monkeypatch.setattr(mw_mod.MainWindow, "_tg_check_updates_async", lambda self: None)
    monkeypatch.setattr(mw_mod.MainWindow, "_tg_restore_state", lambda self: None)
    # Tray icon — show() requires a system tray; on headless CI it would
    # warn. Stubbed at the Tray class level so the MainWindow still gets a
    # Tray instance, just without the visible icon.
    from ui.tray import Tray
    monkeypatch.setattr(Tray, "show", lambda self: None)

    config = AppConfig.load()
    win = mw_mod.MainWindow(config, start_minimized=False)
    try:
        yield win
    finally:
        # Clean shutdown so QTimers don't leak into the next test.
        # Order matters: stop timers → stop engines → drop refs → process
        # pending events so Qt can safely tear down widget tree.
        try:
            if hasattr(win, "_status_timer"):
                win._status_timer.stop()
        except Exception:
            pass
        try:
            win._force_quit = True
            win._user_stop = True
            win.runner.stop()
            win.tg_runner.stop()
            win.tg_runner.wait_for_stop(timeout=2.0)
        except Exception:
            pass
        try:
            win.hide()
            win.deleteLater()
        except Exception:
            pass
        # Process pending deleteLater() calls so the widget tree is gone
        # before the next test creates a fresh MainWindow. Without this
        # PyQt6 sometimes holds stale references that lead to a segfault
        # on interpreter shutdown when ddtrace is present.
        try:
            qapp.processEvents()
        except Exception:
            pass


# --- tests ------------------------------------------------------------------

def test_main_window_constructs(main_window):
    """MainWindow must construct without raising. This catches import
    errors, typos in objectNames referenced from QSS, and broken
    signal/slot connections — none of which the logic tests exercise."""
    assert main_window.windowTitle() == "Zapret GUI"
    # All 5 tabs must have been added.
    assert main_window.tabs.count() == 5


def test_all_themes_apply_without_error(main_window):
    """Every theme in the catalog (3 presets + 7 image) must apply cleanly.

    Catches:
      * QSS substitution bugs (an unknown colour token in DARK_QSS would
        leak through and break the palette);
      * missing background image files (would silently fall back to the
        purple gradient — a regression we already fixed);
      * crash in set_theme_colors() for image themes;
      * crash in the nav glow / shadow reconfiguration.
    """
    for theme_id in theme_ids():
        main_window._toggle_theme(theme_id, checked=True)
        assert main_window.current_theme == theme_id, (
            f"Theme {theme_id!r} did not stick — saved theme is "
            f"{main_window.current_theme!r}"
        )
        # The QSS must be non-empty for every theme.
        qss = main_window.styleSheet()
        assert qss and qss.strip(), f"Theme {theme_id!r} produced empty QSS"


def test_tab_switching_does_not_crash(main_window):
    """Switching to every tab index must not raise. Catches regressions
    in _fade_current_tab (QGraphicsOpacityEffect) and _update_bg_mode."""
    for idx in range(main_window.tabs.count()):
        main_window.tabs.setCurrentIndex(idx)
        assert main_window.tabs.currentIndex() == idx


def test_language_toggle_round_trip(main_window):
    """Toggling the language ru → en → ru must not crash and must update
    the stored config. The English UI strings come from _TRANSLATIONS; a
    KeyError in the translation table would raise here."""
    assert main_window.lang == "ru"
    main_window._toggle_language()
    assert main_window.lang == "en"
    main_window._toggle_language()
    assert main_window.lang == "ru"


def test_theme_persists_after_window_rebuild(main_window, isolated_env):
    """The theme-validation fix from audit Rec #1: the saved theme must
    survive a fresh AppConfig.load(). We pick an image theme, save it,
    reload the config, and verify the same id comes back."""
    # Pick the first image theme (e.g. "mist").
    image_theme = next(t.id for t in THEMES if t.group == "image")
    main_window._toggle_theme(image_theme, checked=True)
    main_window.config.save()
    # Reload from disk.
    reloaded = AppConfig.load()
    assert reloaded.theme == image_theme, (
        f"Theme {image_theme!r} did not persist; reload gave {reloaded.theme!r}. "
        f"This is the audit Rec #1 regression — the GUI was filtering image "
        f"theme ids against only ('purple','light','dark')."
    )


def test_tg_dc_ip_field_round_trips_to_runner(main_window):
    """Editing the DC IP field on the TG tab must update both the config
    and the runner, so the next proxy start uses the new IPs.

    Note on the default: the field is intentionally left EMPTY on a fresh
    profile. Since tg-ws-proxy v1.8+ an empty value means "auto" — the engine
    maps all known DCs itself, which is the recommended mode. Pre-filling the
    field would silently pin the user to a single hard-coded DC IP.
    """
    assert hasattr(main_window, "tg_dc_edit"), "TG DC IP edit field missing"
    # Default on a clean profile: empty field, no overrides anywhere.
    assert main_window.tg_dc_edit.text() == ""
    assert main_window.config.tg_proxy_dc_ips == []
    # Simulate the user typing a custom value.
    main_window.tg_dc_edit.setText("3:149.154.175.100, 5:91.105.192.100")
    main_window._on_tg_dc_ips_edited()
    # The config must now hold the overrides.
    assert main_window.config.tg_proxy_dc_ips == [
        "3:149.154.175.100", "5:91.105.192.100"
    ]
    # The runner must have picked them up too.
    assert main_window.tg_runner.get_dc_ips() == [
        "3:149.154.175.100", "5:91.105.192.100"
    ]
    # Clearing the field must drop the overrides again (back to "auto").
    main_window.tg_dc_edit.setText("")
    main_window._on_tg_dc_ips_edited()
    assert main_window.config.tg_proxy_dc_ips == []
    assert main_window.tg_runner.get_dc_ips() == []


def test_engine_args_filter_without_roblox_is_passthrough(main_window):
    """_engine_args_filter must return args unchanged when Roblox combine
    is off. Catches a regression where the filter would always inject
    Roblox args (would break every non-Roblox strategy)."""
    main_window.config.roblox_combine = False
    args = ["--wf-tcp=443", "--dpi-desync=fake"]
    out = main_window._engine_args_filter(list(args))
    assert out == args


def test_engine_args_filter_with_roblox_injects_profile(main_window):
    """With roblox_combine on, the filter must merge the Roblox profile
    into the args. We don't check exact arg layout (covered by the logic
    tests for combine_with_roblox) — we only verify the UDP filter and
    ipset appear, proving the merge actually ran."""
    main_window.config.roblox_combine = True
    args = ["--wf-tcp=443", "--dpi-desync=fake"]
    out = main_window._engine_args_filter(list(args))
    joined = " ".join(out)
    assert "--filter-udp=49152-65535" in joined, "Roblox UDP filter missing"
    assert "--ipset-ip=" in joined, "Roblox ipset missing"
    # The original TCP filter must still be there.
    assert "--wf-tcp=443" in joined


def test_tray_menu_has_tg_submenu(main_window):
    """The tray context menu must include a Telegram submenu (added so the
    user can control the proxy from the tray without opening the window).
    Catches a regression where _build_tg_menu fails silently."""
    tray = main_window.tray
    assert hasattr(tray, "tg_menu"), "Tray has no TG submenu"
    assert tray.tg_menu is not None
    # The submenu must have at least the 5 actions we wired up.
    actions = tray.tg_menu.actions()
    assert len(actions) >= 5, (
        f"Tray TG submenu has only {len(actions)} actions, expected >= 5"
    )
