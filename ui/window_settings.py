"""Settings-tab actions: folder picker and feature toggles."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from app import autostart
from app.service_manager import ServiceManager
from app.strategy_manager import StrategyManager


class SettingsActionsMixin:
    """Handlers behind the checkboxes and buttons of the settings tab."""

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
