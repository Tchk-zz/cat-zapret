"""Conftest for GUI smoke tests.

Sets LD_LIBRARY_PATH so PyQt6 can find libEGL on the CI sandbox (where
apt-installed system libraries aren't available — we reuse the libEGL.so
shipped with the Playwright Chromium bundle), and forces the Qt offscreen
platform so no X server / display is needed.
"""
import os
from pathlib import Path

# Reuse libEGL.so from the Playwright Chromium install if the system doesn't
# ship one. This lets PyQt6 import on a minimal Linux sandbox without root.
_playwright_lib = Path("/home/z/.cache/ms-playwright/chromium-1228/chrome-linux64")
if _playwright_lib.is_dir():
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    if str(_playwright_lib) not in cur:
        os.environ["LD_LIBRARY_PATH"] = (
            str(_playwright_lib) + (":" + cur if cur else "")
        )

# Force offscreen Qt platform so tests run on a headless box.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
