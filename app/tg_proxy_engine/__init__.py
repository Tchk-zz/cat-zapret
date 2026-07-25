"""Embedded tg-ws-proxy engine (from Flowseal/tg-ws-proxy).

The proxy modules shipped under this package are taken verbatim from
https://github.com/Flowseal/tg-ws-proxy (MIT, Flowseal). We bundle them so the
GUI can run the proxy as a Python asyncio task inside its own process — no
separate ``TgWsProxy.exe`` subprocess, no second tray icon, no double
application. Only the proxy library is imported; the upstream tray UI
(``windows.py``, ``macos.py``, ``linux.py``, ``ui/``) is NOT included.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _read_version() -> str:
    """Read the engine version from the VERSION file shipped with the app.

    The file lives at the project root (next to ``main.py``) when running
    from source, and at ``sys._MEIPASS/VERSION`` when frozen by PyInstaller.
    Falls back to ``"0.0.0"`` if the file is missing (should never happen
    in a real install, but the proxy still works without a version string).
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / "tg_proxy_engine" / "VERSION")
        candidates.append(Path(meipass) / "VERSION")
    candidates.append(Path(__file__).resolve().parent / "VERSION")
    # Backwards-compatible fallback: older builds used the app VERSION for
    # the proxy too. Prefer the package VERSION above so ZapretGUI and the
    # embedded proxy can move independently.
    candidates.append(Path(__file__).resolve().parent.parent.parent / "VERSION")
    for c in candidates:
        try:
            if c.exists():
                text = c.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return "0.0.0"


__version__ = _read_version()
