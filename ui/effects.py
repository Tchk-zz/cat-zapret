"""Central switch for Qt graphics effects (drop shadows and glows).

Why this exists
---------------
main.py shrinks the whole interface with ``QT_SCALE_FACTOR`` when the desktop
is smaller than the 1240x900 design canvas -- on a 1920x1080 screen that comes
out as ~0.886. Qt turns that into a device pixel ratio below 1.

Every ``QGraphicsEffect`` is composited through an offscreen pixmap whose size
is derived from that ratio. At a ratio below 1 the pixmap is *smaller* than the
area the effect paints into, so the blurred result is scaled back up, lands off
the pixel grid and is clipped to the pixmap bounds. Visually that is exactly
what users report on Full HD:

* square, hard-cut corners around the power button's glow,
* dark bands and leftover "ghost" strips under the home panels,
* the glow appearing to shake, because the animated blur radius rounds to a
  different pixmap size on nearly every frame.

Widgets without an effect are unaffected -- plain painting handles a fractional
ratio fine. Both the effects and the scaling arrived in the same 1.7.3 release,
which is why the two have always shipped broken together on Full HD.

Rather than removing the effects (they look correct at scale 1.0, e.g. on 1440p
displays) we install them only when the ratio is safe.
"""
from __future__ import annotations

import os

from PyQt6.QtWidgets import QGraphicsEffect, QWidget

# Below this the offscreen pixmap is smaller than the painted area. 0.999
# rather than 1.0 keeps float formatting noise ("0.999") on the safe side.
_MIN_SAFE_SCALE = 0.999


def ui_scale() -> float:
    """Return the UI scale main.py settled on (1.0 when it did not scale)."""
    raw = os.environ.get("QT_SCALE_FACTOR", "").strip()
    if not raw:
        return 1.0
    try:
        value = float(raw)
    except ValueError:
        return 1.0
    return value if value > 0 else 1.0


def effects_supported() -> bool:
    """True when QGraphicsEffect composites correctly at the current scale."""
    return ui_scale() >= _MIN_SAFE_SCALE


def apply_effect(widget: QWidget, effect: QGraphicsEffect | None) -> bool:
    """Install ``effect`` on ``widget`` unless the current scale would break it.

    Clearing an effect (``effect is None``) always goes through. Returns True
    when the effect was actually installed, so callers can skip starting the
    animations that drive it.
    """
    if effect is not None and not effects_supported():
        return False
    widget.setGraphicsEffect(effect)
    return effect is not None
