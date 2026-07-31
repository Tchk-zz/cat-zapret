"""Update flows for :class:`~ui.main_window.MainWindow`.

Split out of ``ui/main_window.py`` verbatim. Two independent things live here,
both of which download something from GitHub on a worker thread:

* **zapret update** -- refreshes the bundled winws binaries, strategies and
  lists (``check_updates_async`` ... ``_on_force_update_finished``). It stops a
  running engine and the service first, because Windows keeps replaced files
  locked, and restarts them only after a clearly successful update.
* **application self-update** -- checks for a newer Zapret GUI installer and
  runs it (``_check_app_update_silent`` ... ``_on_app_download_finished``).

The two flows deliberately use separate thread/worker slots so a zapret update
and an installer download can never clobber each other's state:
``_update_thread`` / ``_update_worker`` versus ``_app_update_thread`` /
``_app_update_worker``. Both are initialised in ``MainWindow.__init__`` and
joined in ``_cancel_and_join_workers`` on shutdown.

Success and failure are told apart by the message prefix the workers return
("Обновлено до ..." versus "Ошибка" / "Не удалось" / partial-update warnings),
so those prefixes are part of the contract with ui/workers.py.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QMessageBox

from .workers import (
    AppSelfUpdateDownloadWorker,
    AppSelfUpdateWorker,
    UpdateApplyWorker,
    UpdateCheckWorker,
)


class UpdateFlowMixin:
    """Check for, download and apply zapret and application updates."""

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
        self.progress_label.setText(self._t("Обновление zapret..."))
        self._set_busy(True)
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
        self._log("[обновление] " + msg)
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
                self._log("[обновление] zapret перезапущен после обновления")
            except Exception as exc:  # noqa: BLE001
                self._log("[обновление] не удалось перезапустить zapret: " + str(exc))
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

    # --------------------------------------------------- app self-update
    def _check_app_update_silent(self) -> None:
        """Called automatically on launch -- does not pop up if already up to date."""
        self.check_app_update_async(silent=True)

    def check_app_update_async(self, silent: bool = False) -> None:
        """Check GitHub for a newer Zapret GUI installer (non-blocking).

        If *silent* is True, nothing is shown when already up to date
        (used for the auto-check on launch).
        """
        if getattr(self, "_app_update_thread", None) is not None:
            return
        worker = AppSelfUpdateWorker()
        thread = QThread(self)
        self._app_update_thread = thread
        self._app_update_worker = worker
        self._app_update_silent = silent
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_app_update_checked)
        thread.start()

    def _on_app_update_checked(self, result) -> None:
        if self._app_update_thread is not None:
            self._app_update_thread.quit()
            self._app_update_thread.wait()
            self._app_update_thread = None

        silent = getattr(self, "_app_update_silent", False)

        # The worker sends (status, release). Older call sites may still pass a
        # bare release object or None, so accept both shapes.
        if isinstance(result, tuple):
            status, release = result
        else:
            status, release = ("uptodate" if result is None else "update"), result

        if status == "error":
            # Do not stay silent on a failed check -- that looked like the
            # "Обновить приложение" button was broken.
            self._log("[обновление] не удалось проверить обновления Zapret GUI")
            if not silent:
                QMessageBox.warning(
                    self,
                    self._msg_title("Обновление приложения"),
                    self._msg_text(
                        "Не удалось проверить обновления.\n\n"
                        "Возможно, нет интернета или GitHub временно недоступен. "
                        "Попробуйте ещё раз позже."
                    ),
                )
            return

        if release is None:
            # No newer version found
            if not silent:
                from app.self_updater import local_version
                cur = local_version() or "?"
                QMessageBox.information(
                    self,
                    self._msg_title("Обновление приложения"),
                    self._msg_text(
                        f"\u0423 \u0432\u0430\u0441 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u0432\u0435\u0440\u0441\u0438\u044f Zapret GUI \u2014 {cur}.\n\n"
                        "\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043d\u0435 \u0442\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f."
                    ),
                )
            return

        # Newer version available
        from app.self_updater import local_version
        cur = local_version() or "?"
        ans = QMessageBox.question(
            self,
            self._msg_title("\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f"),
            self._msg_text(
                f"\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u043d\u043e\u0432\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f Zapret GUI: {release.tag}\n"
                f"\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043d\u0430\u044f: {cur}\n\n"
                "\u0421\u043a\u0430\u0447\u0430\u0442\u044c \u0438 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0449\u0438\u043a?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._app_download_and_launch(release)

    def _app_download_and_launch(self, release) -> None:
        """Download the installer in a worker thread and launch it."""
        if getattr(self, "_app_update_thread", None) is not None:
            return
        worker = AppSelfUpdateDownloadWorker(release)
        thread = QThread(self)
        self._app_update_thread = thread
        self._app_update_worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._append_log)
        worker.percent.connect(self._on_app_download_percent)
        worker.finished.connect(self._on_app_download_finished)
        self.progress.setVisible(True)
        # Real 0-100 progress: the worker reports actual bytes downloaded
        # instead of an indeterminate bar that told the user nothing.
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_label.setText("\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f...")
        thread.start()

    def _on_app_download_percent(self, pct: int) -> None:
        """Update the progress bar and caption as the installer downloads."""
        self.progress.setValue(pct)
        self.progress_label.setText(
            "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f... {}%".format(pct)
        )

    def _on_app_download_finished(self, msg: str) -> None:
        if self._app_update_thread is not None:
            self._app_update_thread.quit()
            self._app_update_thread.wait()
            self._app_update_thread = None
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        if msg == "cancelled":
            # The user closed the app mid-download; no dialog to show.
            return
        if msg == "ok":
            QMessageBox.information(
                self,
                self._msg_title("\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f"),
                self._msg_text(
                    "\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u0449\u0438\u043a \u0437\u0430\u043f\u0443\u0449\u0435\u043d. \u041f\u0440\u043e\u0439\u0434\u0438\u0442\u0435 \u0448\u0430\u0433\u0438 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438 \u0432 \u043e\u0442\u043a\u0440\u044b\u0432\u0448\u0435\u043c\u0441\u044f \u043e\u043a\u043d\u0435.\n\n"
                    "\u041f\u043e\u0441\u043b\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435."
                ),
            )
        else:
            QMessageBox.warning(
                self,
                self._msg_title("\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f"),
                self._msg_text(msg),
            )
