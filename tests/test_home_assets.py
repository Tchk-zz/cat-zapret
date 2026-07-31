"""Guards for the Home-tab bitmaps and the lazy mascot loader.

Two regressions are locked down here.

1. **Asset size budget.** The three mascot frames and the dark backdrop used to
   ship on a 5167x3750 canvas. Qt decodes a QPixmap at its stored size, so each
   of those files cost ~74 MB of RAM (5167 * 3750 * 4 bytes) -- about 300 MB for
   the four of them, most of the app's footprint. ``tools/optimize_assets.py``
   regenerates them from ``assets_src/``; this test fails if an oversized bitmap
   ever lands in ``ui/assets`` again.

2. **Lazy mascot loading.** ``HomeTabMixin`` no longer decodes all three frames
   while building the Home tab: the classic presets never show the cat and the
   "searching" frame only appears during auto-select. The frames must be loaded
   on first use, cached, and pre-scaled to the label size.

The budget test is pure stdlib (it parses the PNG IHDR chunk itself) so it runs
everywhere, including without Pillow. The loader test needs PyQt6 and is skipped
when it is unavailable.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:  # ``python -m unittest discover`` without dev deps.
    import unittest
    raise unittest.SkipTest("pytest is not installed; asset tests skipped")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

ASSETS = _PROJECT_ROOT / "ui" / "assets"

# Decoded (32-bit ARGB) megabytes a single bitmap may occupy in RAM.
DEFAULT_BUDGET_MB = 12.0
# The dark backdrop covers the whole window and is kept at 2x the 1240x900
# design size for high-DPI screens, so it gets a larger allowance.
PER_FILE_BUDGET_MB = {"bg_dark.png": 20.0}
# The mascot is painted 256 logical px wide; anything far above that is waste.
MASCOT_MAX_WIDTH = 800
MASCOT_FILES = ("home_cat.png", "home_cat_closed.png", "home_cat_search.png")


def _png_size(path: Path) -> tuple[int, int]:
    """Return (width, height) from a PNG's IHDR chunk, without Pillow."""
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path.name} is not a valid PNG")
    if header[12:16] != b"IHDR":
        raise AssertionError(f"{path.name}: first chunk is not IHDR")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _decoded_mb(width: int, height: int) -> float:
    return width * height * 4 / (1024 * 1024)


def test_every_shipped_png_fits_the_memory_budget():
    """No single bundled bitmap may blow up into tens of MB of RAM."""
    assert ASSETS.is_dir(), f"missing assets directory: {ASSETS}"
    offenders = []
    for path in sorted(ASSETS.rglob("*.png")):
        width, height = _png_size(path)
        budget = PER_FILE_BUDGET_MB.get(path.name, DEFAULT_BUDGET_MB)
        decoded = _decoded_mb(width, height)
        if decoded > budget:
            offenders.append(
                f"{path.relative_to(_PROJECT_ROOT)}: {width}x{height} "
                f"= {decoded:.0f} MB decoded (budget {budget:.0f} MB)"
            )
    assert not offenders, (
        "Oversized bitmaps in ui/assets. Regenerate them with "
        "`python tools/optimize_assets.py`:\n  " + "\n  ".join(offenders)
    )


def test_mascot_frames_are_not_stored_at_print_resolution():
    """The mascot is drawn 256px wide; the files must not be huge canvases."""
    for name in MASCOT_FILES:
        path = ASSETS / name
        assert path.is_file(), f"missing mascot frame: {name}"
        width, _height = _png_size(path)
        assert width <= MASCOT_MAX_WIDTH, (
            f"{name} is {width}px wide; the Home tab paints it at 256px. "
            "Run `python tools/optimize_assets.py`."
        )


def test_mascot_frames_share_one_aspect_ratio():
    """Swapping frames must never resize or shift the cat.

    ``ui/tab_home.py`` derives the label height from the "open" frame only, then
    reuses that size for every frame. Different ratios would squash a frame.
    """
    ratios = {}
    for name in MASCOT_FILES:
        width, height = _png_size(ASSETS / name)
        # The layout does: int(256 * height / width)
        ratios[name] = int(256 * height / width)
    assert len(set(ratios.values())) == 1, (
        f"mascot frames disagree on their layout height: {ratios}"
    )


# --- lazy loader -------------------------------------------------------------

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from ui.tab_home import HomeTabMixin  # noqa: E402


class _MascotHost(HomeTabMixin):
    """Minimal stand-in for MainWindow: only the mascot label is needed."""


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture
def mascot_host(qapp):
    host = _MascotHost()
    host.home_cat = QLabel()
    host.home_cat.setFixedSize(256, 185)
    yield host
    host.home_cat.deleteLater()


def test_frames_load_on_demand_and_are_cached(mascot_host):
    """Nothing is decoded until asked for, and each file is decoded once."""
    assert not getattr(mascot_host, "_home_cat_cache", {}), (
        "a mascot frame was decoded before anything requested it"
    )
    first = mascot_host._home_cat_frame_pixmap("open")
    assert isinstance(first, QPixmap)
    assert not first.isNull(), "home_cat.png failed to load"
    assert set(mascot_host._home_cat_cache) == {"open"}, (
        "asking for the open frame must not pull in the other frames"
    )
    # The second call must hand back the very same object, not a new decode.
    assert mascot_host._home_cat_frame_pixmap("open") is first


def test_scaled_frames_match_the_label_and_are_cached(mascot_host):
    """Frames are pre-scaled once per size instead of on every repaint."""
    scaled = mascot_host._home_cat_scaled("closed", 256, 185)
    assert (scaled.width(), scaled.height()) == (256, 185)
    assert mascot_host._home_cat_scaled("closed", 256, 185) is scaled
    # A different size is a different cache entry.
    other = mascot_host._home_cat_scaled("closed", 128, 93)
    assert other is not scaled
    assert (other.width(), other.height()) == (128, 93)


def test_set_home_cat_frame_paints_at_label_size(mascot_host):
    """Every frame can be shown and lands on the label at its exact size."""
    for frame in ("open", "closed", "search"):
        assert mascot_host._set_home_cat_frame(frame) is True, (
            f"frame {frame!r} could not be shown"
        )
        shown = mascot_host.home_cat.pixmap()
        assert not shown.isNull()
        assert (shown.width(), shown.height()) == (256, 185)


def test_missing_label_is_handled(qapp):
    """Before the Home tab exists there is no label; this must not raise."""
    host = _MascotHost()
    assert host._set_home_cat_frame("open") is False
