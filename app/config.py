"""Persistent JSON configuration for Zapret GUI.

Stores user preferences and the last known working strategy so the app can
start instantly next time. Settings live in the per-user data directory
(``%LOCALAPPDATA%\\ZapretGUI\\config.json``); a legacy file next to the
executable is migrated automatically on first run.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def app_dir() -> Path:
    """Directory of the running app (works for both .py and frozen .exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    """Writable per-user data dir (survives reinstalls, no admin needed)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "ZapretGUI"
    return app_dir() / "data"


def config_path() -> Path:
    return default_data_dir() / "config.json"


@dataclass
class AppConfig:
    # Path to the unpacked zapret-discord-youtube folder. If empty, the app
    # auto-detects it next to the executable.
    zapret_dir: str = ""
    # Name of the last strategy that successfully passed connectivity checks.
    last_working_strategy: str = ""
    # Start the last working strategy automatically on launch.
    autostart_strategy: bool = False
    # Launch the GUI together with Windows.
    autostart_with_windows: bool = False
    # Start minimized to the system tray.
    start_minimized: bool = False
    # Minimize to tray instead of quitting when the window is closed.
    minimize_to_tray: bool = True
    # Check Flowseal GitHub releases for newer strategies on launch.
    check_updates_on_launch: bool = True
    # Refresh upstream zapret list/ipset/hosts template files automatically.
    auto_update_lists: bool = True
    # Minimum interval between automatic list refreshes.
    list_update_interval_hours: int = 24
    # Unix timestamp of the last successful list refresh.
    last_lists_update: int = 0
    # Per-service timeout (seconds) used by connectivity checks.
    connectivity_timeout: float = 6.0
    # Seconds to wait after starting winws before testing connectivity.
    warmup_seconds: float = 3.0
    # --- deep auto-select checks ---
    # Duration (s) of the sustained freeze/throughput test in "best" mode.
    deep_freeze_seconds: float = 16.0
    # Shorter freeze test used by the fast "working" mode.
    working_freeze_seconds: float = 6.0
    # How many repeated probes to gauge stability (best mode).
    deep_attempts: int = 3
    # Seconds without data mid-stream that counts as a freeze.
    stall_timeout: float = 4.0
    # Check Discord voice (signaling + UDP/STUN) as part of the score.
    enable_voice_check: bool = True
    # Ordered list of strategy names tried first during auto-select.
    preferred_order: List[str] = field(default_factory=list)
    # Enabled exclusion preset ids (services zapret should NOT touch).
    excluded_presets: List[str] = field(default_factory=list)
    # "Apply bypass" selections -> written to lists/list-general-user.txt
    include_presets: List[str] = field(default_factory=list)
    include_custom: List[str] = field(default_factory=list)
    # "Do not touch" selections -> written to lists/list-exclude-user.txt
    exclude_presets: List[str] = field(default_factory=list)
    exclude_custom: List[str] = field(default_factory=list)
    # Experimental: apply DPI-desync to game ports too (Flowseal game filter).
    game_filter_enabled: bool = False
    # Merge the Roblox bypass profile into the selected strategy when enabled.
    roblox_combine: bool = False
    # Interface language: "ru" or "en".
    language: str = "ru"
    # Visual theme: "purple", "light" or "dark". Dark is a Windows 11-like neutral theme.
    theme: str = "purple"
    # --- Telegram MTProto proxy (Flowseal/tg-ws-proxy) ---
    # Whether the user has enabled the TG proxy in the GUI. We persist it so
    # the toggle stays in sync across restarts.
    tg_proxy_enabled: bool = False
    # Auto-start the TG proxy whenever zapret starts. Convenience for users
    # who always want both bypasses active together.
    tg_proxy_autostart_with_zapret: bool = False
    # Optional user-specified DC IP overrides for the tg-ws-proxy engine.
    # Empty list = do NOT force DC->IP overrides. This intentionally matches
    # tg-ws-proxy v1.8.x guidance: if fronting/WS timeouts happen, clearing
    # DC->IP lets the engine use its fallback chain instead of a stale IP.
    tg_proxy_dc_ips: List[str] = field(default_factory=list)
    # Optional custom Cloudflare Proxy / Worker domains for advanced users.
    # Empty = use tg-ws-proxy automatic/default CF proxy domain list; only fill
    # these when the upstream project or user specifically provides domains.
    tg_proxy_cfproxy_domains: List[str] = field(default_factory=list)
    tg_proxy_cfworker_domains: List[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "AppConfig":
        path = config_path()
        if not path.exists():
            legacy = app_dir() / "config.json"
            if legacy.exists():
                path = legacy
            else:
                return cls()
        try:
            data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)

    def save(self) -> None:
        try:
            config_path().parent.mkdir(parents=True, exist_ok=True)
            config_path().write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def resolve_zapret_dir(self) -> Optional[Path]:
        """Return the zapret folder, auto-detecting it if not configured."""
        if self.zapret_dir:
            p = Path(self.zapret_dir)
            if p.exists():
                return p
        return _autodetect_zapret_dir()

    def managed_zapret_dir(self) -> Path:
        """Folder the app uses for zapret; downloaded on first run if absent.

        Uses the configured folder if set, an existing detected install if
        present, otherwise a managed folder under the user's data dir.
        """
        if self.zapret_dir:
            p = Path(self.zapret_dir)
            # Honor an explicitly chosen folder only if it actually holds an
            # install. This prevents a stale/empty saved path (e.g. an old
            # C:\zapret from a previous version) from trapping the app and
            # blocking auto-connect to our own managed folder.
            try:
                if (p / "bin" / "winws.exe").exists():
                    return p
            except OSError:
                pass
        # Self-contained by default: use our own managed folder and never
        # depend on a zapret install the user may have elsewhere on the PC.
        return default_data_dir() / "zapret"


def _autodetect_zapret_dir() -> Optional[Path]:
    """Look for a zapret install near the app.

    A valid folder contains a ``bin`` directory with ``winws.exe`` and at
    least one ``general*.bat`` strategy file.
    """
    base = app_dir()
    candidates = [base, base.parent]
    # Common sibling folder names produced by the Flowseal archive.
    for name in (
        "zapret-discord-youtube",
        "zapret",
        "zapret-discord-youtube-main",
    ):
        candidates.append(base / name)
        candidates.append(base.parent / name)
    for c in candidates:
        try:
            if (c / "bin" / "winws.exe").exists():
                return c
        except OSError:
            continue
    return None
