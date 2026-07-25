"""Launch the GUI together with Windows.

Two mechanisms are supported:

  1. Per-user Run registry key  -- simple, but causes a UAC prompt at every
     logon because the app requires admin rights (WinDivert).
  2. Task Scheduler with /RL HIGHEST -- runs elevated with NO UAC prompt at
     logon. This is the DEFAULT since the app already requires admin.

The public ``enable`` / ``disable`` / ``is_enabled`` API uses whichever
mechanism is currently active. The legacy registry helpers are kept as
``enable_run`` / ``disable_run`` for migration / fallback.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE = "ZapretGUI"
TASK_NAME = "ZapretGUI_Autostart"
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def _exe_command(minimized: bool) -> str:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        cmd = f'"{exe}"'
    else:
        script = str(Path(__file__).resolve().parent.parent / "main.py")
        cmd = f'"{exe}" "{script}"'
    if minimized:
        cmd += " --minimized"
    return cmd


def _task_exists() -> bool:
    """True if the autostart scheduled task is registered."""
    if not IS_WINDOWS:
        return False
    res = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        creationflags=_NO_WINDOW,
    )
    return res.returncode == 0


# --- public API: task scheduler preferred (no UAC at logon) ----------------
def is_enabled() -> bool:
    """True if EITHER the scheduled task OR the legacy Run key is set."""
    if not IS_WINDOWS:
        return False
    if _task_exists():
        return True
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_VALUE)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable(minimized: bool = False) -> None:
    """Enable autostart. Uses the elevated scheduled task by default so the
    user does NOT get a UAC prompt at every logon. Also removes any stale
    Run-key entry to avoid double-launching."""
    if not IS_WINDOWS:
        return
    # Create the elevated task. Falls back to the Run key on failure.
    res = subprocess.run(
        [
            "schtasks", "/Create", "/TN", TASK_NAME,
            "/TR", _exe_command(minimized),
            "/SC", "ONLOGON", "/RL", "HIGHEST", "/F",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        creationflags=_NO_WINDOW,
    )
    if res.returncode != 0:
        # Could not create the task (e.g. Task Scheduler disabled). Fall back
        # to the Run key — user will get a UAC prompt, but autostart at least
        # works.
        enable_run(minimized)


def disable() -> None:
    """Disable autostart: remove BOTH the scheduled task and the Run key."""
    if not IS_WINDOWS:
        return
    # Best-effort: ignore errors if either doesn't exist.
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        creationflags=_NO_WINDOW,
    )
    disable_run()


# --- legacy registry helpers (kept for migration / fallback) ---------------
def enable_run(minimized: bool = False) -> None:
    if not IS_WINDOWS:
        return
    import winreg  # type: ignore

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, APP_VALUE, 0, winreg.REG_SZ, _exe_command(minimized))


def disable_run() -> None:
    if not IS_WINDOWS:
        return
    import winreg  # type: ignore

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_VALUE)
    except FileNotFoundError:
        pass
    except OSError:
        pass


# --- Backwards-compat aliases (old public names) ---------------------------
enable_task = enable
disable_task = disable
