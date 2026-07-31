"""Regenerate the shipped UI bitmaps from the originals in ``assets_src/``.

Why this exists
---------------
The three mascot PNGs and the dark backdrop were authored on a 5167x3750
canvas. The interface never paints them larger than a few hundred logical
pixels, but Qt decodes a QPixmap at its full stored size: 5167 * 3750 * 4
bytes is about 74 MB of RAM per image -- roughly 300 MB for the four of them,
which is where most of the app's memory footprint used to go.

This script rewrites them at the size the UI actually needs. The untouched
originals stay in ``assets_src/``, which is deliberately NOT collected by
``zapret-gui.spec`` (that only walks ``ui/assets``), so the step is fully
reversible and can be re-run after an artist updates an original.

Layout safety
-------------
``ui/tab_home.py`` derives the mascot height from the pixmap's own aspect
ratio::

    cat_h = int(cat_w * pm.height() / max(1, pm.width()))

A naive resize can change that integer by a pixel and shift the cat over the
power button. ``_target_height`` therefore picks the new height so the value
the layout computes stays byte-for-byte identical to the original.

Usage::

    python tools/optimize_assets.py            # rewrite ui/assets copies
    python tools/optimize_assets.py --check     # report only, change nothing
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - dev-only tool
    print("optimize_assets: Pillow is required (pip install -r requirements-dev.txt)")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "assets_src"
OUT_DIR = ROOT / "ui" / "assets"

# file name -> (target width in px, layout base width or None)
#
# target width: the widest the image is ever painted, times a safety factor for
#   high-DPI screens (the mascot is drawn at 256 logical px, the backdrop at up
#   to 1240 logical px; both get a 2x buffer).
# layout base: the logical width ui/tab_home.py uses when it derives the height
#   from the pixmap ratio. None means no code depends on the exact ratio.
SPECS: dict[str, tuple[int, int | None]] = {
    "home_cat.png": (640, 256),
    "home_cat_closed.png": (640, 256),
    "home_cat_search.png": (640, 256),
    "bg_dark.png": (2480, None),
}


def _target_height(orig_w: int, orig_h: int, new_w: int, layout_base: int | None) -> int:
    """Height for ``new_w`` that keeps the layout's derived size unchanged."""
    exact = new_w * orig_h / orig_w
    if layout_base is None:
        return max(1, round(exact))
    # What ui/tab_home.py computes today, from the original pixmap.
    want = int(layout_base * orig_h / orig_w)
    candidates = {round(exact), int(exact), int(exact) + 1, int(exact) - 1}
    for height in sorted(candidates, key=lambda c: abs(c - exact)):
        if height > 0 and int(layout_base * height / new_w) == want:
            return height
    return max(1, round(exact))


def _human(num_bytes: int) -> str:
    return f"{num_bytes / 1024:.0f} KB"


def _decoded_mb(width: int, height: int) -> float:
    """RAM a QPixmap of this size occupies (32-bit ARGB)."""
    return width * height * 4 / (1024 * 1024)


def process(name: str, target_w: int, layout_base: int | None, check_only: bool) -> bool:
    """Rewrite one asset. Returns True when the file on disk is up to date."""
    src = SRC_DIR / name
    dst = OUT_DIR / name
    if not src.is_file():
        print(f"  {name}: MISSING in assets_src/ -- skipped")
        return False

    with Image.open(src) as img:
        orig_w, orig_h = img.size
        if orig_w <= target_w:
            # Nothing to gain; ship the original verbatim.
            if not check_only and (not dst.is_file() or dst.stat().st_size != src.stat().st_size):
                shutil.copy2(src, dst)
            print(f"  {name}: {orig_w}x{orig_h} already within budget")
            return True

        new_h = _target_height(orig_w, orig_h, target_w, layout_base)
        mode = img.mode
        if mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGBA")
            mode = "RGBA"
        resized = img.resize((target_w, new_h), Image.Resampling.LANCZOS)

    before_bytes = dst.stat().st_size if dst.is_file() else src.stat().st_size
    if check_only:
        print(
            f"  {name}: {orig_w}x{orig_h} -> {target_w}x{new_h} "
            f"({_decoded_mb(orig_w, orig_h):.0f} MB -> {_decoded_mb(target_w, new_h):.1f} MB in RAM)"
        )
        return False

    resized.save(dst, format="PNG", optimize=True, compress_level=9)
    after_bytes = dst.stat().st_size
    layout_note = ""
    if layout_base is not None:
        want = int(layout_base * orig_h / orig_w)
        got = int(layout_base * new_h / target_w)
        layout_note = f", layout height {got}px (was {want}px)"
    print(
        f"  {name}: {orig_w}x{orig_h} -> {target_w}x{new_h}, "
        f"{_human(before_bytes)} -> {_human(after_bytes)}, "
        f"RAM {_decoded_mb(orig_w, orig_h):.0f} MB -> {_decoded_mb(target_w, new_h):.1f} MB"
        f"{layout_note}"
    )
    return layout_base is None or want == got


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report what would change",
    )
    args = parser.parse_args(argv)

    if not SRC_DIR.is_dir():
        print(f"optimize_assets: {SRC_DIR} not found")
        return 1
    if not OUT_DIR.is_dir():
        print(f"optimize_assets: {OUT_DIR} not found")
        return 1

    print(f"{'Checking' if args.check else 'Optimizing'} {len(SPECS)} assets")
    ok = True
    for name, (target_w, layout_base) in SPECS.items():
        ok = process(name, target_w, layout_base, args.check) and ok
    if args.check:
        return 0
    if not ok:
        print("optimize_assets: a layout-derived size changed -- review before committing")
        return 1
    print("optimize_assets: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
