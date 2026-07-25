"""Shared asset lookup for the UI layer.

The same "find a bundled image" helper used to be copy-pasted into
main_window.py, theme.py and tray.py. It lives here now so there is exactly
one place that knows where assets are, both when running from source
(ui/assets) and when frozen by PyInstaller (sys._MEIPASS/ui/assets).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List


def _roots() -> List[Path]:
    """Folders to search, most specific first."""
    roots: List[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass) / "ui" / "assets")
        roots.append(Path(meipass) / "assets")
    roots.append(Path(__file__).resolve().parent / "assets")
    return roots


def _find(name: str) -> str:
    for root in _roots():
        cand = root / name
        try:
            if cand.is_file():
                return str(cand)
        except OSError:
            pass
    return ""


def asset_path(name: str) -> str:
    """Return the absolute path of a bundled UI asset by file name.

    If the asset is missing, returns the path it *would* have had, so callers
    get something predictable to log instead of an exception.
    """
    found = _find(name)
    if found:
        return found
    return str(_roots()[-1] / name)


def asset_path_or_empty(name: str) -> str:
    """Same lookup, but returns "" when the asset does not exist.

    theme.py and tray.py rely on the empty string to fall back to a drawn
    placeholder instead of trying to load a non-existent file.
    """
    return _find(name)
