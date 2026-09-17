"""Launch the built GUI briefly in an isolated profile, then terminate it.

Run after PyInstaller: python tools/smoke_built_exe.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "ZapretGUI.exe"


def main() -> int:
    if not EXE.is_file():
        raise SystemExit(f"Missing build artifact: {EXE}")
    profile = Path(tempfile.mkdtemp(prefix="cat-zapret-exe-smoke-"))
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(profile / "Local")
    env["APPDATA"] = str(profile / "Roaming")
    proc = subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env)
    try:
        time.sleep(15)
        if proc.poll() is not None:
            raise SystemExit(f"ZapretGUI exited early with code {proc.returncode}")
        print(f"ZapretGUI stayed alive for 15s (pid={proc.pid})")
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
