"""Zapret GUI application package."""

from __future__ import annotations

import sys
from pathlib import Path

_FALLBACK_VERSION = "0.0.0"


def _read_version() -> str:
    """Return the app version from the VERSION file (single source of truth).

    The VERSION file in the project root is the ONLY place the version is
    edited by hand:

    * build_installer.bat reads it and passes it to ISCC as /DMyAppVersion,
    * installer.iss ships it next to the exe,
    * app/self_updater.local_version() reads that shipped copy.

    This module used to hardcode the version as well, which immediately drifted
    (it still said "1.0.0" while the app was at 1.8.4), so it is read from the
    same file instead of being duplicated.

    Frozen builds are checked in two places: PyInstaller unpacks bundled data
    into sys._MEIPASS, while the installer also puts VERSION next to the exe.
    The file next to the exe wins because that is what the self-updater sees.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "VERSION")
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass) / "VERSION")
    else:
        candidates.append(Path(__file__).resolve().parent.parent / "VERSION")

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return _FALLBACK_VERSION


__version__ = _read_version()
