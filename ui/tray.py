"""System tray icon with status colour and quick actions."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QFontDatabase, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .paths import asset_path_or_empty


# Shared with main_window and theme (see ui/paths.py). Returns "" when the
# icon file is missing, which makes _star_icon fall back to a drawn dot.
_asset_path = asset_path_or_empty


def _dot_icon(color: str) -> QIcon:
    """Fallback icon if custom star assets are unavailable."""
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QColor(0, 0, 0, 0))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pix)


def _star_icon(filename: str, fallback_color: str) -> QIcon:
    """Build a tray QIcon from the custom star PNG at several crisp sizes."""
    path = _asset_path(filename)
    if not path:
        return _dot_icon(fallback_color)
    source = QPixmap(path)
    if source.isNull():
        return _dot_icon(fallback_color)
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48):
        pix = source.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon.addPixmap(pix)
    return icon




def _tray_text(lang: str, ru: str, en: str) -> str:
    return en if lang == "en" else ru


def _tray_label(lang: str, label: str) -> str:
    mapping = {
        "остановлен": "stopped",
        "работает": "running",
        "подбор...": "selecting...",
        "stopped": "остановлен",
        "running": "работает",
        "selecting...": "подбор...",
    }
    if lang == "en":
        return mapping.get(label, label)
    return mapping.get(label, label)


TRAY_ICONS = {
    "running": ("tray_star_on.png", "#37c871"),
    "stopped": ("tray_star_off.png", "#d9434e"),
    # During auto-select there are only two custom states, so keep the active
    # green star while the app is working.
    "working": ("tray_star_on.png", "#37c871"),
}


class Tray(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._lang = getattr(window, "lang", "ru")
        self._state = "stopped"
        self._label = "остановлен"
        self._tg_running = False
        self.setIcon(_star_icon(*TRAY_ICONS["stopped"]))
        self.setToolTip("Zapret GUI")

        menu = QMenu()
        # Keep the previous (system) UI font for the tray menu only — the rest
        # of the app uses the bundled Unbounded font.
        menu.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        )
        self.act_status = QAction("\u0421\u0442\u0430\u0442\u0443\u0441: \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d", menu)
        self.act_status.setEnabled(False)
        self.act_toggle = QAction("\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c", menu)
        self.act_auto = QAction("\u0410\u0432\u0442\u043e\u043f\u043e\u0434\u0431\u043e\u0440", menu)
        self.act_show = QAction("\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043e\u043a\u043d\u043e", menu)
        self.act_exit = QAction("\u0412\u044b\u0445\u043e\u0434", menu)

        menu.addAction(self.act_status)
        menu.addSeparator()
        menu.addAction(self.act_toggle)
        menu.addAction(self.act_auto)
        menu.addSeparator()
        menu.addAction(self.act_show)
        menu.addAction(self.act_exit)
        self.setContextMenu(menu)

        self.act_toggle.triggered.connect(window.toggle_engine)
        self.act_auto.triggered.connect(window.start_auto_select)
        self.act_show.triggered.connect(window.show_normal)
        self.act_exit.triggered.connect(window.quit_app)
        self.activated.connect(self._on_activated)

        # Telegram proxy submenu — added lazily so the tray still works even
        # if the TG runner hasn't been initialized yet.
        try:
            self._build_tg_menu(menu)
        except Exception:
            pass

    def _build_tg_menu(self, parent_menu: QMenu) -> None:
        """Append a Telegram submenu with toggle/open-in-Telegram/rotate-secret entries.

        The submenu EXPLICITLY inherits the parent menu's system font —
        otherwise Qt would fall back to the application-wide font (the bundled
        Unbounded display font), which looks oversized and out of place in
        the tray context menu.
        """
        self.tg_menu = parent_menu.addMenu(_tray_text(self._lang, "Telegram", "Telegram"))
        # Force the same system font the parent menu uses, otherwise the
        # submenu inherits the app-wide Unbounded font (too big, too "branded"
        # for a tray context menu).
        try:
            self.tg_menu.setFont(parent_menu.font())
        except Exception:
            pass
        self.act_tg_status = QAction(
            _tray_text(self._lang, "Прокси выключен", "Proxy off"), self.tg_menu
        )
        self.act_tg_status.setEnabled(False)
        self.act_tg_toggle = QAction(
            _tray_text(self._lang, "Запустить прокси", "Start proxy"), self.tg_menu
        )
        self.act_tg_open = QAction(
            _tray_text(self._lang, "Открыть в Telegram", "Open in Telegram"), self.tg_menu
        )
        self.act_tg_copy = QAction(
            _tray_text(self._lang, "Скопировать ссылку", "Copy link"), self.tg_menu
        )
        self.act_tg_rotate = QAction(
            _tray_text(self._lang, "Сгенерировать новый secret", "Generate new secret"), self.tg_menu
        )
        self.tg_menu.addAction(self.act_tg_status)
        self.tg_menu.addSeparator()
        self.tg_menu.addAction(self.act_tg_toggle)
        self.tg_menu.addAction(self.act_tg_open)
        self.tg_menu.addAction(self.act_tg_copy)
        self.tg_menu.addAction(self.act_tg_rotate)
        # Wire to the window's TG methods if they exist.
        if hasattr(self._window, "tg_toggle"):
            self.act_tg_toggle.triggered.connect(self._window.tg_toggle)
        if hasattr(self._window, "tg_open_in_telegram"):
            self.act_tg_open.triggered.connect(self._window.tg_open_in_telegram)
        if hasattr(self._window, "tg_copy_link"):
            self.act_tg_copy.triggered.connect(self._window.tg_copy_link)
        if hasattr(self._window, "tg_rotate_secret"):
            self.act_tg_rotate.triggered.connect(self._window.tg_rotate_secret)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._window.show_normal()

    def set_language(self, lang: str) -> None:
        self._lang = lang if lang in ("ru", "en") else "ru"
        self.act_auto.setText(_tray_text(self._lang, "Автоподбор", "Auto-select"))
        self.act_show.setText(_tray_text(self._lang, "Открыть окно", "Open window"))
        self.act_exit.setText(_tray_text(self._lang, "Выход", "Exit"))
        if hasattr(self, "tg_menu"):
            self.tg_menu.setTitle(_tray_text(self._lang, "Telegram", "Telegram"))
            self.act_tg_status.setText(
                _tray_text(self._lang, "Прокси выключен", "Proxy off")
                if not self._tg_running
                else _tray_text(self._lang, "Прокси запущен", "Proxy running")
            )
            self.act_tg_toggle.setText(
                _tray_text(self._lang, "Остановить прокси", "Stop proxy")
                if self._tg_running
                else _tray_text(self._lang, "Запустить прокси", "Start proxy")
            )
            self.act_tg_open.setText(_tray_text(self._lang, "Открыть в Telegram", "Open in Telegram"))
            self.act_tg_copy.setText(_tray_text(self._lang, "Скопировать ссылку", "Copy link"))
            self.act_tg_rotate.setText(_tray_text(self._lang, "Сгенерировать новый secret", "Generate new secret"))
        self.set_state(self._state, self._label)

    def set_state(self, state: str, label: str) -> None:
        self._state = state
        self._label = label
        display_label = _tray_label(self._lang, label)
        self.setIcon(_star_icon(*TRAY_ICONS.get(state, TRAY_ICONS["stopped"])))
        self.act_status.setText(f"{_tray_text(self._lang, 'Статус', 'Status')}: {display_label}")
        self.act_toggle.setText(
            _tray_text(self._lang, "Остановить", "Stop") if state == "running" else _tray_text(self._lang, "Запустить", "Start")
        )
        self.setToolTip(f"Zapret GUI — {display_label}")

    def set_tg_running(self, running: bool) -> None:
        """Update the Telegram submenu to reflect the proxy's current state."""
        self._tg_running = bool(running)
        if not hasattr(self, "act_tg_status"):
            return
        self.act_tg_status.setText(
            _tray_text(self._lang, "Прокси запущен", "Proxy running")
            if running
            else _tray_text(self._lang, "Прокси выключен", "Proxy off")
        )
        self.act_tg_toggle.setText(
            _tray_text(self._lang, "Остановить прокси", "Stop proxy")
            if running
            else _tray_text(self._lang, "Запустить прокси", "Start proxy")
        )
