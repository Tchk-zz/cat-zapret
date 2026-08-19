"""Engine start/stop, connectivity checks and status indicators."""
from __future__ import annotations

from PyQt6.QtCore import QPropertyAnimation, QThread
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox

from .effects import effects_supported
from .widgets_custom import BypassTestPopup, StyledPopup
from .workers import CheckWorker


class EngineControlMixin:
    """Power button, engine lifecycle, manual check and status glow."""

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
        # Give WinDivert a moment to actually release the filter before we
        # re-grab it. This used to be QTimer.singleShot(500, lambda: None),
        # which scheduled an empty callback and returned immediately: the wait
        # never happened and winws.exe was launched while the driver handle was
        # still held -- the exact conflict this function exists to prevent.
        # Sleeping on the GUI thread is deliberate; a nested event loop would
        # let the user press "Start" again in the middle of the stop sequence.
        import time as _time

        _time.sleep(0.6)
        return True

    def start_engine(self) -> None:
        strat = self._current_strategy()
        if strat is None:
            StyledPopup(
                "Ошибка запуска",
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
            # winws never started, so skip the Telegram-proxy autostart below
            # and only refresh the buttons. Without this return the app showed
            # the error popup and then continued as if the bypass was running.
            self._refresh_status()
            return
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
            self._set_home_cat_frame("open" if on else "closed")
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
        # Nothing is installed on the button when the UI runs at a scale below
        # 1 (see ui/effects.py), so driving the animations would only burn CPU.
        if not effects_supported():
            return
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
        # This method runs on a 2s timer. setStyleSheet() re-parses the sheet
        # and repolishes the widget every single time, so the dot colour is
        # only rewritten when the state actually flips.
        if running != getattr(self, "_status_dot_running", None):
            self.status_dot.setStyleSheet(
                "color: #37c871; padding-top: 2px;"
                if running
                else "color: #ff5c6c; padding-top: 2px;"
            )
            self._status_dot_running = running
        if running:
            strat = self.runner.current_strategy
            name = strat.name if strat else ""
            self.status_label.setText(self._t("подключено"))
            self.tray.set_state("running", name or "работает")
            if hasattr(self, "run_field"):
                self.run_field.setText(name or "\u2014")
            self._set_power_state(True)
        else:
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
