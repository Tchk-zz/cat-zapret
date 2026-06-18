"""Entry point for Zapret GUI.

Ensures the process runs with administrator rights (WinDivert needs them),
then launches the PyQt6 application.
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

# Make sure ``app`` and ``ui`` packages are importable when frozen or run as a
# script from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


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

    from PyQt6.QtWidgets import QApplication, QMessageBox

    from app.config import AppConfig
    from ui.main_window import MainWindow

    # Safety net: in PyQt6 an unhandled exception in any slot/worker aborts the
    # whole process (the app "just closes"). Route exceptions to a log + dialog
    # instead so the window stays open.
    import traceback

    def _excepthook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
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
