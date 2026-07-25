"""Launch and stop the zapret engine (winws.exe).

Guarantees a single running engine at a time, captures output for the log
view, reports the exit code when winws stops on its own, and cleans up stray
winws processes on stop.
"""
from __future__ import annotations

import collections
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Deque, List, Optional

from .strategy_manager import Strategy

IS_WINDOWS = sys.platform.startswith("win")
# CREATE_NO_WINDOW keeps the console hidden in the packaged app.
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


class ProcessRunner:
    """Owns the winws.exe subprocess lifecycle.

    Methods ``start`` / ``stop`` / ``is_running`` are safe to call from the GUI
    thread and the auto-selector worker thread concurrently: a single
    ``threading.Lock`` serializes the critical sections so a stop() from one
    thread can't race a start() from another (which previously could re-launch
    winws after the user asked to quit).
    """

    def __init__(
        self,
        winws_path: Path,
        log_cb: Optional[Callable[[str], None]] = None,
        on_exit: Optional[Callable[[int, str], None]] = None,
        args_filter: Optional[Callable[[List[str]], List[str]]] = None,
    ):
        self.winws_path = Path(winws_path)
        # Optional hook to transform the strategy args right before launch
        # (used to inject per-service exclusions).
        self._args_filter = args_filter
        self._proc: Optional[subprocess.Popen] = None
        self._current: Optional[Strategy] = None
        self._log_cb = log_cb or (lambda _msg: None)
        # Called (from a worker thread) when winws exits WITHOUT us asking it to.
        self._on_exit = on_exit
        self._reader: Optional[threading.Thread] = None
        self._stopping = False
        self._tail: Deque[str] = collections.deque(maxlen=300)
        # PID of the last process we started. Tracked so stop() can kill ONLY
        # our own process tree (and not, say, the zapret Windows service).
        self._last_pid: Optional[int] = None
        # Serializes start/stop between the GUI thread and the auto-selector
        # worker. Without this, worker.start() could re-launch winws after the
        # GUI called stop() during quit.
        self._lock = threading.RLock()

    @property
    def current_strategy(self) -> Optional[Strategy]:
        with self._lock:
            return self._current

    def log(self, msg: str) -> None:
        try:
            self._log_cb(msg)
        except Exception:
            pass

    def last_output(self) -> str:
        return "\n".join(self._tail).strip()

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start(self, strategy: Strategy) -> int:
        """Stop any running engine, then start winws with this strategy.

        The whole stop+launch sequence is locked so the auto-selector worker
        can't interleave start() with a GUI-thread stop()/quit()."""
        with self._lock:
            self._stop_locked()
            if not self.winws_path.exists():
                raise FileNotFoundError("winws.exe \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d: " + str(self.winws_path))

            self._tail.clear()
            self._stopping = False
            eff_args = list(strategy.args)
            if self._args_filter is not None:
                try:
                    eff_args = list(self._args_filter(eff_args))
                except Exception as exc:  # noqa: BLE001
                    self.log("[\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f] \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0440\u0438\u043c\u0435\u043d\u0438\u0442\u044c: " + str(exc))
            cmd: List[str] = [str(self.winws_path)] + eff_args
            self.log("[\u0417\u0430\u043f\u0443\u0441\u043a] " + strategy.name)
            self.log("[\u041a\u043e\u043c\u0430\u043d\u0434\u0430] " + " ".join(cmd))

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.winws_path.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    # winws.exe prints Russian-language diagnostic lines
                    # using the OEM console code page (typically cp866 on
                    # ru-RU Windows). Decoding as UTF-8 leaves Cyrillic
                    # garbled; we use cp866 with errors='replace' so the log
                    # stays readable on Russian Windows and never crashes on
                    # an unexpected byte. Falls back to locale default on
                    # non-Windows (where the engine doesn't run anyway).
                    text=True,
                    encoding=("cp866" if IS_WINDOWS else None),
                    errors="replace",
                    creationflags=_NO_WINDOW,
                )
            except Exception as exc:  # noqa: BLE001
                self.log("[\u041e\u0448\u0438\u0431\u043a\u0430] \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c winws.exe: " + str(exc))
                raise

            self._current = strategy
            self._last_pid = self._proc.pid
            self._start_reader()
            return self._proc.pid

    def _start_reader(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return

        def _pump() -> None:
            try:
                for line in proc.stdout:  # type: ignore[union-attr]
                    line = line.rstrip()
                    if line:
                        self._tail.append(line)
                        self.log(line)
            except Exception:
                pass
            # The stream closed => the process is exiting. Capture the code.
            code = proc.poll()
            if code is None:
                try:
                    code = proc.wait(timeout=2)
                except Exception:
                    code = -1
            # Only report an *unexpected* exit: not an app-initiated stop and
            # still the current process (a new start() would have replaced it).
            if (not self._stopping) and (self._proc is proc):
                self.log("[\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u0435] winws.exe \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u043b\u0441\u044f \u0441\u0430\u043c (\u043a\u043e\u0434 " + str(code) + ")")
                cb = self._on_exit
                if cb is not None:
                    try:
                        cb(code if code is not None else -1, self.last_output())
                    except Exception:
                        pass

        self._reader = threading.Thread(target=_pump, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        """Terminate the running engine. Only kills OUR process tree; the
        broad "taskkill /IM winws.exe" sweep is no longer automatic because it
        also murders the zapret Windows service and any other instance."""
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        """Internal stop — caller must already hold self._lock."""
        self._stopping = True
        if self._proc is not None:
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
            except Exception as exc:  # noqa: BLE001
                self.log("[\u0421\u0442\u043e\u043f] \u043e\u0448\u0438\u0431\u043a\u0430: " + str(exc))
            finally:
                self._proc = None
                self._current = None
        # Kill our own PID tree as a safety net (no-op if it already exited).
        self._kill_own_tree()

    def _kill_own_tree(self) -> None:
        """Kill the PID we started (and its child processes) as a safety net.

        This is a no-op if the process already exited cleanly, which is the
        common case after `terminate()` succeeded above."""
        if not IS_WINDOWS:
            return
        pid = self._last_pid
        if not pid:
            return
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=_NO_WINDOW,
            )
        except Exception:
            pass

    def kill_all_winws(self) -> None:
        """Explicit broad sweep: kill EVERY winws.exe on the machine.

        Use this only when the user explicitly asks for a cleanup (e.g. at app
        start when recovering from a crash). Never call automatically on every
        stop() — it would silently kill the Windows service and other tools."""
        if not IS_WINDOWS:
            return
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "winws.exe", "/T"],
                capture_output=True,
                creationflags=_NO_WINDOW,
            )
        except Exception:
            pass
