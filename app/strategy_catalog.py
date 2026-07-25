"""Own strategy catalog: convert Flowseal .bat recipes into a portable JSON.

Instead of parsing third-party batch files every time, we extract their
winws.exe arguments once into a single ``strategies.json`` catalog with
portable placeholders (%BIN%, %LISTS%, %ZAPRET%, %GAMEFILTER*%). The app then
loads strategies from this catalog -- our own schemas, derived from Flowseal's
batches but decoupled from them. The catalog is regenerated from the installed
.bat files on demand (e.g. after a Flowseal update or via "Refresh list").
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .strategy_manager import (
    _EXCLUDE,
    Strategy,
    expand_portable_args,
    parse_bat,
)

CATALOG_VERSION = 1
CATALOG_FILENAME = "strategies.json"


def catalog_path(zapret_dir: Path) -> Path:
    return Path(zapret_dir) / CATALOG_FILENAME


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "strategy"


def _classify_services(name: str, args: List[str]) -> List[str]:
    low = name.lower()
    joined = " ".join(args).lower()
    services: List[str] = []
    if low.startswith("discord") or "discord" in joined:
        services.append("discord")
    if low.startswith("youtube") or "youtube" in low or "googlevideo" in joined:
        services.append("youtube")
    if low.startswith("general") or not services:
        # General strategies target everything.
        services = ["discord", "youtube"]
    return list(dict.fromkeys(services))


def build_catalog(zapret_dir: Path) -> Dict:
    """Parse every Flowseal .bat into portable catalog entries."""
    zapret_dir = Path(zapret_dir)
    entries: List[Dict] = []
    seen_ids = set()
    for bat in sorted(zapret_dir.glob("*.bat")):
        if bat.name.lower() in _EXCLUDE:
            continue
        strat = parse_bat(bat, zapret_dir, portable=True)
        if strat is None:
            continue
        sid = _slug(strat.name)
        base = sid
        n = 2
        while sid in seen_ids:
            sid = f"{base}-{n}"
            n += 1
        seen_ids.add(sid)
        entries.append(
            {
                "id": sid,
                "name": strat.name,
                "description": strat.description,
                "services": _classify_services(strat.name, strat.args),
                "args": list(strat.args),
                "source": bat.name,
            }
        )
    return {
        "version": CATALOG_VERSION,
        "source": "Flowseal/zapret-discord-youtube",
        "generated_at": int(time.time()),
        "strategies": entries,
    }


def write_catalog(zapret_dir: Path, catalog: Dict) -> Path:
    path = catalog_path(zapret_dir)
    path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def seed_catalog_path() -> Optional[Path]:
    """Locate the prebuilt strategies.json shipped inside the app, if any.

    This seed is generated at build time from Flowseal's .bat recipes so the
    strategy list is available immediately on first launch -- even before the
    bin/lists are downloaded. When frozen by PyInstaller it sits next to the
    extracted data (sys._MEIPASS); from source it lives in vendor/.
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / CATALOG_FILENAME)
        candidates.append(Path(meipass) / "vendor" / CATALOG_FILENAME)
    root = Path(__file__).resolve().parent.parent
    candidates.append(root / "vendor" / CATALOG_FILENAME)
    candidates.append(root / CATALOG_FILENAME)
    for c in candidates:
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None


def delete_bat_files(zapret_dir: Path) -> int:
    """Delete every *.bat in the zapret root. Returns how many were removed.

    Once a .bat has been converted into our catalog it is foreign clutter we no
    longer need -- the app launches winws.exe straight from the catalog args.
    """
    zapret_dir = Path(zapret_dir)
    removed = 0
    try:
        bats = list(zapret_dir.glob("*.bat"))
    except OSError:
        return 0
    for bat in bats:
        try:
            bat.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def rebuild_from_bats(zapret_dir: Path, delete_bats: bool = True) -> int:
    """Convert the Flowseal .bat recipes into our catalog, then drop the .bat.

    Returns the number of strategies written. If nothing parsed (no .bat / no
    winws lines) the existing catalog and files are left untouched.
    """
    zapret_dir = Path(zapret_dir)
    cat = build_catalog(zapret_dir)
    strategies = cat.get("strategies") or []
    if not strategies:
        return 0
    write_catalog(zapret_dir, cat)
    if delete_bats:
        delete_bat_files(zapret_dir)
    return len(strategies)


def ensure_catalog(zapret_dir: Path) -> Path:
    """Guarantee a runtime catalog exists -- WITHOUT parsing .bat every launch.

    Priority:
      1. An existing runtime strategies.json -> use as-is (normal case).
      2. Foreign .bat still present (fresh download) -> convert once, delete .bat.
      3. The prebuilt seed bundled with the app -> copy it in.
    """
    zapret_dir = Path(zapret_dir)
    path = catalog_path(zapret_dir)
    if path.exists():
        return path
    try:
        if any(zapret_dir.glob("*.bat")):
            if rebuild_from_bats(zapret_dir, delete_bats=True) > 0:
                return path
    except OSError:
        pass
    seed = seed_catalog_path()
    if seed is not None:
        try:
            zapret_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seed, path)
        except OSError:
            pass
    return path


def load_catalog(zapret_dir: Path) -> List[Strategy]:
    """Load catalog strategies, resolving portable placeholders to real paths."""
    zapret_dir = Path(zapret_dir)
    path = catalog_path(zapret_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[Strategy] = []
    for entry in data.get("strategies", []):
        raw = entry.get("args") or []
        if isinstance(raw, str):
            raw = raw.split()
        args = expand_portable_args(list(raw), zapret_dir)
        if not args:
            continue
        out.append(
            Strategy(
                name=entry.get("name", entry.get("id", "strategy")),
                source_file=path,
                args=args,
                description=entry.get("description", ""),
                custom=False,
            )
        )
    return out
