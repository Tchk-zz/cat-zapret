"""Font loading helpers shared across the UI."""

import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase

from .paths import asset_path_or_empty

UNBOUNDED_FAMILY = "Unbounded"


def smooth_code_font(size: int = 12) -> QFont:
    """Readable anti-aliased monospace font for code/log widgets.

    Lives here (not in main_window) so the strategy editor, the log view and
    the hosts dialog can all reach it without importing the window module.
    """
    font = QFont("Cascadia Mono")
    font.setFamilies(["Cascadia Mono", "Consolas", "Liberation Mono", "Courier New"])
    font.setPointSize(size)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias
        | QFont.StyleStrategy.PreferQuality
    )
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _font_path(filename: str) -> str:
    """Locate a bundled font, both from source and when frozen by PyInstaller."""
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass) / "ui" / "assets" / "fonts")
        roots.append(Path(meipass) / "assets" / "fonts")
    here = Path(__file__).resolve().parent
    roots.append(here / "assets" / "fonts")
    for root in roots:
        cand = root / filename
        try:
            if cand.is_file():
                return str(cand)
        except OSError:
            pass
    return ""


# Shared with main_window and tray (see ui/paths.py). Returns "" when the
# image is missing so the callers below can skip loading it.
_asset_path = asset_path_or_empty


def load_app_fonts() -> str:
    """Register the bundled Unbounded font. Returns the family name, or "" on failure."""
    path = _font_path("Unbounded-VariableFont_wght.ttf")
    if not path:
        return ""
    try:
        fid = QFontDatabase.addApplicationFont(path)
        if fid == -1:
            return ""
        fams = QFontDatabase.applicationFontFamilies(fid)
        return fams[0] if fams else ""
    except Exception:
        return ""
