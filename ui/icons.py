"""Vector (SVG) icons for the top navigation, recoloured per theme.

The icon files in ``ui/assets/icons`` are single-colour line drawings authored
on a 24x24 grid with a white, 2-unit stroke. Instead of shipping one file per
theme they are rasterised once and tinted with ``CompositionMode_SourceIn``,
which keeps the anti-aliased edges and replaces only the colour.

Sharpness is the whole point of the arithmetic below. main.py squeezes the UI
with a fractional ``QT_SCALE_FACTOR`` (about 0.886 on a 1920x1080 screen), so:

  * rendering at the logical size and letting Qt rescale on paint softens every
    stroke (the first attempt's blur);
  * even rendering at the physical size blurs if that size is not a whole
    multiple of the 24-unit grid -- a 2-unit stroke then lands on a fractional
    number of pixels and gets spread across two of them.

So the icons are rendered at exactly ``PHYSICAL_PX`` device pixels, chosen as a
multiple of the 24-unit viewBox: one SVG unit becomes a whole pixel and the
2-unit strokes come out exactly 2 pixels wide. The widget-side (logical) size is
derived from that, so the icon occupies the right amount of layout space.

Rendered icons are cached by (name, colour, physical size).
"""

from __future__ import annotations

from typing import Dict, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .effects import ui_scale
from .paths import asset_path_or_empty

# Navigation section -> icon file name, in the same order as the tabs.
NAV_ICON_NAMES = ("home", "settings", "strategy", "games", "telegram")

# Device pixels per icon. Must stay a multiple of the 24-unit viewBox (24 -> 1
# unit = 1 px, 48 -> 1 unit = 2 px) or the strokes stop being pixel-aligned.
PHYSICAL_PX = 24

_cache: Dict[Tuple[str, str, int], QIcon] = {}


def _scale() -> float:
    try:
        value = float(ui_scale())
    except Exception:
        return 1.0
    return value if value > 0.01 else 1.0


def nav_icon_size() -> int:
    """Logical (widget-side) icon size that maps onto PHYSICAL_PX real pixels.

    Pass this to ``setIconSize``. Under a squeezed UI it is larger than
    PHYSICAL_PX, which is exactly the point: the widget reserves enough logical
    room for a full-resolution glyph.
    """
    return max(1, int(round(PHYSICAL_PX / _scale())))


def _icon_file(name: str) -> str:
    return asset_path_or_empty(f"icons/{name}.svg")


def themed_icon(name: str, color: str) -> QIcon:
    """Return the named SVG icon tinted with ``color``.

    Returns an empty QIcon when the file is missing or unreadable, so a lost
    asset degrades to a text-only tab instead of breaking the window.
    """
    key = (name, color, PHYSICAL_PX)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    icon = QIcon()
    path = _icon_file(name)
    if path:
        renderer = QSvgRenderer(path)
        if renderer.isValid():
            px = QPixmap(PHYSICAL_PX, PHYSICAL_PX)
            px.fill(Qt.GlobalColor.transparent)
            painter = QPainter(px)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, PHYSICAL_PX, PHYSICAL_PX))
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(px.rect(), QColor(color))
            painter.end()
            # Mark the pixmap as already being at device resolution: Qt then
            # blits it 1:1 instead of resampling it down to the logical size.
            px.setDevicePixelRatio(PHYSICAL_PX / float(nav_icon_size()))
            icon = QIcon(px)

    _cache[key] = icon
    return icon


def nav_icons(color: str) -> list[QIcon]:
    """Icons for the five top-level sections, in tab order."""
    return [themed_icon(name, color) for name in NAV_ICON_NAMES]
