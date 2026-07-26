"""Qt worker objects that run blocking tasks off the UI thread."""
from __future__ import annotations

import threading
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.auto_selector import AutoSelectResult, AutoSelector
from app.strategy_manager import Strategy


class AutoSelectWorker(QObject):
    """Runs AutoSelector.run() in a QThread and emits progress/results."""

    progress = pyqtSignal(int, int, str, str)  # index, total, name, phase
    log = pyqtSignal(str)
    finished = pyqtSignal(object)  # AutoSelectResult

    def __init__(
        self,
        selector: AutoSelector,
        strategies: List[Strategy],
        mode: str = "working",
        last_working: Optional[str] = None,
        preferred_order: Optional[List[str]] = None,
    ):
        super().__init__()
        self._selector = selector
        self._strategies = strategies
        self._mode = mode
        # Hints that let the selector try the most likely winner first.
        self._last_working = last_working
        self._preferred_order = preferred_order

    def run(self) -> None:
        def on_progress(idx: int, total: int, strat: Strategy, phase: str) -> None:
            self.progress.emit(idx, total, strat.name, phase)

        result: AutoSelectResult = self._selector.run(
            self._strategies,
            on_progress,
            self._mode,
            last_working=self._last_working,
            preferred_order=self._preferred_order,
        )
        self.finished.emit(result)

    def cancel(self) -> None:
        self._selector.cancel()


class UpdateCheckWorker(QObject):
    """Checks GitHub for a newer strategy release."""

    finished = pyqtSignal(object)  # ReleaseInfo or None

    def __init__(self, zapret_dir):
        super().__init__()
        self._zapret_dir = zapret_dir

    def run(self) -> None:
        from app import updater

        rel = updater.update_available(self._zapret_dir)
        self.finished.emit(rel)


class CheckWorker(QObject):
    """Runs a one-off connectivity check off the UI thread."""

    finished = pyqtSignal(object)  # CheckResult

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def run(self) -> None:
        from app.connectivity import check

        self.finished.emit(check(self._timeout))


class BootstrapWorker(QObject):
    """Downloads the Flowseal zapret bundle on first run, off the UI thread."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(str)  # "ok" or an error message

    def __init__(self, zapret_dir):
        super().__init__()
        self._zapret_dir = zapret_dir

    def run(self) -> None:
        from app import bootstrap

        msg = bootstrap.ensure_zapret(
            self._zapret_dir, progress_cb=lambda m: self.progress.emit(m)
        )
        self.finished.emit(msg)


class UpdateApplyWorker(QObject):
    """Downloads the latest Flowseal release and applies it off the UI thread.

    After extraction the updater converts the new .bat into our catalog and
    deletes the .bat, so the engine keeps running straight from the catalog.
    """

    progress = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, zapret_dir, release=None):
        super().__init__()
        self._zapret_dir = zapret_dir
        self._release = release

    def run(self) -> None:
        # Anything that escapes here would crash the whole PyQt6 app, so we
        # always turn failures into a finished() message instead.
        try:
            from app import updater

            if self._release is not None:
                rel = self._release
            else:
                rel = updater.latest_release()
                if rel is None:
                    self.finished.emit("Не удалось получить релиз с GitHub. Проверьте интернет.")
                    return
                cur = updater._norm(updater.local_version(self._zapret_dir))
                if cur and updater._norm(rel.tag) == cur:
                    self.finished.emit("Установлена последняя версия zapret (" + rel.tag + "). Обновление не требуется.")
                    return
            if rel is None:
                self.finished.emit("Не удалось получить релиз с GitHub. Проверьте интернет.")
                return
            msg = updater.download_and_apply(
                rel, self._zapret_dir, on_status=lambda m: self.progress.emit(m)
            )
            self.finished.emit(msg)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit("\u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f: " + str(exc))


class ListUpdateWorker(QObject):
    """Refresh upstream zapret list/ipset/hosts-template files off the UI thread."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # app.list_manager.ListUpdateResult

    def __init__(self, zapret_dir):
        super().__init__()
        self._zapret_dir = zapret_dir

    def run(self) -> None:
        try:
            from app import list_manager

            res = list_manager.update_zapret_lists(
                self._zapret_dir, progress_cb=lambda m: self.progress.emit(m)
            )
        except Exception as exc:  # noqa: BLE001
            from app.list_manager import ListUpdateResult
            res = ListUpdateResult(False, message="Ошибка обновления списков: " + str(exc))
        self.finished.emit(res)


class TGProxyUpdateWorker(QObject):
    """Checks and optionally applies upstream tg-ws-proxy updates."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # app.tg_proxy.TGProxyUpdateResult

    def __init__(self, data_dir, apply_update: bool = False):
        super().__init__()
        self._data_dir = data_dir
        self._apply_update = bool(apply_update)

    def run(self) -> None:
        from app import tg_proxy

        try:
            res = tg_proxy.check_and_update(
                self._data_dir,
                apply_update=self._apply_update,
                progress_cb=lambda m: self.progress.emit(m),
            )
        except Exception as exc:  # noqa: BLE001
            res = tg_proxy.TGProxyUpdateResult(
                False, "error", "Ошибка обновления tg-ws-proxy: " + str(exc)
            )
        self.finished.emit(res)


class AppSelfUpdateWorker(QObject):
    """Checks our own GitHub releases for a newer Zapret GUI installer.

    Emits a ``(status, release)`` pair so the window can tell "you are up to
    date" apart from "the check failed". Previously both cases arrived as
    ``None`` and a failed check looked like the button did nothing.
    """

    finished = pyqtSignal(object)  # (status, AppRelease|None)

    def run(self) -> None:
        from app import self_updater
        try:
            self.finished.emit(self_updater.check_update())
        except Exception:  # noqa: BLE001
            self.finished.emit(("error", None))


class AppSelfUpdateDownloadWorker(QObject):
    """Downloads the Zapret GUI installer and launches it.

    Emits ``percent`` so the UI can show a real progress bar instead of an
    indeterminate one, and supports cancellation via :meth:`cancel` (used
    when the main window closes mid-download).
    """

    progress = pyqtSignal(str)
    percent = pyqtSignal(int)    # 0-100 download completion
    finished = pyqtSignal(str)   # "ok", "cancelled" or error message

    def __init__(self, release):
        super().__init__()
        self._release = release
        # threading.Event is safe to set from the UI thread while the worker
        # thread reads it inside the download loop.
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Ask the running download to stop as soon as possible."""
        self._cancel.set()

    def run(self) -> None:
        try:
            from app import self_updater
            msg = self_updater.download_and_launch(
                self._release,
                on_status=lambda m: self.progress.emit(m),
                on_progress=lambda p: self.percent.emit(p),
                should_cancel=self._cancel.is_set,
            )
            self.finished.emit(msg)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit("Ошибка: " + str(exc))
