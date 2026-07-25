"""Install / remove zapret as a Windows service.

We reuse Flowseal's own ``service.bat`` when present (it knows how to register
winws with the right WinDivert filters); otherwise we fall back to a direct
``sc create`` that launches a chosen strategy's .bat on boot.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

IS_WINDOWS = sys.platform.startswith("win")
SERVICE_NAME = "zapret"
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


class ServiceManager:
    # Status queries are cached for this long so the 2-second status timer
    # doesn't spawn `sc.exe` every tick (which causes noticeable UI lag on
    # domain-joined / slow machines).
    _STATUS_TTL = 15.0  # seconds

    def __init__(self, zapret_dir: Path):
        self.zapret_dir = Path(zapret_dir)
        self._status_cache: Optional[str] = None  # "installed" / "running" / "stopped" / "absent"
        self._status_cached_at: float = 0.0

    # --- helpers -----------------------------------------------------------
    def _service_bat(self) -> Optional[Path]:
        p = self.zapret_dir / "service.bat"
        return p if p.exists() else None

    def _run(self, args, **kw) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_NO_WINDOW,
            **kw,
        )

    def _refresh_status(self) -> str:
        """Query `sc` once and cache the result for `_STATUS_TTL` seconds."""
        import time as _time

        now = _time.monotonic()
        if self._status_cache is not None and (now - self._status_cached_at) < self._STATUS_TTL:
            return self._status_cache
        if not IS_WINDOWS:
            self._status_cache = "absent"
        else:
            res = self._run(["sc", "query", SERVICE_NAME])
            out = (res.stdout or "")
            if "SERVICE_NAME" not in out and res.returncode != 0:
                self._status_cache = "absent"
            elif "RUNNING" in out:
                self._status_cache = "running"
            else:
                self._status_cache = "stopped"
        self._status_cached_at = now
        return self._status_cache

    def invalidate_status(self) -> None:
        """Force the next status query to actually hit `sc` (after install/remove)."""
        self._status_cache = None
        self._status_cached_at = 0.0

    # --- status ------------------------------------------------------------
    def is_installed(self) -> bool:
        return self._refresh_status() != "absent"

    def is_running(self) -> bool:
        return self._refresh_status() == "running"

    def status_text(self) -> str:
        state = self._refresh_status()
        if state == "absent":
            return "\u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430" if IS_WINDOWS else "\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0442\u043e\u043b\u044c\u043a\u043e \u0432 Windows"
        return "\u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442" if state == "running" else "\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430"

    # --- install / remove --------------------------------------------------
    def install(self, strategy=None, on_pre_start=None) -> str:
        """Install zapret as an autostart Windows service running winws.exe.

        We no longer ship Flowseal's service.bat (all .bat are deleted after
        conversion), so we register winws.exe with the selected strategy's
        arguments directly via ``sc create``.

        ``on_pre_start`` is an optional callback invoked BEFORE ``sc start``.
        The GUI uses it to stop its own running winws.exe so the service's
        winws can grab WinDivert without a conflict. Without this, the service
        starts, fails to open WinDivert (already held by the GUI), and exits
        with error 1060 — leaving the user with a "service installed but
        stopped" state.
        """
        if not IS_WINDOWS:
            return "\u0421\u043b\u0443\u0436\u0431\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u0432 Windows."
        sbat = self._service_bat()
        if sbat is not None:
            if on_pre_start is not None:
                try:
                    on_pre_start()
                except Exception:
                    pass
            res = self._run(["cmd", "/c", str(sbat), "install"], cwd=str(self.zapret_dir))
            self.invalidate_status()
            return (res.stdout or "") + (res.stderr or "") or "\u0421\u043b\u0443\u0436\u0431\u0430 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430."
        # Normal case: no service.bat. Register winws.exe + the strategy args.
        winws = self.zapret_dir / "bin" / "winws.exe"
        if not winws.exists():
            return "\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d winws.exe \u0434\u043b\u044f \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438 \u0441\u043b\u0443\u0436\u0431\u044b."
        args = list(getattr(strategy, "args", None) or [])
        if not args:
            return "\u041d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u0430 \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f \u0434\u043b\u044f \u0441\u043b\u0443\u0436\u0431\u044b."
        # Build the binPath for `sc create`. The whole thing must be ONE
        # argument (sc.exe parses binPath= as a single token up to the next
        # "key=" pair), with the exe path quoted in case it contains spaces
        # (e.g. C:\Program Files\ZapretGUI\...). Strategy args normally don't
        # contain spaces because they were tokenized from a .bat, but if any
        # do (e.g. a custom hostlist path with a space), wrap them in quotes.
        # Bare backslashes are fine — sc.exe doesn't process them specially.
        def _quote_if_needed(tok: str) -> str:
            if " " in tok and not (tok.startswith('"') and tok.endswith('"')):
                return '"' + tok + '"'
            return tok

        bin_path = '"' + str(winws) + '" ' + " ".join(_quote_if_needed(a) for a in args)
        # Replace any previous registration so a new strategy takes effect.
        self._run(["sc", "stop", SERVICE_NAME])
        self._run(["sc", "delete", SERVICE_NAME])
        res = self._run([
            "sc", "create", SERVICE_NAME,
            "binPath=", bin_path,
            "start=", "auto",
            "DisplayName=", "Zapret DPI bypass",
        ])
        out = (res.stdout or "") + (res.stderr or "")
        # Stop the GUI's own winws BEFORE the service tries to start, so the
        # service's winws can grab WinDivert without a conflict.
        if on_pre_start is not None:
            try:
                on_pre_start()
            except Exception:
                pass
        start = self._run(["sc", "start", SERVICE_NAME])
        out += (start.stdout or "") + (start.stderr or "")
        self.invalidate_status()
        return out or "\u0421\u043b\u0443\u0436\u0431\u0430 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430."

    def start(self) -> str:
        """Start the already installed zapret service."""
        if not IS_WINDOWS:
            return "Служба доступна только в Windows."
        sbat = self._service_bat()
        if sbat is not None:
            res = self._run(["cmd", "/c", str(sbat), "start"], cwd=str(self.zapret_dir))
            self.invalidate_status()
            return (res.stdout or "") + (res.stderr or "") or "Служба запущена."
        res = self._run(["sc", "start", SERVICE_NAME])
        self.invalidate_status()
        return (res.stdout or "") + (res.stderr or "") or "Служба запущена."

    def stop(self) -> str:
        """Stop the running service (without removing it)."""
        if not IS_WINDOWS:
            return "\u0421\u043b\u0443\u0436\u0431\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u0432 Windows."
        sbat = self._service_bat()
        if sbat is not None:
            res = self._run(["cmd", "/c", str(sbat), "stop"], cwd=str(self.zapret_dir))
            out = (res.stdout or "") + (res.stderr or "")
            if out.strip():
                self.invalidate_status()
                return out
        res = self._run(["sc", "stop", SERVICE_NAME])
        self.invalidate_status()
        return (res.stdout or "") + (res.stderr or "") or "\u0421\u043b\u0443\u0436\u0431\u0430 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430."

    def remove(self) -> str:
        if not IS_WINDOWS:
            return "\u0421\u043b\u0443\u0436\u0431\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u0432 Windows."
        sbat = self._service_bat()
        if sbat is not None:
            res = self._run(["cmd", "/c", str(sbat), "remove"], cwd=str(self.zapret_dir))
            self.invalidate_status()
            return (res.stdout or "") + (res.stderr or "") or "\u0421\u043b\u0443\u0436\u0431\u0430 \u0443\u0434\u0430\u043b\u0435\u043d\u0430."
        self._run(["sc", "stop", SERVICE_NAME])
        res = self._run(["sc", "delete", SERVICE_NAME])
        self.invalidate_status()
        return (res.stdout or "") + (res.stderr or "")
