"""Compatibility facade for the custom widgets.

The widgets themselves now live in topic modules (widgets_power,
widgets_nav, widgets_popups, widgets_home, widgets_settings). This module
keeps the historical import path working, so ``from .widgets_custom import
PowerButton`` still does the right thing.
"""
from __future__ import annotations

from .widgets_power import _ShimmerPlate, PowerButton
from .widgets_nav import _GlassNav, GamesColumnIcon
from .widgets_popups import (
    BypassTestPopup, StyledPopup, AnimatedGradientProgressBar, AutoSelectProgressPopup,
    POPUP_QSS, POPUP_DARK_QSS, POPUP_LIGHT_QSS,
)
from .widgets_home import (
    _paint_dark_3d_surface, _Dark3DPanel, _Dark3DButton, _DarkAnimatedProgressBar,
    _HomeAutoSelectPanel, _SleepZWidget,
)
from .widgets_settings import _SettingsRow

__all__ = [
    "_ShimmerPlate",
    "PowerButton",
    "_GlassNav",
    "BypassTestPopup",
    "StyledPopup",
    "AnimatedGradientProgressBar",
    "AutoSelectProgressPopup",
    "POPUP_QSS",
    "POPUP_DARK_QSS",
    "POPUP_LIGHT_QSS",
    "GamesColumnIcon",
    "_paint_dark_3d_surface",
    "_Dark3DPanel",
    "_Dark3DButton",
    "_DarkAnimatedProgressBar",
    "_HomeAutoSelectPanel",
    "_SleepZWidget",
    "_SettingsRow",
]
