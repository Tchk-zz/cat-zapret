"""GamesTabMixin — part of MainWindow, kept in its own file.

These methods were moved out of ui/main_window.py unchanged. They are
mixed into MainWindow, so ``self`` still refers to the window and every
attribute they use lives there as before.
"""
from __future__ import annotations

import math
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QThread, QTimer, QPropertyAnimation, QEasingCurve, QVariantAnimation,
    pyqtSignal, QRect, QRectF, QPointF, QPoint, QSize,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QDialog, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app import autostart, bootstrap, editor as editor_mod, list_manager
from app.auto_selector import AutoSelectResult, AutoSelector
from app.config import AppConfig, default_data_dir
from app.process_runner import ProcessRunner
from app.service_manager import ServiceManager
from app.strategy_manager import Strategy, StrategyManager
from app import tg_proxy
from .paths import asset_path
from .tab_telegram import TelegramTabMixin
from .theme import DARK_QSS, WIN11_DARK_QSS, WIN11_LIGHT_QSS, GradientBackground
from .tray import Tray
from .waiting_runner_game import WaitingRunnerGame
from .workers import (
    AutoSelectWorker,
    BootstrapWorker,
    CheckWorker,
    ListUpdateWorker,
    UpdateCheckWorker,
)
from .i18n import (  # noqa: E402
    _TRANSLATIONS,
    _TRANSLATIONS_REVERSE,
    localize_runtime_text,
    tr_text,
)
from .widgets_custom import (  # noqa: E402
    POPUP_DARK_QSS,
    POPUP_LIGHT_QSS,
    POPUP_QSS,
    AnimatedGradientProgressBar,
    AutoSelectProgressPopup,
    BypassTestPopup,
    GamesColumnIcon,
    PowerButton,
    StyledPopup,
    _Dark3DButton,
    _Dark3DPanel,
    _DarkAnimatedProgressBar,
    _GlassNav,
    _HomeAutoSelectPanel,
    _paint_dark_3d_surface,
    _SettingsRow,
    _ShimmerPlate,
    _SleepZWidget,
)


class GamesTabMixin:
    """Mixin: see module docstring."""

    def _build_games_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("gamesRoot")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(46, 14, 46, 16)
        lay.setSpacing(8)

        title = QLabel("Игры и сервисы")
        self.games_title = title
        title.setObjectName("gamesTitle")
        lay.addWidget(title)

        sub = QLabel(
            "Отметь сервис чтобы обход его НЕ трогал (если игра/клиент игры ломается)\n"
            "или, наоборот, применялся к нему. Можно добавить свои домены."
        )
        self.games_subtitle = sub
        sub.setObjectName("gamesSubtitle")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        card = QFrame()
        card.setObjectName("gamesCard")
        card_lay = QVBoxLayout(card)
        # Make the two domain/service columns a bit longer horizontally without
        # changing the order or vertical rhythm of the elements.
        card_lay.setContentsMargins(21, 22, 21, 18)
        card_lay.setSpacing(0)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(24)
        columns.addWidget(
            self._build_list_group(
                "include",
                "Применять обход",
            ),
            1,
        )
        divider = QFrame()
        divider.setObjectName("gamesDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        columns.addWidget(divider)
        columns.addWidget(
            self._build_list_group(
                "exclude",
                "НЕ Применять обход",
            ),
            1,
        )
        card_lay.addLayout(columns, 0)

        note = QLabel(
            "Изменения сохраняются сразу. Если zapret включён — он перезапустится ����втоматически."
        )
        self.games_note = note
        note.setObjectName("gamesNote")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        card_lay.addWidget(note)

        card_lay.addSpacing(4)
        card_lay.addWidget(self._build_game_filter_group())
        lay.addWidget(card, 1)
        return w

    def _build_game_filter_group(self):
        box = QGroupBox("Игровой фильтр (эксперимент)")
        self.games_filter_box = box
        box.setObjectName("gamesFilterBox")
        gl = QVBoxLayout(box)
        gl.setContentsMargins(16, 12, 16, 10)
        gl.setSpacing(5)
        cb = QCheckBox(
            "\u041f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c \u043e\u0431\u0445\u043e\u0434 \u043a \u0438\u0433\u0440\u043e\u0432\u043e\u043c\u0443 \u0442\u0440\u0430\u0444\u0438\u043a\u0443 (\u043f\u043e\u0440\u0442\u044b 1024-65535)"
        )
        self.games_filter_cb = cb
        cb.setObjectName("gamesFilterCheck")
        cb.setChecked(bool(getattr(self.config, "game_filter_enabled", False)))
        cb.toggled.connect(self._toggle_game_filter)
        gl.addWidget(cb)
        gl.addSpacing(4)
        warn = QLabel(
            "\u041f\u0440\u0438\u043c\u0435\u043d\u044f\u0435\u0442 DPI-\u043e\u0431\u0445\u043e\u0434 \u043a \u0438\u0433\u0440\u043e\u0432\u043e\u043c\u0443 UDP/TCP \u043d\u0430 \u0432\u044b\u0441\u043e\u043a\u0438\u0445 \u043f\u043e\u0440\u0442\u0430\u0445. "
            "\u0418\u043d\u043e\u0433\u0434\u0430 \u043f\u043e\u043c\u043e\u0433\u0430\u0435\u0442 (\u0435\u0441\u043b\u0438 \u0441\u0435\u0440\u0432\u0438\u0441 \u0440\u0435\u0436\u0435\u0442\u0441\u044f \u043f\u043e DPI), \u043d\u043e \u0427\u0410\u0429\u0415 \u043b\u043e\u043c\u0430\u0435\u0442 \u0438\u0433\u0440\u044b \u2014 "
            "\u0432 \u0420\u0424 \u043e\u043d\u0438 \u043e\u0431\u044b\u0447\u043d\u043e \u043d\u0435 \u0431\u043b\u043e\u043a\u0438\u0440\u0443\u044e\u0442\u0441\u044f \u043f\u043e DPI. "
            "\u0412\u043a\u043b\u044e\u0447\u0430\u0439 \u0434\u043b\u044f \u0442\u0435\u0441\u0442\u0430; \u0441\u0442\u0430\u043b\u043e \u0445\u0443\u0436\u0435 \u2014 \u0432\u044b\u043a\u043b\u044e\u0447\u0438."
        )
        self.games_filter_warn = warn
        warn.setObjectName("gamesFilterWarn")
        warn.setWordWrap(True)
        gl.addWidget(warn)
        return box

    def _apply_game_filter(self) -> None:
        """Enable/disable Flowseal's game filter via utils/game_filter.enabled."""
        try:
            flag = Path(self.zapret_dir) / "utils" / "game_filter.enabled"
            if bool(getattr(self.config, "game_filter_enabled", False)):
                flag.parent.mkdir(parents=True, exist_ok=True)
                flag.write_text("all\n", encoding="utf-8")
            elif flag.exists():
                flag.unlink()
        except Exception:
            pass

    def _toggle_game_filter(self, enabled: bool) -> None:
        self.config.game_filter_enabled = bool(enabled)
        self.config.save()
        self._apply_game_filter()
        # Re-expand strategy args with the new port range, then restart winws.
        self.reload_strategies()
        self._restart_engine_fresh()

    def _restart_engine_fresh(self) -> None:
        """Restart winws with freshly built args (game filter / Roblox combine)."""
        try:
            if self.runner.is_running():
                strat = self._current_strategy()
                if strat is not None:
                    self._user_stop = False
                    self.runner.start(strat)
                    self._refresh_status()
        except Exception:
            pass

    def _engine_args_filter(self, args):
        """Applied by ProcessRunner right before EVERY launch. When the Roblox
        checkbox is on, merge the Roblox bypass profile into the args so Roblox
        AND YouTube/Discord work together. Crucially this also runs during
        auto-select, so the strategy that ends up running really contains the
        Roblox UDP/ipset profile needed to join places.

        The profile is loaded from ``roblox_profile.json`` (so users can edit
        IP ranges without rebuilding the exe). Falls back to the hardcoded
        constant if the JSON is missing/unreadable.
        """
        try:
            if not getattr(self.config, "roblox_combine", False):
                return args
            from app import strategy_manager as _sm
            from app.bootstrap import load_roblox_profile
            roblox_args, _desc = load_roblox_profile()
            roblox = _sm._tokenize_args(roblox_args)
            return _sm.combine_with_roblox(list(args), roblox)
        except Exception:
            return args

    def _toggle_roblox_combine(self, enabled: bool) -> None:
        self.config.roblox_combine = bool(enabled)
        self.config.save()
        self._update_cmd_preview()
        self._restart_engine_fresh()
