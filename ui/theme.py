"""Theme facade.

Kept so existing ``from .theme import ...`` imports keep working.
New code may import from .fonts, .qss or .gradient_background directly.
"""

from .fonts import UNBOUNDED_FAMILY, load_app_fonts, smooth_code_font
from .gradient_background import GradientBackground
from .qss import DARK_QSS, WIN11_DARK_QSS, WIN11_LIGHT_QSS

__all__ = [
    "UNBOUNDED_FAMILY",
    "DARK_QSS",
    "WIN11_DARK_QSS",
    "WIN11_LIGHT_QSS",
    "GradientBackground",
    "load_app_fonts",
    "smooth_code_font",
]
