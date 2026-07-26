"""Entry point for Zapret GUI.

Ensures the process runs with administrator rights (WinDivert needs them),
then launches the PyQt6 application.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

# Make sure ``app`` and ``ui`` packages are importable when frozen or run as a
# script from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


# Kept alive for the whole process lifetime: releasing the handle would let a
# second copy of the app start.
_INSTANCE_MUTEX = None
_MUTEX_NAME = "Global\\ZapretGUI_SingleInstance_Mutex"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance() -> bool:
    """True if this is the only running instance.

    Without this guard every launch (Start menu, autostart, desktop shortcut,
    a second double-click while the window is minimised to tray) spawned a
    whole new app: several tray icons, several winws.exe children fighting
    over WinDivert, and settings overwriting each other.
    """
    global _INSTANCE_MUTEX
    if not sys.platform.startswith("win"):
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if not handle:
            return True  # can't tell — never block the user out of the app
        if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
            return False
        _INSTANCE_MUTEX = handle
        return True
    except Exception:
        return True


def _focus_existing_instance() -> bool:
    """Bring the already-running window to the front instead of duplicating it."""
    if not sys.platform.startswith("win"):
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "Zapret GUI")
        if not hwnd:
            return False
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


# Design canvas the whole interface is laid out against.
DESIGN_WIDTH = 1240
DESIGN_HEIGHT = 900
# The window should never eat more than this share of the usable desktop.
_MAX_HEIGHT_SHARE = 0.78
_MAX_WIDTH_SHARE = 0.64
_MIN_SCALE = 0.62


def scale_factor_for(work_w: float, work_h: float) -> float:
    """Return the UI scale factor for a desktop work area of this size.

    Pure arithmetic (no Windows calls) so it can be unit-tested: 1.0 means
    "draw at the design size", smaller values shrink the whole interface.
    """
    if work_w <= 0 or work_h <= 0:
        return 1.0
    factor = min(
        1.0,
        (work_h * _MAX_HEIGHT_SHARE) / DESIGN_HEIGHT,
        (work_w * _MAX_WIDTH_SHARE) / DESIGN_WIDTH,
    )
    return max(factor, _MIN_SCALE)  # never shrink into unreadability


def _apply_ui_scale() -> None:
    """Scale the whole UI down when the desktop is smaller than the design size.

    The interface is drawn against a 1240x900 design canvas, which looks right
    on 1440p but eats almost the entire usable height of a 1080p desktop.
    QT_SCALE_FACTOR scales *everything* (fonts, paddings, fixed widget sizes
    from QSS) uniformly, so the layout stays pixel-identical, just smaller.
    Must be set before QApplication is constructed.
    """
    if not sys.platform.startswith("win"):
        return
    if os.environ.get("QT_SCALE_FACTOR"):
        return  # respect an explicit user/env override
    try:
        import ctypes.wintypes

        SPI_GETWORKAREA = 0x0030
        rect = ctypes.wintypes.RECT()
        if not ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
        ):
            return
        # Physical pixels -> Qt logical pixels (Qt already applies system DPI).
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        dpi_scale = max(dpi, 96) / 96.0
        work_w = (rect.right - rect.left) / dpi_scale
        work_h = (rect.bottom - rect.top) / dpi_scale
        if work_w <= 0 or work_h <= 0:
            return
        factor = scale_factor_for(work_w, work_h)
        if factor < 0.98:
            os.environ["QT_SCALE_FACTOR"] = f"{factor:.3f}"
    except Exception:
        pass


def _is_admin() -> bool:
    if not sys.platform.startswith("win"):
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> bool:
    """Try to relaunch the current program elevated. Returns True if launched."""
    if not sys.platform.startswith("win"):
        return False
    try:
        if getattr(sys, "frozen", False):
            program = sys.executable
            params = " ".join(sys.argv[1:])
        else:
            program = sys.executable
            params = " ".join([f'"{a}"' for a in sys.argv])
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", program, params, None, 1
        )
        return rc > 32
    except Exception:
        return False


def main() -> int:
    if not _is_admin():
        # Relaunch elevated; if the user accepts UAC, this instance exits.
        if _relaunch_as_admin():
            return 0
        # Otherwise continue without admin \u2014 the engine will warn on start.

    # Single instance: if the app is already running, just bring its window to
    # the front and exit. Prevents a pile of tray icons and duplicate engines.
    if not _acquire_single_instance():
        _focus_existing_instance()
        return 0

    # Fit the 1240x900 design canvas onto smaller desktops (e.g. 1080p).
    _apply_ui_scale()

    from PyQt6.QtWidgets import QApplication, QMessageBox

    from app.config import AppConfig
    from ui.main_window import MainWindow

    # Start the log file first: everything below may fail silently, and the
    # journal is the only way to find out why afterwards.
    import app as app_pkg
    from app import applog
    applog.setup()
    applog.log_startup(app_pkg.__version__)
    _log = applog.get_logger("start")

    # Safety net: in PyQt6 an unhandled exception in any slot/worker aborts the
    # whole process (the app "just closes"). Route exceptions to a log + dialog
    # instead so the window stays open.
    import traceback

    def _excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            _log.error("unhandled exception:\n%s", text)
        except Exception:
            pass
        try:
            from app.config import default_data_dir
            log_path = default_data_dir() / "crash.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except Exception:
            pass
        try:
            QMessageBox.critical(None, "Zapret GUI", "\u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430:\n\n" + str(exc_value))
        except Exception:
            pass

    sys.excepthook = _excepthook

    # Crisp text on fractional-DPI Windows displays (prevents blurry/pixelated
    # scaling of the UI font). Must be set before QApplication is created.
    try:
        from PyQt6.QtCore import Qt as _Qt
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            _Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    # Windows shows the taskbar icon of whatever process owns the window
    # group. When running from source that process is python.exe, so the
    # taskbar shows the Python logo instead of ours. Declaring our own
    # AppUserModelID makes Windows use the window icon we set below.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "CatZapret.ZapretGUI"
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Zapret GUI")
    app.setQuitOnLastWindowClosed(False)

    # Register the bundled Unbounded font and use it as the base UI font.
    # Headings/buttons are bumped to Medium via QSS; code/log areas stay
    # monospace. Falls back silently to the system font if registration fails.
    try:
        from PyQt6.QtGui import QFont
        from ui.theme import load_app_fonts
        _fam = load_app_fonts()
        if _fam:
            _font = QFont(_fam)
            _font.setWeight(QFont.Weight.Normal)  # body ~400
            # Smooth, non-pixelated rendering for this display font.
            _font.setStyleStrategy(
                QFont.StyleStrategy.PreferAntialias
                | QFont.StyleStrategy.PreferQuality
            )
            _font.setHintingPreference(
                QFont.HintingPreference.PreferNoHinting
            )
            app.setFont(_font)
    except Exception:
        pass

    try:
        from ui.main_window import app_icon
        _ic = app_icon()
        if not _ic.isNull():
            app.setWindowIcon(_ic)
    except Exception:
        pass

    config = AppConfig.load()
    # zapret is downloaded automatically on first run (MainWindow handles it).

    minimized = "--minimized" in sys.argv
    win = MainWindow(config, start_minimized=minimized)
    if not minimized:
        win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
