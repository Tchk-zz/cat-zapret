"""Main application window: Home / Settings / Strategy (list + editor + logs)."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QThread, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal,
    QPoint, QSize,
)
from PyQt6.QtGui import (
    QColor, QIcon, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QDialog,
    QPlainTextEdit, QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app import autostart, bootstrap, editor as editor_mod, list_manager
from app.auto_selector import AutoSelectResult, AutoSelector
from app.config import AppConfig, default_data_dir
from app.process_runner import ProcessRunner
from app.service_manager import ServiceManager
from app.strategy_manager import Strategy, StrategyManager
from app import tg_proxy
from .paths import asset_path
from .tab_games import GamesTabMixin
from .tab_home import HomeTabMixin
from .tab_settings import SettingsTabMixin
from .tab_strategy import StrategyTabMixin
from .tab_telegram import TelegramTabMixin
from .theme import (
    DARK_QSS,
    WIN11_DARK_QSS,
    WIN11_LIGHT_QSS,
    GradientBackground,
    smooth_code_font,
)
from .tray import Tray
from .workers import (
    AutoSelectWorker,
    BootstrapWorker,
    CheckWorker,
    ListUpdateWorker,
    UpdateCheckWorker,
)


# Asset lookup lives in ui/paths.py so main_window, theme and tray all share
# one implementation. Re-exported here because existing code (and tests)
# import asset_path from this module.

# Translation tables live in ui/i18n.py; re-exported here because the
# window and the tests import these names from this module.
from .i18n import (  # noqa: E402
    _TRANSLATIONS,
    _TRANSLATIONS_REVERSE,
    localize_runtime_text,
    tr_text,
)


def app_icon_path() -> str:
    """Locate the bundled application icon (.ico preferred, .png fallback).

    Works both from source (ui/assets) and when frozen by PyInstaller
    (sys._MEIPASS/ui/assets).
    """
    names = ("app.ico", "app_icon.png")
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass) / "ui" / "assets")
        roots.append(Path(meipass) / "assets")
    here = Path(__file__).resolve().parent
    roots.append(here / "assets")
    for root in roots:
        for name in names:
            cand = root / name
            try:
                if cand.is_file():
                    return str(cand)
            except OSError:
                pass
    return ""


def app_icon() -> QIcon:
    path = app_icon_path()
    return QIcon(path) if path else QIcon()


# The monospace font helper now lives in ui/theme.py (alias kept so existing
# call sites in this module stay untouched).
_smooth_code_font = smooth_code_font


# Painted widgets and popups live in ui/widgets_custom.py.
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


class MainWindow(
    HomeTabMixin,
    TelegramTabMixin,
    GamesTabMixin,
    StrategyTabMixin,
    SettingsTabMixin,
    QMainWindow,
):
    # Signals let worker threads update the GUI safely (Qt requires widget
    # access from the GUI thread only).
    engine_log = pyqtSignal(str)
    engine_exited = pyqtSignal(int, str)
    tg_engine_exited = pyqtSignal(int)

    def __init__(self, config: AppConfig, start_minimized: bool = False):
        super().__init__()
        self.config = config
        self.zapret_dir = config.managed_zapret_dir()
        self.manager = StrategyManager(self.zapret_dir)
        self.service = ServiceManager(self.zapret_dir)
        self.runner = self._make_runner()
        # Telegram MTProto proxy runner. Lives next to the zapret runner so
        # both can be stopped together at quit.
        self._tg_data_dir = default_data_dir()
        self.tg_runner = tg_proxy.TGProxyRunner(
            self._tg_data_dir,
            log_cb=lambda m: self.engine_log.emit(m),
            on_exit=lambda code: self.tg_engine_exited.emit(code),
            dc_ips=list(getattr(config, "tg_proxy_dc_ips", []) or []),
            cfproxy_domains=list(getattr(config, "tg_proxy_cfproxy_domains", []) or []),
            cfworker_domains=list(getattr(config, "tg_proxy_cfworker_domains", []) or []),
        )
        self._auto_thread: Optional[QThread] = None
        self._auto_worker: Optional[AutoSelectWorker] = None
        self._update_thread: Optional[QThread] = None
        self._check_thread: Optional[QThread] = None
        self._bootstrap_thread: Optional[QThread] = None
        self._tg_update_thread: Optional[QThread] = None
        self._list_update_thread: Optional[QThread] = None
        self._tg_popup: Optional[StyledPopup] = None
        self._force_quit = False
        self._user_stop = False
        self._auto_popup = None
        self._auto_popup_closing = False
        # Guards _autostart_engine_if_configured against double-fire (both
        # _ensure_ready and _on_bootstrap_finished could call it on the same
        # launch if the bootstrap finishes very fast).
        self._autostart_done = False
        self._bootstrap_popup = None
        self._suppress_next_engine_exit_popup = False
        self.lang = getattr(config, "language", "ru") if getattr(config, "language", "ru") in ("ru", "en") else "ru"
        # Validate the saved theme against the full catalog (3 presets + 7
        # image themes). Previously this only accepted "purple"/"light"/"dark"
        # and silently reset any image theme (mist/azure/snow/...) to purple
        # on the next launch — a real user-visible regression.
        try:
            from .themes_catalog import theme_ids as _valid_theme_ids
            _valid = set(_valid_theme_ids())
        except Exception:
            _valid = {"purple", "dark", "light"}
        _saved_theme = getattr(config, "theme", "purple")
        self.current_theme = _saved_theme if _saved_theme in _valid else "purple"

        self.setWindowTitle("Zapret GUI")
        _icon = app_icon()
        if not _icon.isNull():
            self.setWindowIcon(_icon)
            QApplication.setWindowIcon(_icon)
        # Fixed, non-resizable window. Sized to fit every tab without scrolling.
        # The 1240x900 design canvas is right for 1440p; on smaller desktops the
        # whole UI is scaled down via QT_SCALE_FACTOR in main.py. This is the
        # last-resort clamp for cases where that isn't possible (odd DPI, a
        # secondary monitor, a taskbar on the side): shrink proportionally so
        # the window always fits inside the available work area.
        self._design_size = (1240, 900)
        self.setFixedSize(*self._fitted_window_size(1240, 900))
        self.setStyleSheet(WIN11_DARK_QSS if self.current_theme == "dark" else (WIN11_LIGHT_QSS if self.current_theme == "light" else DARK_QSS))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.tabBar().hide()  # replaced by a custom "liquid glass" segmented nav
        self._bg = GradientBackground()
        _bg_layout = QVBoxLayout(self._bg)
        _bg_layout.setContentsMargins(0, 16, 0, 0)
        _bg_layout.setSpacing(12)
        self._top_nav = _GlassNav([
            "Главная",
            "На��тройки",
            "Стратегия",
            "Игры и сервисы",
            "Telegram",
        ], on_select=self.tabs.setCurrentIndex)
        _bg_layout.addWidget(self._top_nav, 0, Qt.AlignmentFlag.AlignHCenter)
        _bg_layout.addWidget(self.tabs)
        self.setCentralWidget(self._bg)
        # The top nav is not scrollable, so the window must never get narrower
        # than the panel's natural width — otherwise the last tab ("\u0418\u0433\u0440\u044b \u0438
        # \u0441\u0435\u0440\u0432\u0438\u0441\u044b") gets clipped on the right edge.
        self._top_nav.ensurePolished()
        # Window is fixed-size (see setFixedSize above), so no minimum-width
        # enforcement is needed here; polishing alone keeps the metrics right.
        self.tabs.addTab(self._build_home_tab(), "\u0413\u043b\u0430\u0432\u043d\u0430\u044f")
        self.tabs.addTab(self._build_settings_tab(), "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438")
        # Strategy is tuned to fit the window exactly; do not wrap it in a page
        # scroll area so the page itself never scrolls.
        self.tabs.addTab(self._build_strategy_tab(), "\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f")
        # Games/Services is designed to fit the window exactly; no page scroll.
        self.tabs.addTab(self._build_games_tab(), "\u0418\u0433\u0440\u044b \u0438 \u0441\u0435\u0440\u0432\u0438\u0441\u044b")
        # Telegram proxy tab.
        self.tabs.addTab(self._build_tg_tab(), "Telegram")

        self.tabs.currentChanged.connect(self._top_nav.set_active)
        self.tabs.currentChanged.connect(self._fade_current_tab)
        self.tabs.currentChanged.connect(self._update_bg_mode)
        self._top_nav.set_active(self.tabs.currentIndex(), animate=False)
        self._update_bg_mode(self.tabs.currentIndex())

        # Wire thread-safe signals now that the widgets exist.
        self.engine_log.connect(self._append_log)
        self.engine_exited.connect(self._on_engine_exited)
        self.tg_engine_exited.connect(self._on_tg_engine_exited)

        self.tray = Tray(self)
        self.tray.show()

        self.reload_strategies()
        self._refresh_status()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(2000)
        self._apply_language()
        self._apply_theme()

        # Extract bundled zapret files on first run, then refresh the list.
        QTimer.singleShot(0, self._ensure_ready)
        # If the user previously enabled the Telegram proxy, kick off the
        # bootstrap+start sequence so it's running again by the time they
        # open Telegram Desktop.
        QTimer.singleShot(500, self._tg_restore_state)

        if config.check_updates_on_launch:
            QTimer.singleShot(3000, self.check_updates_async)
            # Also check the embedded tg-ws-proxy engine for upstream updates.
            # Runs slightly after the zapret check so they don't collide on
            # the GitHub API rate limit.
            QTimer.singleShot(5000, self._tg_check_updates_async)
        if start_minimized:
            QTimer.singleShot(0, self.hide)

    # ------------------------------------------------------------- runner
    def _make_runner(self) -> ProcessRunner:
        """Build a ProcessRunner whose callbacks marshal back to the GUI thread."""
        return ProcessRunner(
            self.manager.winws_path(),
            log_cb=lambda m: self.engine_log.emit(m),
            on_exit=lambda code, tail: self.engine_exited.emit(code, tail),
            args_filter=self._engine_args_filter,
        )

    def _apply_user_lists(self) -> None:
        """Write include/exclude user lists from the saved selections."""
        try:
            from app import exclusions

            exclusions.apply_lists(
                self.zapret_dir,
                include_presets=self.config.include_presets or [],
                include_custom=self.config.include_custom or [],
                exclude_presets=self.config.exclude_presets or [],
                exclude_custom=self.config.exclude_custom or [],
            )
        except Exception:
            pass

    def _restart_engine_if_running(self) -> None:
        """Reload winws so changed user lists take effect immediately."""
        try:
            if self.runner.is_running():
                strat = self.runner.current_strategy or self._current_strategy()
                if strat is not None:
                    self._user_stop = False
                    self.runner.start(strat)
                    self._refresh_status()
        except Exception:
            pass

    def _toggle_service(self, kind: str, sid: str, enabled: bool) -> None:
        if kind == "include" and sid == "roblox":
            # The Roblox entry under "\u041f\u0440\u0438\u043c\u0435\u043d\u044f\u0442\u044c \u043e\u0431\u0445\u043e\u0434" is special: instead of only
            # adding domains to a hostlist, it merges the full Roblox bypass
            # profile (game UDP servers + ipset) into whatever strategy is
            # selected -- exactly what is needed to join places.
            self._toggle_roblox_combine(enabled)
            return
        field_name = "include_presets" if kind == "include" else "exclude_presets"
        cur = list(getattr(self.config, field_name) or [])
        if enabled and sid not in cur:
            cur.append(sid)
        elif not enabled and sid in cur:
            cur.remove(sid)
        setattr(self.config, field_name, cur)
        self.config.save()
        self._apply_user_lists()
        self._restart_engine_if_running()

    def _set_custom_domains(self, kind: str, text: str) -> None:
        field_name = "include_custom" if kind == "include" else "exclude_custom"
        domains = [p for p in text.replace(",", " ").replace(";", " ").split() if p]
        setattr(self.config, field_name, domains)
        self.config.save()
        self._apply_user_lists()
        self._restart_engine_if_running()

    def _service_display_name(self, name: str) -> str:
        """Short labels for the compact Games/Services layout."""
        mapping = {
            "Valorant / Riot Games": "Riot Games",
            "Battle.net / Blizzard": "Battle.net/Blizzard",
        }
        return mapping.get(name, name)

    def _build_list_group(self, kind: str, title_text: str):
        from app import exclusions

        box = QFrame()
        box.setObjectName("gamesColumn")
        gl = QVBoxLayout(box)
        # Raise the column header (icon + title) by 2pt without changing the
        # element order or divider behavior.
        gl.setContentsMargins(0, -2, 0, 0)
        gl.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        icon = GamesColumnIcon(kind)
        title = QLabel(title_text)
        title.setObjectName("gamesColumnTitle")
        title_row.addWidget(icon)
        title_row.addWidget(title)
        title_row.addStretch(1)
        gl.addLayout(title_row)

        sel = set(
            (
                self.config.include_presets
                if kind == "include"
                else self.config.exclude_presets
            )
            or []
        )
        for svc in exclusions.SERVICES:
            cb = QCheckBox(self._service_display_name(svc.name))
            cb.setObjectName("gamesCheck")
            if kind == "include" and svc.id == "roblox":
                # Under "Применять обход", Roblox drives the full combine
                # toggle (UDP place-join + ipset), not just a domain hostlist.
                cb.setChecked(bool(getattr(self.config, "roblox_combine", False)))
                cb.setToolTip(
                    "Объединяет выбранную стратегию с обходом для Roblox "
                    "(игровые UDP-серверы 49152-65535 + ipset + домены) — "
                    "нужно для входа на плейсы. Работает с любой стратегией."
                )
            else:
                cb.setChecked(svc.id in sel)
                cb.setToolTip(svc.description)
            cb.toggled.connect(
                lambda checked, k=kind, sid=svc.id: self._toggle_service(k, sid, checked)
            )
            gl.addWidget(cb)

        gl.addSpacing(8)
        domain_block = QWidget()
        domain_block.setObjectName("gamesDomainBlock")
        domain_lay = QVBoxLayout(domain_block)
        domain_lay.setContentsMargins(0, 0, 0, 0)
        domain_lay.setSpacing(0)
        lbl = QLabel("Свои домены (через запятую)")
        lbl.setObjectName("gamesDomainLabel")
        lbl.setContentsMargins(10, 0, 0, 0)
        lbl.setFixedHeight(18)
        domain_lay.addWidget(lbl)
        edit = QLineEdit()
        edit.setObjectName("gamesInput")
        edit.setFixedHeight(32)
        custom = (
            self.config.include_custom
            if kind == "include"
            else self.config.exclude_custom
        ) or []
        edit.setText(", ".join(custom))
        edit.setPlaceholderText("example.com, site.org")
        edit.editingFinished.connect(
            lambda e=edit, k=kind: self._set_custom_domains(k, e.text())
        )
        domain_lay.addWidget(edit)
        gl.addWidget(domain_block)
        # Lower the bottom separator by 2pt while keeping the center divider
        # inside the gap between the domain inputs (not over the inputs).
        gl.addSpacing(2)
        return box

    # ------------------------------------------------------------- telegram
    def _ensure_ready(self) -> None:
        """Make sure zapret files exist; extract the bundled copy on first run."""
        try:
            if bootstrap.is_installed(self.zapret_dir):
                bootstrap.ensure_user_lists(self.zapret_dir)
                bootstrap.ensure_builtin_strategies(self.zapret_dir)
                self._apply_user_lists()
                self._apply_game_filter()
                self.reload_strategies()
                self._refresh_status()
                self._maybe_auto_update_lists()
                # Auto-start the bypass if the user enabled it. This fires
                # after the strategy list is loaded so start_engine() can
                # find the last working strategy in the combo box.
                self._autostart_engine_if_configured()
                return
        except Exception:
            pass
        self._start_bootstrap()

    def _autostart_engine_if_configured(self) -> None:
        """Auto-start the zapret bypass engine if the user enabled
        'Включать обход при запуске приложения' and a working strategy is
        pinned. Also auto-starts the TG proxy if 'Запускать вместе с zapret'
        is checked (handled inside start_engine → _tg_ensure_installed_then).

        This is called from _ensure_ready (when zapret is already installed)
        and from _on_bootstrap_finished (after first-run download completes).
        It only fires once per launch — the _autostart_done flag prevents
        duplicate starts if both code paths execute."""
        if getattr(self, "_autostart_done", False):
            return
        self._autostart_done = True
        if not getattr(self.config, "autostart_strategy", False):
            return
        key = getattr(self.config, "last_working_strategy", "")
        if not key:
            return
        # Make sure the strategy exists in the loaded list.
        strat = self.manager.get(key)
        if strat is None:
            self._log("[auto] last working strategy not found in catalog, skipping auto-start")
            return
        # Select it in the combo box so start_engine picks up the right one.
        idx = self.strategy_combo.findData(key)
        if idx >= 0:
            self.strategy_combo.setCurrentIndex(idx)
        self._log(f"[auto] auto-starting bypass: {strat.name}")
        try:
            self.start_engine()
        except Exception as exc:  # noqa: BLE001
            self._log(f"[auto] auto-start failed: {exc}")

    def _start_bootstrap(self) -> None:
        if self._bootstrap_thread is not None:
            return
        self.progress.setVisible(False)
        self.progress_label.setText("")
        self._set_busy(True)
        self._bootstrap_popup = StyledPopup(
            "Подготовка zapret",
            "Загружаем необходимые файлы...",
            self,
            ok_text="OK",
        )
        self._bootstrap_popup.show()
        worker = BootstrapWorker(self.zapret_dir)
        thread = QThread(self)
        self._bootstrap_worker = worker
        self._bootstrap_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_bootstrap_progress)
        worker.progress.connect(self._append_log)
        worker.finished.connect(self._on_bootstrap_finished)
        thread.start()

    def _on_bootstrap_progress(self, text: str) -> None:
        if self._bootstrap_popup is not None:
            self._bootstrap_popup.body.setText(self._localize_runtime(self._t(text)))

    def _on_bootstrap_finished(self, result: str) -> None:
        if self._bootstrap_thread is not None:
            self._bootstrap_thread.quit()
            self._bootstrap_thread.wait()
            self._bootstrap_thread = None
            self._bootstrap_worker = None
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        if self._bootstrap_popup is not None:
            self._bootstrap_popup.close()
            self._bootstrap_popup = None
        self._set_busy(False)
        # Re-point managers at the now-populated zapret dir.
        self.manager = StrategyManager(self.zapret_dir)
        self.service = ServiceManager(self.zapret_dir)
        self.runner = self._make_runner()
        if result == "ok":
            try:
                bootstrap.ensure_user_lists(self.zapret_dir)
                bootstrap.ensure_builtin_strategies(self.zapret_dir)
                self._apply_user_lists()
                self._apply_game_filter()
            except Exception:
                pass
            self.progress_label.setText(self._t("Файлы zapret готовы."))
            self.reload_strategies()
            self._maybe_auto_update_lists()
            # After first-run bootstrap completes, auto-start the bypass
            # if the user enabled it (same as _ensure_ready's fast path).
            self._autostart_engine_if_configured()
        else:
            self.progress_label.setText(self._msg_text("Не удалось подготовить zapret") + ": " + self._localize_runtime(result))
            StyledPopup(
                "Не удалось подг��товить zapret",
                "Проверьте интернет-соединение и попробуйте снова.\n\n" + result,
                self,
                error_style=True,
            ).exec()
        # Reflect the resolved dir in the settings field.
        try:
            self.dir_edit.setText(str(self.zapret_dir))
        except Exception:
            pass
        self._refresh_status()

    def _require_installed(self) -> bool:
        """Block engine start until zapret files are present; seed user lists."""
        try:
            if not bootstrap.is_installed(self.zapret_dir):
                StyledPopup(
                    "Подготовка zapret",
                    "Файлы zapret ещё не готовы. Идёт подготовка, попробуйте через несколько секунд.",
                    self,
                ).exec()
                self._ensure_ready()
                return False
            bootstrap.ensure_user_lists(self.zapret_dir)
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------ tab fade
    def _fade_current_tab(self, index: int) -> None:
        """Subtle iOS-style fade-in of the freshly selected section."""
        try:
            w = self.tabs.widget(index)
            if w is None:
                return
            eff = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: w.setGraphicsEffect(None))
            self._tab_fade_anim = anim
            anim.start()
        except Exception:
            pass

    def _t(self, text: str) -> str:
        return tr_text(self.lang, text)

    def _toggle_language(self) -> None:
        self.lang = "en" if self.lang == "ru" else "ru"
        self.config.language = self.lang
        self.config.save()
        self._apply_language()

    def _translate_widget_tree(self) -> None:
        for widget in self.findChildren((QLabel, QPushButton, QCheckBox, QGroupBox)):
            if widget is getattr(self, "btn_lang", None):
                continue
            try:
                widget.setText(self._t(widget.text()))
            except Exception:
                pass
            try:
                widget.setTitle(self._t(widget.title()))
            except Exception:
                pass
        for widget in self.findChildren(QLineEdit):
            try:
                widget.setPlaceholderText(self._t(widget.placeholderText()))
            except Exception:
                pass
        for tabs in self.findChildren(QTabWidget):
            for i in range(tabs.count()):
                tabs.setTabText(i, self._t(tabs.tabText(i)))

    def _apply_language(self) -> None:
        if hasattr(self, "btn_lang"):
            self.btn_lang.setText("EN" if self.lang == "ru" else "RU")
            self.btn_lang.setToolTip("Сменить язык" if self.lang == "ru" else "Switch language")
        if hasattr(self, "_top_nav"):
            games_nav = self._t("Игры и сервисы")
            if self.lang == "en":
                games_nav = "Games && Services"
            self._top_nav.set_labels([
                self._t("Главная"), self._t("Настройки"),
                self._t("Стратегия"), games_nav, self._t("Telegram"),
            ])
        self._translate_widget_tree()
        # Explicitly refresh text that can be long/wrapped or rebuilt dynamically.
        if hasattr(self, "games_title"):
            self.games_title.setText("Games & Services" if self.lang == "en" else "Игры и сервисы")
        if hasattr(self, "games_subtitle"):
            if self.lang == "en":
                self.games_subtitle.setText(
                    "Select a service that the bypass should NOT touch "
                    "(if a game/client breaks)\n"
                    "or, conversely, force the bypass to apply to it. "
                    "You can add custom domains."
                )
            else:
                self.games_subtitle.setText(
                    "Отметь сервис чтобы обход его НЕ трогал "
                    "(если игра/клиент игры ломается)\n"
                    "или, наоборот, применялся к нему. Можно добавить свои домены."
                )
        if hasattr(self, "games_note"):
            self.games_note.setText(self._t("Изменения сохраняются сразу. Если zapret включён — он перезапустится автоматически."))
        if hasattr(self, "cb_auto_lists"):
            self.cb_auto_lists.setText(self._t("Автоматически обновлять списки/IPset"))
        if hasattr(self, "btn_update_lists"):
            self.btn_update_lists.setText(self._t("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0441\u043f\u0438\u0441\u043a\u0438/IPset"))
        if hasattr(self, "btn_hosts_dialog"):
            self.btn_hosts_dialog.setText(self._t("HOSTS для Windows"))
        if hasattr(self, "games_filter_box"):
            self.games_filter_box.setTitle(self._t("Игровой фильтр (эксперимент)"))
        if hasattr(self, "games_filter_cb"):
            self.games_filter_cb.setText(self._t("Применять обход к игровому трафику (порты 1024-65535)"))
        if hasattr(self, "games_filter_warn"):
            self.games_filter_warn.setText(self._t("Применяет DPI-обход к игровому UDP/TCP на высоких портах. Иногда помогает (если сервис режется по DPI), но ЧАЩЕ ломает игры — в РФ они ��бычно не блокируются по DPI. Включай для теста; стало хуже — выключи."))
        # Telegram tab dynamic text.
        if hasattr(self, "tg_title"):
            self.tg_title.setText(self._t("Telegram прокси"))
        if hasattr(self, "tg_subtitle"):
            self.tg_subtitle.setText(self._t(
                "Локальный MTProto-прокси для Telegram Desktop. Telegram подключается к нему, "
                "а прокси туннелирует трафик через WebSocket к серверам Telegram — обход бло��ировок "
                "без сторонних серверов."
            ))
        if hasattr(self, "cb_tg_autostart"):
            self.cb_tg_autostart.setText(self._t("Запускать в��есте с zapret"))
        if hasattr(self, "btn_tg_copy"):
            self.btn_tg_copy.setText(self._t("��копиров��ть ссылку"))
        if hasattr(self, "btn_tg_open"):
            self.btn_tg_open.setText(self._t("��ткрыть в Telegram"))
        if hasattr(self, "btn_tg_rotate"):
            self.btn_tg_rotate.setText(self._t("Сгенерировать новый secret"))
        if hasattr(self, "btn_tg_update"):
            self.btn_tg_update.setText(self._t("Проверить обновления tg-ws-proxy"))
        try:
            tab_titles = ["Главная", "Настройки", "Стратегия", "Игры и сервисы", "Telegram"]
            for i, txt in enumerate(tab_titles):
                label = self._t(txt)
                if self.lang == "en" and txt == "Игры и серви��ы":
                    label = "Games && Services"
                self.tabs.setTabText(i, label)
        except Exception:
            pass
        if hasattr(self, "tray"):
            try:
                self.tray.set_language(self.lang)
            except Exception:
                pass
        if hasattr(self, "status_label"):
            self._refresh_status()
        if hasattr(self, "tg_status_label"):
            self._tg_refresh_status()

    def _update_bg_mode(self, index: int) -> None:
        """Tell the background widget which mode to use for the current tab.

        Image themes use the same background on every tab, so home/settings
        mode is irrelevant — set_theme_image() already takes priority in the
        painter. We still set dark/light mode flags so a switch back to a
        preset theme renders correctly.
        """
        from .themes_catalog import is_image_theme
        cur = getattr(self, "current_theme", "purple")
        is_dark = cur == "dark"
        is_light = cur == "light"
        is_image = is_image_theme(cur)
        self._bg.set_dark_mode(is_dark)
        self._bg.set_light_mode(is_light)
        if index == 0 and hasattr(self, "home_tg_srv"):
            self._refresh_home_cards()
        # Home/settings modes are only relevant for the procedural purple
        # theme. Image themes ignore them (set_theme_image takes priority),
        # and dark/light themes ignore them too.
        if is_image or is_dark or is_light:
            self._bg.set_home_mode(False)
            self._bg.set_settings_mode(False)
        else:
            self._bg.set_home_mode(index == 0)
            # Settings-mode background applies to all "card-style" tabs.
            self._bg.set_settings_mode(index in (1, 2, 3, 4))

    # ------------------------------------------------------------------ tabs
    def _fitted_window_size(self, width: int, height: int) -> tuple:
        """Shrink the design size proportionally so it fits the current screen.

        Keeps the 1240x900 aspect ratio (all inner layouts are tuned for it)
        and never returns a size larger than the design one.
        """
        try:
            screen = self.screen() or QApplication.primaryScreen()
            if screen is None:
                return (width, height)
            avail = screen.availableGeometry()
            # Leave room for the title bar and a little breathing space.
            max_w = max(avail.width() - 40, 320)
            max_h = max(avail.height() - 70, 240)
            factor = min(1.0, max_w / float(width), max_h / float(height))
            if factor >= 0.999:
                return (width, height)
            return (int(width * factor), int(height * factor))
        except Exception:
            return (width, height)

    def _build_logs_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("strategyPage")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(34, 26, 34, 28)
        lay.setSpacing(14)
        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setFont(_smooth_code_font(12))
        self.log_view.setReadOnly(True)
        lay.addWidget(self.log_view, 1)
        row = QHBoxLayout()
        btn_copy = QPushButton("\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c")
        btn_copy.setObjectName("strategySoftBtn")
        btn_copy.clicked.connect(self._copy_logs)
        btn_clear = QPushButton("\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c")
        btn_clear.setObjectName("strategySoftBtn")
        btn_clear.clicked.connect(lambda: self.log_view.clear())
        row.addStretch(1)
        row.addWidget(btn_copy)
        row.addWidget(btn_clear)
        lay.addLayout(row)
        return w

    # --------------------------------------------------------------- helpers
    def _append_log(self, msg: str) -> None:
        msg = self._localize_runtime(msg)
        self.log_view.append(msg)
        if hasattr(self, "home_log"):
            self.home_log.append(msg)

    def _log(self, msg: str) -> None:
        # Safe to call from any thread \u2014 routed through a queued signal.
        self.engine_log.emit(msg)

    def _copy_logs(self) -> None:
        QApplication.clipboard().setText(self.log_view.toPlainText())

    def _localize_runtime(self, text: str) -> str:
        return localize_runtime_text(self.lang, text)

    def _set_progress_label(self, text: str) -> None:
        self.progress_label.setText(self._localize_runtime(text))

    def _msg_title(self, text: str) -> str:
        return self._t(text)

    def _msg_text(self, text: str) -> str:
        return self._localize_runtime(self._t(text))

    def _set_busy(self, busy: bool) -> None:
        for b in (
            getattr(self, "btn_toggle", None),
            getattr(self, "btn_check", None),
            getattr(self, "btn_run_list", None),
            getattr(self, "btn_reload", None),
            getattr(self, "btn_update_lists", None),
            getattr(self, "btn_hosts_dialog", None),
        ):
            if b is not None:
                b.setEnabled(not busy)

    def reload_strategies(self, rebuild: bool = False) -> None:
        # The "Refresh list" button rebuilds our JSON catalog from the Flowseal
        # .bat files; normal reloads just read the existing catalog.
        self.manager.reload(force_rebuild=rebuild)
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        self.strategy_list.clear()
        for s in self.manager.strategies:
            label = ("\u2605 " if s.custom else "") + s.name
            self.strategy_combo.addItem(label, s.key)
            self.strategy_list.addItem(label)
        if self.config.last_working_strategy:
            idx = self.strategy_combo.findData(self.config.last_working_strategy)
            if idx >= 0:
                self.strategy_combo.setCurrentIndex(idx)
        self.strategy_combo.blockSignals(False)
        self._update_cmd_preview()
        self._reload_domain_files()

    def _current_strategy(self) -> Optional[Strategy]:
        key = self.strategy_combo.currentData()
        return self.manager.get(key) if key else None

    def _update_cmd_preview(self) -> None:
        s = self._current_strategy()
        if s is None:
            self.cmd_preview.setPlainText("")
        else:
            args = self._engine_args_filter(list(s.args))
            self.cmd_preview.setPlainText("winws.exe " + " ".join(args))

    def _on_strategy_selected(self, row: int) -> None:
        if 0 <= row < len(self.manager.strategies):
            s = self.manager.strategies[row]
            self.strategy_detail.setPlainText(
                f"{s.name}\n\n{s.description}\n\n" + " ".join(s.args)
            )

    def _run_selected_from_list(self) -> None:
        row = self.strategy_list.currentRow()
        if 0 <= row < len(self.manager.strategies):
            self.strategy_combo.setCurrentIndex(row)
            self.start_engine()
            self.tabs.setCurrentIndex(0)

    # ----------------------------------------------------------- engine ctrl
    def power_toggle(self) -> None:
        """Central power button.

        Stop if running. Otherwise, if a strategy has already been pinned (e.g.
        by a previous auto-select), launch it directly. Only fall back to a
        fresh auto-select when nothing is pinned yet.
        """
        if self.runner.is_running():
            self.stop_engine()
            return
        key = self.config.last_working_strategy
        strat = self.manager.get(key) if key else None
        if strat is not None:
            idx = self.strategy_combo.findData(key)
            if idx >= 0:
                self.strategy_combo.setCurrentIndex(idx)
            self.start_engine()
        else:
            self.start_auto_select("working")

    def toggle_engine(self) -> None:
        if self.runner.is_running():
            self.stop_engine()
        else:
            self.start_engine()

    def _warn_service_conflict(self) -> bool:
        """If the zapret service is running it holds WinDivert and a manual
        winws.exe will instantly exit. Offer to stop the service first.

        Returns True if the caller may proceed (service not running, or user
        agreed to stop it, or stop succeeded). Returns False if the user
        declined to stop the service — in that case the caller MUST abort,
        otherwise its winws.exe will collide with the service and die."""
        try:
            if not self.service.is_running():
                return True
        except Exception:
            return True
        ans = QMessageBox.question(
            self, self._msg_title("Служба zapret"),
            "\u0421\u043b\u0443\u0436\u0431\u0430 zapret \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u0430 \u0438 \u0443\u0436\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442 WinDivert. "
            "\u0420\u0443\u0447\u043d\u043e\u0439 \u0437\u0430\u043f\u0443\u0441\u043a \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0438 \u0431\u0443\u0434\u0435\u0442 \u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442\u043e\u0432\u0430\u0442\u044c, \u0438 winws.exe \u0441\u0440\u0430\u0437\u0443 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u0441\u044f.\n\n"
            "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0441\u043b\u0443\u0436\u0431\u0443 \u0441\u0435\u0439\u0447\u0430\u0441?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            # User declined to stop the service. Launching winws now would
            # instantly fail with a WinDivert conflict, so abort.
            return False
        msg = self.service.stop()
        self._log("[\u0441\u043b\u0443\u0436\u0431\u0430] " + msg)
        # Give WinDivert a moment to release the filter before we re-grab it.
        QTimer.singleShot(500, lambda: None)
        return True

    def start_engine(self) -> None:
        strat = self._current_strategy()
        if strat is None:
            StyledPopup(
                "Ошибк�� запуска",
                "Нет выбранной стратегии.",
                self,
                error_style=True,
            ).exec()
            return
        if not self._require_installed():
            return
        # Abort if the user declined to stop a conflicting service — otherwise
        # winws would crash instantly with a WinDivert conflict.
        if not self._warn_service_conflict():
            return
        self._user_stop = False
        self._suppress_next_engine_exit_popup = False
        try:
            self.runner.start(strat)
            self.config.last_working_strategy = strat.key
            self.config.save()
        except Exception as exc:  # noqa: BLE001
            StyledPopup(
                "Ошибка запуска",
                "Не удалось запустить zapret.\n\n" + str(exc),
                self,
                error_style=True,
            ).exec()
        # Auto-start the Telegram proxy if the user asked for it.
        if getattr(self.config, "tg_proxy_autostart_with_zapret", False) and not self.tg_runner.is_running():
            self._tg_ensure_installed_then(start_after=True)
        self._refresh_status()

    def stop_engine(self) -> None:
        self._user_stop = True
        self.runner.stop()
        self._refresh_status()

    def _clear_suppress_exit_flag(self) -> None:
        """Auto-reset the suppression flag so a later genuine crash is reported."""
        self._suppress_next_engine_exit_popup = False

    def _on_engine_exited(self, code: int, tail: str) -> None:
        """winws.exe stopped on its own (crash / conflict / bad args)."""
        self._refresh_status()
        # During auto-select this is expected churn — the worker handles it.
        if self._auto_thread is not None or self._user_stop:
            return
        if self._suppress_next_engine_exit_popup:
            self._suppress_next_engine_exit_popup = False
            self._log("[winws] позднее завершение после автоподбора скрыто")
            return
        hints = (
            "\u0412\u043e\u0437\u043c\u043e\u0436\u043d\u044b\u0435 \u043f\u0440\u0438\u0447\u0438\u043d\u044b:\n"
            "\u2022 \u041f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0430 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u0430 \u0431\u0435\u0437 \u043f\u0440\u0430\u0432 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430 (WinDivert \u0438\u0445 \u0442\u0440\u0435\u0431\u0443\u0435\u0442).\n"
            "\u2022 \u0423\u0436\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0441\u043b\u0443\u0436\u0431\u0430 zapret \u0438\u043b\u0438 \u0434\u0440\u0443\u0433\u043e\u0439 winws.exe (\u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442 WinDivert).\n"
            "\u2022 \u0417\u0430\u043f\u0443\u0449\u0435\u043d \u0434\u0440\u0443\u0433\u043e\u0439 DPI-\u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 (GoodbyeDPI, \u0434\u0440\u0443\u0433\u043e\u0439 zapret).\n"
            "\u2022 \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0435 \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442\u044b \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0438."
        )
        body = (
            f"\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u043b\u0430\u0441\u044c, \u043d\u043e winws.exe \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0441\u044f \u0441\u0430\u043c (\u043a\u043e\u0434 {code}).\n\n"
            + hints
        )
        if tail:
            body += "\n\n\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0432\u044b\u0432\u043e\u0434 winws.exe:\n" + tail[-1200:]
        StyledPopup(
            "winws.exe остановился",
            body,
            self,
            error_style=True,
        ).exec()

    def manual_check(self) -> None:
        if self._check_thread is not None:
            return
        self.btn_check.setEnabled(False)
        if getattr(self, "_action_deco_active", False) and hasattr(self, "btn_check_deco_title"):
            self.btn_check_deco_title.setText(self._t("Проверка..."))
        else:
            self.btn_check.setText(self._t("Проверка..."))
        self._log("[\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430] \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u0430...")
        worker = CheckWorker(self.config.connectivity_timeout)
        thread = QThread(self)
        self._check_worker = worker
        self._check_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_check_finished)
        thread.start()

    def _on_check_finished(self, res) -> None:
        if self._check_thread is not None:
            self._check_thread.quit()
            self._check_thread.wait()
            self._check_thread = None
            self._check_worker = None
        self.btn_check.setEnabled(True)
        if getattr(self, "_action_deco_active", False) and hasattr(self, "btn_check_deco_title"):
            self.btn_check_deco_title.setText(self._t("Тест обхода"))
        else:
            self.btn_check.setText(self._t("Тест обхода"))
        self._log("[\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430] " + res.detail)
        BypassTestPopup(res, self).exec()

    # --------------------------------------------------------- auto selection
    def _set_dark_auto_panel_active(self, active: bool) -> None:
        """Replace dark Home cards/actions and switch the cat emotion once."""
        is_dark = getattr(self, "current_theme", "purple") == "dark"
        show_panel = bool(active) and is_dark
        if hasattr(self, "home_auto_stack"):
            self.home_auto_stack.setVisible(show_panel)
            if show_panel:
                self.home_auto_stack.raise_()
        if hasattr(self, "home_auto_panel"):
            self.home_auto_panel.setVisible(show_panel)
        if hasattr(self, "home_runner_card"):
            self.home_runner_card.setVisible(show_panel)
        if hasattr(self, "waiting_runner_game"):
            self.waiting_runner_game.set_searching(show_panel)
        if hasattr(self, "home_right_top_spacer"):
            self.home_right_top_spacer.setFixedHeight(100)
        if is_dark:
            for card in (getattr(self, "home_tg_card", None), getattr(self, "home_zap_card", None)):
                if card is not None:
                    card.setVisible(not show_panel)
            for button in (getattr(self, "btn_auto", None), getattr(self, "btn_check", None)):
                if button is not None:
                    button.setVisible(not show_panel)

        was_active = bool(getattr(self, "_home_cat_auto_active", False))
        if show_panel != was_active and hasattr(self, "home_cat"):
            if show_panel:
                search_pixmap = getattr(self, "_home_cat_search_pixmap", QPixmap())
                if not search_pixmap.isNull():
                    self.home_cat.setPixmap(search_pixmap)
                if hasattr(self, "sleep_z"):
                    self.sleep_z.set_sleeping(False)
            else:
                running = bool(self.runner.is_running()) if hasattr(self, "runner") else False
                normal_pixmap = (
                    getattr(self, "_home_cat_open_pixmap", QPixmap())
                    if running
                    else getattr(self, "_home_cat_closed_pixmap", QPixmap())
                )
                if not normal_pixmap.isNull():
                    self.home_cat.setPixmap(normal_pixmap)
                if hasattr(self, "sleep_z"):
                    self.sleep_z.set_sleeping(is_dark and not running)
            self._home_cat_auto_active = show_panel
        elif show_panel and hasattr(self, "sleep_z"):
            self.sleep_z.set_sleeping(False)

    def _on_waiting_runner_round_ended(self) -> None:
        result = getattr(self, "_pending_auto_result", None)
        if result is None:
            return
        self._pending_auto_result = None
        # Keep the game-over frame visible briefly, then show the search result.
        QTimer.singleShot(400, lambda result=result: self._on_auto_finished(result))

    def _set_auto_buttons(self, state: str) -> None:
        """state: 'idle' | 'choices' | 'running'."""
        self.btn_auto.setVisible(state != "running")
        self.btn_check.setVisible(state != "running")
        self.btn_auto_best.setVisible(state == "choices")
        self.btn_auto_work.setVisible(state == "choices")
        self.btn_auto_cancel.setVisible(False)

    def start_auto_select(self, mode: str = "working") -> None:
        if self._auto_thread is not None:
            return
        if not self._require_installed():
            self._set_auto_buttons("idle")
            return
        strategies = self.manager.ordered_for_autoselect(self.config.preferred_order)
        if not strategies:
            StyledPopup(
                "Стратегии не найдены",
                "Не удалось найти доступные стратегии для автоподбора.",
                self,
                error_style=True,
            ).exec()
            self._set_auto_buttons("idle")
            return
        if not self._warn_service_conflict():
            self._set_auto_buttons("idle")
            return
        self._user_stop = False
        self._pending_auto_result = None
        selector = AutoSelector(
            self.runner,
            warmup_seconds=self.config.warmup_seconds,
            timeout=self.config.connectivity_timeout,
            freeze_seconds=self.config.deep_freeze_seconds,
            working_freeze_seconds=self.config.working_freeze_seconds,
            attempts=self.config.deep_attempts,
            enable_voice=self.config.enable_voice_check,
            stall_timeout=self.config.stall_timeout,
        )
        # Hints so the sweep starts with the strategy that already worked on
        # this machine, followed by the user's preferred order. Cuts a full
        # sweep down to a couple of checks in the common case.
        self._auto_worker = AutoSelectWorker(
            selector,
            strategies,
            mode,
            last_working=self.config.last_working_strategy or None,
            preferred_order=list(self.config.preferred_order or []),
        )
        self._auto_thread = QThread(self)
        self._auto_worker.moveToThread(self._auto_thread)
        self._auto_thread.started.connect(self._auto_worker.run)
        self._auto_worker.progress.connect(self._on_auto_progress)
        self._auto_worker.log.connect(self._append_log)
        self._auto_worker.finished.connect(self._on_auto_finished)
        self.progress.setVisible(False)
        self.progress_label.setText("")
        self._set_busy(True)
        self._set_auto_buttons("running")
        self._auto_popup_closing = False
        if getattr(self, "current_theme", "purple") == "dark" and hasattr(self, "home_auto_panel"):
            self._auto_popup = None
            self.home_auto_panel.reset(len(strategies))
            self._set_dark_auto_panel_active(True)
        else:
            self._auto_popup = AutoSelectProgressPopup(self, total=len(strategies))
            self._auto_popup.accepted.connect(self._cancel_auto_select)
            self._auto_popup.rejected.connect(self._cancel_auto_select)
            self._auto_popup.show()
        self._auto_thread.start()

    def _cancel_auto_select(self) -> None:
        if self._auto_popup_closing:
            return
        if self._auto_worker is not None:
            self._auto_worker.cancel()
        if self._auto_popup is not None:
            self._auto_popup.set_message("Отмена...")
        if hasattr(self, "home_auto_panel") and self.home_auto_panel.isVisible():
            self.home_auto_panel.set_message("Отмена...")
        self.progress_label.setText("")

    def _on_auto_progress(self, idx: int, total: int, name: str, phase: str) -> None:
        if self._auto_popup is not None:
            self._auto_popup.update_progress(idx, total, name, phase)
        if hasattr(self, "home_auto_panel") and self.home_auto_panel.isVisible():
            self.home_auto_panel.update_progress(idx, total, name, phase)
        self.progress_label.setText("")
        self.tray.set_state("working", "подбор...")

    def _on_auto_finished(self, result: AutoSelectResult) -> None:
        if self._auto_thread is not None:
            self._auto_thread.quit()
            self._auto_thread.wait()
            self._auto_thread = None
            self._auto_worker = None
            self._set_busy(False)
            should_defer = bool(
                not result.cancelled
                and getattr(self, "current_theme", "purple") == "dark"
                and hasattr(self, "waiting_runner_game")
                and self.waiting_runner_game.is_user_playing()
            )
            if should_defer:
                self._pending_auto_result = result
                if hasattr(self, "home_auto_panel"):
                    self.home_auto_panel.set_message("Поиск завершён — доиграйте...")
                return
        self._pending_auto_result = None
        self._set_auto_buttons("idle")
        self._set_dark_auto_panel_active(False)
        self.progress.setVisible(False)
        if self._auto_popup is not None:
            self._auto_popup_closing = True
            self._auto_popup.close()
            self._auto_popup = None
            self._auto_popup_closing = False
        if result.cancelled:
            self.progress_label.setText(self._t("Подбор отменён."))
            self._refresh_status()
            return
        if result.strategy is not None:
            # Auto-select intentionally starts/stops winws while testing. Some
            # builds print a late exit after the best strategy has already been
            # accepted; do not show that as an error popup to the user. The flag
            # auto-clears after 8s so a real later crash is still reported.
            self._suppress_next_engine_exit_popup = True
            QTimer.singleShot(8000, self._clear_suppress_exit_flag)
            self.config.last_working_strategy = result.strategy.key
            self.config.save()
            idx = self.strategy_combo.findData(result.strategy.key)
            if idx >= 0:
                self.strategy_combo.setCurrentIndex(idx)
            lat = ""
            if result.latency_ms is not None:
                lat = f", \u043e\u0442\u043a\u043b\u0438\u043a ~{result.latency_ms:.0f} \u043c\u0441"
            if result.partial:
                self.progress_label.setText(self._localize_runtime(
                    f"Частично рабочая: {result.strategy.name} ({result.detail})"
                ))
                StyledPopup(
                    "Стратегия найд��на",
                    f"Полностью рабочая стратегия не найдена.\nВключена наиболее подходящая: {result.strategy.name}\n({result.detail}){lat}",
                    self,
                ).exec()
            else:
                kind = ("Best" if result.mode == "best" else "Working") if self.lang == "en" else ("Лучшая" if result.mode == "best" else "Рабо��ая")
                self.progress_label.setText(self._localize_runtime(
                    f"{kind} стратегия: {result.strategy.name} ({result.detail}){lat}"
                ))
                StyledPopup(
                    "Стратегия найдена",
                    f"{kind} стратегия включена: {result.strategy.name}\n({result.detail}){lat}",
                    self,
                ).exec()
        else:
            self.progress_label.setText(self._t("Рабочая стратегия не найдена."))
            StyledPopup(
                "Стратегия не найдена",
                "Ни одн�� стратегия не разблокировала доступ.\nПопробуйте обновить списки доменов и убедитесь, что приложение запущено от имени администратора.",
                self,
            ).exec()
        self._refresh_status()

    # ------------------------------------------------------------- updates
    def check_updates_async(self) -> None:
        if self._update_thread is not None:
            return
        worker = UpdateCheckWorker(self.zapret_dir)
        self._update_thread = QThread(self)
        self._update_worker = worker
        worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(worker.run)
        worker.finished.connect(self._on_update_checked)
        self._update_thread.start()

    def _on_update_checked(self, rel) -> None:
        self._update_thread.quit()
        self._update_thread.wait()
        self._update_thread = None
        if rel is None:
            self._log("[обновление] у вас последняя версия.")
            return
        ans = QMessageBox.question(
            self, self._msg_title("Обновление"),
            self._msg_text(f"Доступна новая версия {rel.tag}. Скачать и обновить стратегии?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            # Download + apply on a worker thread (the same path as the manual
            # "Обновить zapret" button). Doing it synchronously here froze the
            # whole UI for the duration of the download.
            self._apply_update_async(rel)

    def force_update_zapret(self) -> None:
        """Download the latest zapret release and rebuild the catalog from it."""
        self._apply_update_async(None)

    def _apply_update_async(self, release=None) -> None:
        """Run UpdateApplyWorker off the UI thread for *release* (or latest).

        Full zapret update can replace winws.exe and strategy/list files. If
        winws is running, stop it first so Windows/AV won't keep files locked;
        after a successful update restart the same strategy automatically.
        """
        if self._update_thread is not None:
            return
        self._update_restart_strategy = None
        self._update_restart_service = False
        try:
            if self.runner.is_running():
                self._update_restart_strategy = self._current_strategy()
                self.runner.stop()
                # ProcessRunner.stop() already waits up to 5s for winws.exe.
                self._refresh_status()
        except Exception:
            self._update_restart_strategy = None
        try:
            if self.service.is_running():
                self._update_restart_service = True
                svc_msg = self.service.stop()
                self._log("[служба] остановлена перед обновлением: " + svc_msg.strip())
        except Exception:
            self._update_restart_service = False
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate
        self.progress_label.setText(self._t("Обнов��ение zapret..."))
        self._set_busy(True)
        from .workers import UpdateApplyWorker
        worker = UpdateApplyWorker(self.zapret_dir, release)
        self._update_thread = QThread(self)
        self._update_worker = worker
        worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(worker.run)
        worker.progress.connect(self._set_progress_label)
        worker.progress.connect(self._append_log)
        worker.finished.connect(self._on_force_update_finished)
        self._update_thread.start()

    def _on_force_update_finished(self, msg: str) -> None:
        if self._update_thread is not None:
            self._update_thread.quit()
            self._update_thread.wait()
            self._update_thread = None
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self._set_busy(False)
        self._log("[о��новление] " + msg)
        self.reload_strategies()
        # Restart the previously running strategy only after a clearly
        # successful update. Error messages intentionally start with "Ошибка" /
        # "Не удалось" / warnings and will not restart stale binaries.
        restart = getattr(self, "_update_restart_strategy", None)
        if restart is not None and msg.startswith("Обновлено до"):
            try:
                fresh = self.manager.get(restart.key) or restart
                self.runner.start(fresh)
                self._refresh_status()
                self._log("[обн��вление] zapret перезапущен после обновления")
            except Exception as exc:  # noqa: BLE001
                self._log("[обновлени��] ����е удалось перезапу��тить zapret: " + str(exc))
        if getattr(self, "_update_restart_service", False) and msg.startswith("Обновлено до"):
            try:
                svc_msg = self.service.start()
                self._log("[служба] запущена после обновления: " + svc_msg.strip())
            except Exception as exc:  # noqa: BLE001
                self._log("[служба] не удалось запустить после обновления: " + str(exc))
        self._update_restart_strategy = None
        self._update_restart_service = False
        if (
            msg.startswith("Обновление выполнено частично")
            or msg.startswith("Обновление подготовлено")
            or msg.startswith("Ошибка")
            or msg.startswith("Не удалось")
        ):
            QMessageBox.warning(self, self._msg_title("Обновление"), self._msg_text(msg))
        else:
            QMessageBox.information(self, self._msg_title("Обновление"), self._msg_text(msg))

    # ------------------------------------------------------------- editor
    def _validate_custom(self) -> None:
        res = editor_mod.validate_args(self.edit_args.toPlainText())
        QMessageBox.information(
            self,
            self._msg_title("Проверка"),
            self._msg_text("\n".join(res.messages)),
        )

    def _save_custom(self) -> None:
        name = self.edit_name.text().strip()
        args = self.edit_args.toPlainText().strip()
        if not name or not args:
            QMessageBox.warning(self, "Zapret", self._msg_text("Укажите название и аргументы."))
            return
        self.manager.save_custom(name, args)
        self.reload_strategies()
        QMessageBox.information(self, "Zapret", self._msg_text("Стратегия сохранена."))

    def _delete_custom(self) -> None:
        name = self.edit_name.text().strip()
        if not name:
            return
        # Remember the current selection so we can restore it after the list is
        # rebuilt — otherwise the combo silently falls back to index 0 and a
        # later "Run selected" would launch the wrong strategy.
        prev_key = self.strategy_combo.currentData()
        if not self.manager.delete_custom(name):
            QMessageBox.warning(self, "Zapret", self._msg_text("Нет такой пользовательской стратегии."))
            return
        self.reload_strategies()
        # Restore the previous selection if it still exists; otherwise fall
        # back to the last working strategy (or the first one).
        new_idx = self.strategy_combo.findData(prev_key) if prev_key else -1
        if new_idx < 0:
            new_idx = self.strategy_combo.findData(self.config.last_working_strategy)
        if new_idx < 0 and self.strategy_combo.count() > 0:
            new_idx = 0
        if new_idx >= 0:
            self.strategy_combo.setCurrentIndex(new_idx)
        QMessageBox.information(self, "Zapret", self._msg_text("Удалено."))

    def _reload_domain_files(self) -> None:
        self.domain_combo.blockSignals(True)
        self.domain_combo.clear()
        for p in editor_mod.list_domain_files(self.zapret_dir):
            self.domain_combo.addItem(p.name, str(p))
        self.domain_combo.blockSignals(False)
        self._load_domain_file()

    def _load_domain_file(self) -> None:
        path = self.domain_combo.currentData()
        if not path:
            self.domain_text.setPlainText("")
            return
        try:
            self.domain_text.setPlainText(Path(path).read_text(encoding="utf-8", errors="ignore"))
        except OSError as exc:
            self.domain_text.setPlainText(self._localize_runtime(f"# ошибка: {exc}"))

    def _save_domain_file(self) -> None:
        path = self.domain_combo.currentData()
        if not path:
            return
        try:
            Path(path).write_text(self.domain_text.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Zapret", self._msg_text("Список сохранён."))
        except OSError as exc:
            QMessageBox.critical(self, "Zapret", self._msg_text(str(exc)))

    # ------------------------------------------------------------- settings
    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "\u041f\u0430\u043f\u043a\u0430 zapret", str(self.zapret_dir))
        if d:
            self.dir_edit.setText(d)
            self.config.zapret_dir = d
            self.config.save()
            self.zapret_dir = Path(d)
            self.manager = StrategyManager(self.zapret_dir)
            self.service = ServiceManager(self.zapret_dir)
            self.runner = self._make_runner()
            self._ensure_ready()
            self.reload_strategies()
            self._refresh_status()

    def _toggle_autostart(self, on: bool) -> None:
        if on:
            autostart.enable(self.config.start_minimized)
        else:
            autostart.disable()

    def _toggle_autostart_strategy(self, on: bool) -> None:
        """Toggle 'auto-start the bypass when the app launches'.

        When enabled, the app will automatically start the last working
        strategy on launch (including Windows autostart). If the Telegram
        proxy 'start with zapret' checkbox is also checked, the TG proxy
        starts too — no separate action needed."""
        self.config.autostart_strategy = bool(on)
        self.config.save()

    def _toggle_minimized(self, on: bool) -> None:
        self.config.start_minimized = on
        self.config.save()
        if self.cb_autostart.isChecked():
            autostart.enable(on)

    def _toggle_tray(self, on: bool) -> None:
        self.config.minimize_to_tray = on
        self.config.save()

    def _toggle_updates(self, on: bool) -> None:
        self.config.check_updates_on_launch = on
        self.config.save()

    def _toggle_auto_update_lists(self, on: bool) -> None:
        self.config.auto_update_lists = bool(on)
        self.config.save()

    def _maybe_auto_update_lists(self) -> None:
        try:
            if not getattr(self.config, "auto_update_lists", True):
                return
            interval = int(getattr(self.config, "list_update_interval_hours", 24) or 24)
            last = int(getattr(self.config, "last_lists_update", 0) or 0)
            if list_manager.should_auto_update_lists(last, interval):
                # Delay a little so first-run UI/auto-start is not blocked by GitHub.
                QTimer.singleShot(6500, lambda: self._start_list_update(manual=False))
        except Exception:
            pass

    def force_update_lists(self) -> None:
        self._start_list_update(manual=True)

    def _start_list_update(self, manual: bool = False) -> None:
        if self._list_update_thread is not None:
            return
        if not self._require_installed():
            return
        if manual:
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
            self.progress_label.setText(self._t("Обновление zapret..."))
            self._set_busy(True)
        worker = ListUpdateWorker(self.zapret_dir)
        thread = QThread(self)
        self._list_update_thread = thread
        self._list_update_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._append_log)
        worker.finished.connect(lambda res, m=manual: self._on_lists_update_finished(res, m))
        thread.start()

    def _on_lists_update_finished(self, res, manual: bool) -> None:
        if self._list_update_thread is not None:
            self._list_update_thread.quit()
            self._list_update_thread.wait()
            self._list_update_thread = None
            self._list_update_worker = None
        if manual:
            self.progress.setRange(0, 100)
            self.progress.setVisible(False)
            self._set_busy(False)
        msg = getattr(res, "message", str(res))
        ok = bool(getattr(res, "ok", False))
        self._log("[lists] " + msg)
        changed = int(getattr(res, "updated", 0) or 0)
        if ok:
            self.config.last_lists_update = int(time.time())
            self.config.save()
            if changed > 0:
                self._reload_domain_files()
                self._restart_engine_fresh()
        if manual:
            if ok:
                QMessageBox.information(self, self._msg_title("Обновление"), self._msg_text(msg))
            else:
                QMessageBox.warning(self, self._msg_title("Обновление"), self._msg_text(msg))

    def show_hosts_dialog(self) -> None:
        block = list_manager.build_hosts_block(self.zapret_dir, allow_network=True)
        if not block.strip():
            QMessageBox.warning(
                self,
                self._msg_title("HOSTS для Windows"),
                self._msg_text("Не удалось сформировать HOSTS-строки. Обновите списки/IPset и попробуйте снова."),
            )
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("HOSTS для Windows"))
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        hosts_current = list_manager.hosts_block_is_current(block)
        info_text = (
            "HOSTS уже содержит а��туальный блок ZapretGUI. Повторное применение не нужно."
            if hosts_current else
            "Скопируйте эти строки в Windows HOSTS или нажмите «Применить». "
            "Автоматическое применение создаёт backup и заменяет только блок ZapretGUI."
        )
        info = QLabel(info_text)
        info.setWordWrap(True)
        lay.addWidget(info)
        text = QPlainTextEdit()
        text.setObjectName("cmdPreview")
        text.setPlainText(block)
        text.setFont(_smooth_code_font(11))
        lay.addWidget(text, 1)
        row = QHBoxLayout()
        btn_copy = QPushButton("Копировать")
        btn_apply = QPushButton("Уже применено" if hosts_current else "Применить")
        btn_apply.setEnabled(not hosts_current)
        btn_remove = QPushButton("Удалить блок")
        btn_close = QPushButton("Закрыть")
        for b in (btn_copy, btn_apply, btn_remove, btn_close):
            b.setObjectName("secondaryBtn")
        row.addWidget(btn_copy)
        row.addStretch(1)
        row.addWidget(btn_remove)
        row.addWidget(btn_apply)
        row.addWidget(btn_close)
        lay.addLayout(row)

        def _copy() -> None:
            QApplication.clipboard().setText(text.toPlainText())
            self._log("[hosts] строки скопированы в буфер обмена")

        def _apply() -> None:
            ans = QMessageBox.question(
                dlg,
                self._msg_title("HOSTS для Windows"),
                self._msg_text(
                    "Применить блок ZapretGUI к системному HOSTS?\n\n"
                    "Будет создан backup hosts.zapretgui.bak. Нужны права администратора."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            msg = list_manager.apply_hosts_block(text.toPlainText())
            self._log("[hosts] " + msg)
            QMessageBox.information(dlg, self._msg_title("HOSTS для Windows"), self._msg_text(msg))

        def _remove() -> None:
            ans = QMessageBox.question(
                dlg,
                self._msg_title("HOSTS для Windows"),
                self._msg_text("Удалить блок ZapretGUI из системного HOSTS?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            msg = list_manager.remove_hosts_block()
            self._log("[hosts] " + msg)
            QMessageBox.information(dlg, self._msg_title("HOSTS для Windows"), self._msg_text(msg))

        btn_copy.clicked.connect(_copy)
        btn_apply.clicked.connect(_apply)
        btn_remove.clicked.connect(_remove)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec()

    def _toggle_theme(self, theme_id: str, checked: bool = True) -> None:
        """Apply a theme by id. ``checked`` is kept for backwards-compat
        with the old checkbox wiring — the dropdown menu always passes True."""
        if not checked:
            return
        from .themes_catalog import THEMES
        # Validate the theme_id against the catalog. Unknown → fall back to purple.
        valid_ids = {t.id for t in THEMES}
        if theme_id not in valid_ids:
            theme_id = "purple"
        self.current_theme = theme_id
        self.config.theme = theme_id
        self.config.save()
        self._apply_theme()
        # Update the theme-selector button label so it shows the new theme.
        if hasattr(self, "btn_theme_select"):
            self.btn_theme_select.setText(self._current_theme_display_name())

    def _current_theme_display_name(self) -> str:
        """Display name of the current theme, localized."""
        from .themes_catalog import get_theme
        t = get_theme(self.current_theme)
        return self._t(t.name_ru) if self.lang == "en" else t.name_ru

    def _show_theme_menu(self) -> None:
        """Open a dropdown menu listing all available themes. Selecting one
        applies it immediately."""
        from .themes_catalog import THEMES
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        # Use the system font for the menu (the app-wide font is the bundled
        # display font which is too "branded" for a context menu).
        try:
            from PyQt6.QtGui import QFontDatabase
            menu.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
        except Exception:
            pass
        # Group: presets first, then image themes, with a separator.
        presets = [t for t in THEMES if t.group == "preset"]
        images = [t for t in THEMES if t.group == "image"]
        for t in presets:
            act = menu.addAction(t.name_ru if self.lang != "en" else t.name_en)
            act.setCheckable(True)
            act.setChecked(t.id == self.current_theme)
            act.triggered.connect(lambda _checked=False, tid=t.id: self._toggle_theme(tid))
        if images:
            menu.addSeparator()
            for t in images:
                act = menu.addAction(t.name_ru if self.lang != "en" else t.name_en)
                act.setCheckable(True)
                act.setChecked(t.id == self.current_theme)
                act.triggered.connect(lambda _checked=False, tid=t.id: self._toggle_theme(tid))
        # Show below the button.
        btn = self.btn_theme_select
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft() + QPoint(0, 4)))

    def _apply_theme(self) -> None:
        """Apply the current theme: QSS, background, nav glow, shadows, icons.

        For image themes (group=="image") we use the theme's FULL generated
        QSS (NOT appended on top of DARK_QSS — otherwise the purple-theme
        colours would bleed through). The generated QSS covers every widget
        with the theme's palette, so text is readable on every background.

        For the 3 preset themes we keep the original behaviour (procedural
        purple gradient / flat dark / flat light).
        """
        from .themes_catalog import get_theme, is_image_theme, get_theme_qss
        theme_id = getattr(self, "current_theme", "purple")
        theme = get_theme(theme_id)
        is_image = is_image_theme(theme_id)
        is_dark_preset = theme_id == "dark"
        is_light_preset = theme_id == "light"
        is_neutral = is_dark_preset or is_light_preset  # flat-fill presets
        # --- QSS: use the new get_theme_qss() resolver ---
        base_qss = {
            "DARK": DARK_QSS,
            "WIN11_DARK": WIN11_DARK_QSS,
            "WIN11_LIGHT": WIN11_LIGHT_QSS,
        }
        full_qss = get_theme_qss(theme_id, base_qss)
        self.setStyleSheet(full_qss)
        # Swap the home-tab layout: dark theme uses its own arrangement,
        # purple/light keep the original classic layout.
        if hasattr(self, "home_body"):
            self._apply_home_layout(is_dark_preset)
        # --- Raised 3D home surfaces (dark preset only) ---
        for home_surface in (
            getattr(self, "home_tg_card", None),
            getattr(self, "home_zap_card", None),
            getattr(self, "home_runner_card", None),
            getattr(self, "home_auto_panel", None),
            getattr(self, "btn_auto", None),
            getattr(self, "btn_check", None),
        ):
            if home_surface is None or not hasattr(home_surface, "set_dark_3d"):
                continue
            home_surface.set_dark_3d(is_dark_preset)
            if is_dark_preset:
                if home_surface.graphicsEffect() is None:
                    shadow = QGraphicsDropShadowEffect(home_surface)
                    shadow.setBlurRadius(34)
                    shadow.setOffset(0, 9)
                    shadow.setColor(QColor(0, 0, 0, 165))
                    home_surface.setGraphicsEffect(shadow)
            elif home_surface.graphicsEffect() is not None:
                home_surface.setGraphicsEffect(None)
        if hasattr(self, "home_auto_panel"):
            self._set_dark_auto_panel_active(self._auto_thread is not None)
        # --- Power button theme colours ---
        # The PowerButton is custom-painted (not styled by QSS), so we need
        # to explicitly tell it what colours to use for the glyph + gradient
        # backing. For image themes, use the theme's accent as the stopped
        # colour and green (#37c871) as the running colour. For the purple
        # preset, use the defaults (None = green/purple).
        if hasattr(self, "btn_toggle") and is_image:
            self.btn_toggle.set_theme_colors(
                running_color="#37c871",
                stopped_color=theme.accent,
                running_hue=135,
                stopped_hue=theme._stopped_hue if hasattr(theme, '_stopped_hue') else None,
            )
        elif hasattr(self, "btn_toggle"):
            if is_dark_preset:
                self.btn_toggle.set_theme_colors(
                    running_color="#37c871",
                    stopped_color="#ff1010",
                    running_hue=135,
                    stopped_hue=-1,
                )
            else:
                self.btn_toggle.set_theme_colors()  # Reset to defaults
        # --- Background ---
        if hasattr(self, "_bg"):
            if is_image and theme.bg_image:
                # Resolve the theme background image path.
                bg_path = self._resolve_theme_image_path(theme.bg_image)
                self._bg.set_theme_image(bg_path)
            else:
                # Disable image-theme mode so the procedural/flat renderer takes over.
                self._bg.set_theme_image("")
            self._update_bg_mode(self.tabs.currentIndex() if hasattr(self, "tabs") else 0)
        # --- Nav glow ---
        if hasattr(self, "_top_nav") and hasattr(self._top_nav, "_glow"):
            if is_image:
                glow_color = QColor(theme.nav_glow) if theme.nav_glow else QColor(150, 120, 255, 180)
                self._top_nav._glow.setColor(glow_color)
                self._top_nav._glow.setBlurRadius(getattr(self._top_nav, "_base_blur", 26))
            elif is_neutral:
                self._top_nav._glow.setColor(QColor(0, 0, 0, 0))
                self._top_nav._glow.setBlurRadius(0)
            else:
                self._top_nav._glow.setColor(QColor(150, 120, 255, 180))
                self._top_nav._glow.setBlurRadius(getattr(self._top_nav, "_base_blur", 26))
        # --- Card shadows: keep for image + purple themes; disable for flat presets ---
        if hasattr(self, "settings_card"):
            if is_neutral:
                self.settings_card.setGraphicsEffect(None)
            elif self.settings_card.graphicsEffect() is None:
                card_shadow = QGraphicsDropShadowEffect(self.settings_card)
                card_shadow.setBlurRadius(34)
                card_shadow.setOffset(0, 8)
                card_shadow.setColor(QColor(0, 0, 0, 95))
                self.settings_card.setGraphicsEffect(card_shadow)
        if hasattr(self, "status_pill"):
            if is_neutral:
                self.status_pill.setGraphicsEffect(None)
            elif self.status_pill.graphicsEffect() is None:
                pill_shadow = QGraphicsDropShadowEffect(self.status_pill)
                pill_shadow.setBlurRadius(24)
                pill_shadow.setOffset(0, 2)
                pill_shadow.setColor(QColor(0, 0, 0, 95))
                self.status_pill.setGraphicsEffect(pill_shadow)
        # Neutral themes (dark/light) remove decorative cats and action icons.
        # Image themes + purple keep them.
        show_decor = not is_neutral
        if hasattr(self, "settings_cat"):
            self.settings_cat.setVisible(show_decor)
        if hasattr(self, "btn_auto"):
            self.btn_auto.setIcon(QIcon() if not show_decor else QIcon(asset_path("auto_select_icon_256.png")))
            self.btn_auto.setIconSize(QSize(0, 0) if not show_decor else QSize(50, 50))
        if hasattr(self, "btn_check"):
            self.btn_check.setIcon(QIcon() if not show_decor else QIcon(asset_path("check_icon_256.png")))
            self.btn_check.setIconSize(QSize(0, 0) if not show_decor else QSize(50, 50))
        # Update the theme-selector button label (in case it was created
        # before the theme was applied — e.g. on first launch).
        if hasattr(self, "btn_theme_select"):
            self.btn_theme_select.setText(self._current_theme_display_name())
            if is_dark_preset:
                self.btn_theme_select.setStyleSheet(
                    "QPushButton { background: #2d2d2d; border: 1px solid #5a5a5a; "
                    "border-radius: 14px; color: #ffffff; padding: 7px 18px; "
                    "min-height: 32px; max-height: 32px; font-weight: 600; }"
                    "QPushButton:hover { background: #3a3a3a; border-color: #777777; }"
                    "QPushButton:pressed { background: #252525; border-color: #888888; }"
                )
            else:
                self.btn_theme_select.setStyleSheet("")
        # Compact Settings composition is exclusive to the dark preset.
        # Other themes retain their original spacing and presentation.
        if hasattr(self, "settings_root_layout") and hasattr(self, "settings_card_layout"):
            if is_dark_preset:
                self.settings_root_layout.setContentsMargins(42, 12, 42, 12)
                self.settings_card_layout.setContentsMargins(48, 14, 48, 14)
                self.settings_card_layout.setSpacing(0)
                if hasattr(self, "settings_rows_layout"):
                    self.settings_rows_layout.setSpacing(12)
                if hasattr(self, "settings_updates_layout"):
                    self.settings_updates_layout.setSpacing(8)
                if hasattr(self, "settings_theme_gap"):
                    self.settings_theme_gap.setVisible(True)
                    self.settings_theme_gap.setFixedHeight(30)
                if hasattr(self, "settings_theme_selector_gap"):
                    self.settings_theme_selector_gap.setVisible(True)
                    self.settings_theme_selector_gap.setFixedHeight(20)
                if hasattr(self, "settings_updates_gap"): 
                    self.settings_updates_gap.setVisible(True)
                    self.settings_updates_gap.setFixedHeight(30)
                for row, row_lay, cb in getattr(self, "settings_rows", []):
                    row.setMinimumHeight(45)
                    row.setMaximumHeight(45)
                    row_lay.setContentsMargins(18, 0, 18, 0)
                    cb.setStyleSheet(
                        "QCheckBox#settingsCheck { padding: 0; }"
                        "QCheckBox#settingsCheck::indicator { width: 21px; height: 21px; }"
                    )
            else:
                self.settings_root_layout.setContentsMargins(42, 24, 42, 16)
                self.settings_card_layout.setContentsMargins(48, 18, 48, 18)
                self.settings_card_layout.setSpacing(8)
                if hasattr(self, "settings_rows_layout"):
                    self.settings_rows_layout.setSpacing(8)
                if hasattr(self, "settings_updates_layout"):
                    self.settings_updates_layout.setSpacing(8)
                if hasattr(self, "settings_theme_gap"):
                    self.settings_theme_gap.setVisible(False)
                if hasattr(self, "settings_theme_selector_gap"):
                    self.settings_theme_selector_gap.setVisible(False)
                if hasattr(self, "settings_updates_gap"): 
                    self.settings_updates_gap.setVisible(True)
                    self.settings_updates_gap.setFixedHeight(8)
                for row, row_lay, cb in getattr(self, "settings_rows", []):
                    row.setMinimumHeight(0)
                    row.setMaximumHeight(16777215)
                    row_lay.setContentsMargins(18, 5, 18, 5)
                    cb.setStyleSheet("")
        self._set_power_state(self.runner.is_running() if hasattr(self, "runner") else False)

    def _resolve_theme_image_path(self, filename: str) -> str:
        """Resolve the absolute path to a theme background image.

        Looks under ui/assets/themes/ — both from source (ui/assets/themes)
        and when frozen by PyInstaller (sys._MEIPASS/ui/assets/themes).
        """
        roots = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "ui" / "assets" / "themes")
            roots.append(Path(meipass) / "assets" / "themes")
        here = Path(__file__).resolve().parent
        roots.append(here / "assets" / "themes")
        for root in roots:
            cand = root / filename
            try:
                if cand.is_file():
                    return str(cand)
            except OSError:
                pass
        return ""

    def _set_power_state(self, on: bool) -> None:
        btn = self.btn_toggle
        btn.setProperty("running", "true" if on else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        if hasattr(self, "btn_toggle"):
            self.btn_toggle.set_running(on)
        # The glow around the power button only makes sense on the procedural
        # purple theme. Image themes and flat presets disable it.
        from .themes_catalog import is_image_theme
        cur = getattr(self, "current_theme", "purple")
        # Dark-theme cat emotion: stopped = closed eyes, running = open eyes.
        # Both pixmaps share an identical canvas and alpha mask, so the swap is
        # pixel-aligned and cannot shift or resize the mascot.
        auto_cat_active = cur == "dark" and bool(getattr(self, "_home_cat_auto_active", False))
        if cur == "dark" and hasattr(self, "home_cat") and not auto_cat_active:
            cat_pixmap = (
                getattr(self, "_home_cat_open_pixmap", QPixmap())
                if on
                else getattr(self, "_home_cat_closed_pixmap", QPixmap())
            )
            if not cat_pixmap.isNull():
                self.home_cat.setPixmap(cat_pixmap)
        if hasattr(self, "sleep_z"):
            self.sleep_z.set_sleeping(cur == "dark" and not on and not auto_cat_active)
        if cur == "dark":
            # Static glow for the dark home: green when running, red when off.
            if hasattr(self, "_glow_anim"):
                self._glow_anim.stop()
            if hasattr(self, "_glow_color_anim"):
                self._glow_color_anim.stop()
            if hasattr(self, "_glow"):
                self._glow.setColor(QColor(60, 220, 130) if on else QColor(255, 76, 92))
                self._glow.setBlurRadius(64)
        elif cur == "light" or is_image_theme(cur):
            self._stop_glow()
        elif on:
            self._start_glow()
        else:
            self._stop_glow()

    def _start_glow(self) -> None:
        if hasattr(self, "_glow"):
            self._glow.setColor(QColor(70, 220, 130))
        if hasattr(self, "_glow_anim") and self._glow_anim.state() != QPropertyAnimation.State.Running:
            self._glow_anim.start()
        if hasattr(self, "_glow_color_anim") and self._glow_color_anim.state() != QPropertyAnimation.State.Running:
            self._glow_color_anim.start()

    def _stop_glow(self) -> None:
        if hasattr(self, "_glow_anim"):
            self._glow_anim.stop()
        if hasattr(self, "_glow_color_anim"):
            self._glow_color_anim.stop()
        if hasattr(self, "_glow"):
            self._glow.setColor(QColor(150, 90, 240))
            self._glow.setBlurRadius(26)

    def _refresh_status(self) -> None:
        if hasattr(self, "home_tg_srv"):
            self._refresh_home_cards()
        running = self.runner.is_running()
        if running:
            strat = self.runner.current_strategy
            name = strat.name if strat else ""
            self.status_dot.setStyleSheet("color: #37c871; padding-top: 2px;")
            self.status_label.setText(self._t("подключено"))
            self.tray.set_state("running", name or "работает")
            if hasattr(self, "run_field"):
                self.run_field.setText(name or "\u2014")
            self._set_power_state(True)
        else:
            self.status_dot.setStyleSheet("color: #ff5c6c; padding-top: 2px;")
            self.status_label.setText(self._t("отключено"))
            self.tray.set_state("stopped", "остановлен")
            if hasattr(self, "run_field"):
                self.run_field.setText("\u2014")
            self._set_power_state(False)
        svc_text = self.service.status_text()
        if hasattr(self, "svc_label"):
            self.svc_label.setText(self._t("Служба автозапуска: ") + svc_text)
        if hasattr(self, "svc_inline"):
            self.svc_inline.setText(self._t("Служба: ") + svc_text)

    # ------------------------------------------------------------- window
    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._force_quit = True
        self._user_stop = True
        if hasattr(self, "waiting_runner_game"):
            self.waiting_runner_game.shutdown()
        # Cancel any in-flight worker so it stops calling runner.start() and
        # doesn't re-launch winws after we've stopped it below.
        self._cancel_and_join_workers()
        self.runner.stop()
        # Also stop the Telegram proxy engine. ``stop()`` is non-blocking;
        # ``wait_for_stop`` then joins the engine thread for up to 6s so the
        # asyncio loop has time to close cleanly (otherwise asyncio prints
        # "Task was destroyed but it is pending!" on process exit).
        try:
            self.tg_runner.stop()
            self.tg_runner.wait_for_stop(timeout=6.0)
        except Exception:
            pass
        self.tray.hide()
        QApplication.instance().quit()

    def _cancel_and_join_workers(self) -> None:
        """Stop every background worker cleanly so it can't re-launch winws
        after quit. Each worker is told to cancel (where supported), then we
        quit/wait its QThread so the worker object is safely destroyed."""
        # Auto-select worker: needs an explicit cancel().
        if self._auto_worker is not None:
            try:
                self._auto_worker.cancel()
            except Exception:
                pass
        # Update worker: best-effort; it only calls the network so a quick
        # quit/wait is enough. Includes the TG proxy update thread.
        for attr in (
            "_auto_thread",
            "_update_thread",
            "_check_thread",
            "_bootstrap_thread",
            "_tg_update_thread",
        ):
            thread = getattr(self, attr, None)
            if thread is None:
                continue
            try:
                thread.quit()
                thread.wait(2000)
            except Exception:
                pass
            setattr(self, attr, None)
        # Drop worker refs so they don't outlive their threads.
        self._auto_worker = None
        self._update_worker = None
        self._check_worker = None
        self._bootstrap_worker = None

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._force_quit:
            self._user_stop = True
            self.runner.stop()
            event.accept()
            return

        if self.runner.is_running():
            popup = StyledPopup(
                "Zapret всё ещё работает",
                "Оставить приложение в трее или полностью выключить обход?",
                self,
                ok_text="В трей",
                cancel_text="Выключить",
                show_close=False,
            )
            popup.exec()
            if popup.result_name() == "ok":
                event.ignore()
                self.hide()
                self.tray.showMessage("Zapret GUI", self._t("Приложение свёрнуто в трей."))
            else:
                # The user chose to fully turn the bypass off — actually quit
                # the app. QuitOnLastWindowClosed is False, so without an
                # explicit quit() the process would keep living in the tray.
                self.quit_app()
                event.accept()
            return

        if not self.config.minimize_to_tray:
            # "Minimize to tray on close" is off: closing the window must end
            # the program, not leave a hidden process behind.
            self.quit_app()
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.tray.showMessage("Zapret GUI", self._t("Приложение свёрнуто в трей."))
