"""Automatic strategy selection flow for :class:`~ui.main_window.MainWindow`.

Split out of ``ui/main_window.py`` unchanged. Everything here serves one
scenario: the user presses "Auto", a background sweep tries strategies one by
one, and the result is reported either through the dark-theme Home panel (with
the waiting mini-game) or through a popup on the other themes.

The methods stay a mixin instead of a standalone object because they touch a
lot of window state (``runner``, ``config``, ``manager``, the Home widgets,
the tray and the log view). ``hasattr``/``getattr`` guards are kept exactly as
they were: the dark-theme widgets only exist while that theme is active, and
the auto panel may be missing entirely during early startup or in tests.

State attributes owned by this flow and initialised in ``MainWindow.__init__``:
``_auto_thread``, ``_auto_worker``, ``_auto_popup``, ``_auto_popup_closing``,
``_pending_auto_result``.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, QTimer

from app.auto_selector import AutoSelectResult, AutoSelector

from .widgets_custom import AutoSelectProgressPopup, StyledPopup
from .workers import AutoSelectWorker


class AutoSelectFlowMixin:
    """Start, cancel and report the automatic strategy sweep."""

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
                self._set_home_cat_frame("search")
                if hasattr(self, "sleep_z"):
                    self.sleep_z.set_sleeping(False)
            else:
                running = bool(self.runner.is_running()) if hasattr(self, "runner") else False
                self._set_home_cat_frame("open" if running else "closed")
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
            max_deep_candidates=self.config.max_deep_candidates,
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
                    "Стратегия найдена",
                    f"Полностью рабочая стратегия не найдена.\nВключена наиболее подходящая: {result.strategy.name}\n({result.detail}){lat}",
                    self,
                ).exec()
            else:
                kind = ("Best" if result.mode == "best" else "Working") if self.lang == "en" else ("Лучшая" if result.mode == "best" else "Рабочая")
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
                "Ни одна стратегия не разблокировала доступ.\nПопробуйте обновить списки доменов и убедитесь, что приложение запущено от имени администратора.",
                self,
            ).exec()
        self._refresh_status()
