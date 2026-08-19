"""Main application window: Home / Settings / Strategy (list + editor + logs)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from app.config import AppConfig, default_data_dir
from app.service_manager import ServiceManager
from app.strategy_manager import Strategy, StrategyManager
from app import tg_proxy
# Translation tables live in ui/i18n.py; re-exported here because the window
# and the tests import these names from this module.
from .i18n import (
    localize_runtime_text,
    tr_text,
)
from .icons import NAV_ICON_NAMES
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
from .auto_select_flow import AutoSelectFlowMixin
from .editor_flow import EditorFlowMixin
from .theme_apply import ThemeApplyMixin
from .tray import Tray
from .update_flow import UpdateFlowMixin
from .window_bootstrap import BootstrapMixin
from .window_engine import EngineControlMixin
from .window_lists import ListsMixin
from .window_settings import SettingsActionsMixin
# Painted widgets and popups live in ui/widgets_custom.py.
from .widgets_custom import (
    StyledPopup,
    _GlassNav,
)
from .workers import AutoSelectWorker


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


class MainWindow(
    ListsMixin,
    BootstrapMixin,
    EngineControlMixin,
    SettingsActionsMixin,
    HomeTabMixin,
    TelegramTabMixin,
    GamesTabMixin,
    StrategyTabMixin,
    SettingsTabMixin,
    AutoSelectFlowMixin,
    EditorFlowMixin,
    UpdateFlowMixin,
    ThemeApplyMixin,
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
            "Настройки",
            "Стратегия",
            "Игры и сервисы",
            "Telegram",
        ], on_select=self.tabs.setCurrentIndex,
           icon_names=list(NAV_ICON_NAMES))
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

        # If a silent self-update just relaunched us, show what changed --
        # the installer itself never displayed a single window for this.
        QTimer.singleShot(400, self._check_pending_update_changelog)

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
            # Check our own GitHub for a new Zapret GUI installer (silent
            # on launch -- only shows a dialog if a newer version exists).
            QTimer.singleShot(7000, self._check_app_update_silent)
        if start_minimized:
            QTimer.singleShot(0, self.hide)

    # ------------------------------------------------------------------ tab fade
    def _fade_current_tab(self, index: int) -> None:
        """Subtle iOS-style fade-in of the freshly selected section."""
        try:
            w = self.tabs.widget(index)
            if w is None:
                return
            # No transition animation here on purpose -- two of them have been
            # tried and both were worse than an instant switch:
            #
            # 1. QGraphicsOpacityEffect renders the whole page into an
            #    offscreen pixmap; with the fractional QT_SCALE_FACTOR that
            #    main.py sets (plus PassThrough rounding) every glyph gets
            #    re-snapped to that pixmap grid and snaps back once the effect
            #    is removed -- the "text jumps a couple of pixels and returns"
            #    flicker. It also flattens child glow/shadow effects.
            # 2. Sliding the page in by animating its position avoided all of
            #    that, but simply looked worse in practice and was dropped at
            #    the user's request.
            anim = getattr(self, "_tab_fade_anim", None)
            if anim is not None:
                anim.stop()
                self._tab_fade_anim = None
            if w.graphicsEffect() is not None:
                w.setGraphicsEffect(None)
            w.update()
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
            self.games_filter_warn.setText(self._t("Применяет DPI-обход к игровому UDP/TCP на высоких портах. Иногда помогает (если сервис режется по DPI), но ЧАЩЕ ломает игры — в РФ они обычно не блокируются по DPI. Включай для теста; стало хуже — выключи."))
        # Telegram tab dynamic text.
        if hasattr(self, "tg_title"):
            self.tg_title.setText(self._t("Telegram прокси"))
        if hasattr(self, "tg_subtitle"):
            self.tg_subtitle.setText(self._t(
                "Локальный MTProto-прокси для Telegram Desktop. Telegram подключается к нему, "
                "а прокси туннелирует трафик через WebSocket к серверам Telegram — обход блокировок "
                "без сторонних серверов."
            ))
        if hasattr(self, "cb_tg_autostart"):
            self.cb_tg_autostart.setText(self._t("Запускать вместе с zapret"))
        if hasattr(self, "btn_tg_copy"):
            self.btn_tg_copy.setText(self._t("Скопировать ссылку"))
        if hasattr(self, "btn_tg_open"):
            self.btn_tg_open.setText(self._t("Открыть в Telegram"))
        if hasattr(self, "btn_tg_rotate"):
            self.btn_tg_rotate.setText(self._t("Сгенерировать новый secret"))
        if hasattr(self, "btn_tg_update"):
            self.btn_tg_update.setText(self._t("Проверить обновления tg-ws-proxy"))
        try:
            tab_titles = ["Главная", "Настройки", "Стратегия", "Игры и сервисы", "Telegram"]
            for i, txt in enumerate(tab_titles):
                label = self._t(txt)
                if self.lang == "en" and txt == "Игры и сервисы":
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
        # Self-update download worker: a ~55 MB download would otherwise keep
        # the thread alive past quit and blow the wait() timeout below.
        # The plain update *check* worker has no cancel(), hence the try.
        app_update_worker = getattr(self, "_app_update_worker", None)
        if app_update_worker is not None:
            try:
                app_update_worker.cancel()
            except Exception:
                pass
        # Update worker: best-effort; it only calls the network so a quick
        # quit/wait is enough. Includes the TG proxy update thread.
        for attr in (
            "_auto_thread",
            "_update_thread",
            "_check_thread",
            "_bootstrap_thread",
            "_list_update_thread",
            "_tg_update_thread",
            "_app_update_thread",
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
        self._list_update_worker = None
        self._app_update_worker = None

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
