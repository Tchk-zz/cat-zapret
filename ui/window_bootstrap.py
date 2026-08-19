"""First-run bootstrap of the bundled zapret files."""
from __future__ import annotations

from PyQt6.QtCore import QThread

from app import bootstrap
from app.service_manager import ServiceManager
from app.strategy_manager import StrategyManager

from .widgets_custom import StyledPopup
from .workers import BootstrapWorker


class BootstrapMixin:
    """Downloading/unpacking zapret and the autostart-on-launch flow."""

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
                "Не удалось подготовить zapret",
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
