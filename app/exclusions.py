"""Manage zapret per-user domain lists from the GUI.

Flowseal strategies already reference two editable per-user lists, so we don't
need to inject anything into winws \u2014 we just write into these files:

  * ``lists/list-general-user.txt``  -> domains the bypass IS applied to (include)
  * ``lists/list-exclude-user.txt``  -> domains the bypass must NOT touch (exclude)

We expose curated service presets plus free-form domains and write them into a
clearly delimited "managed block" inside each file, preserving anything else
the user (or Flowseal) put there. Matching is suffix-based, so a base domain
like ``riotgames.com`` also covers all of its subdomains.

Changes take effect the next time winws starts (the engine reads these files on
launch), so the GUI restarts a running engine after editing them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Set

INCLUDE_FILE = "list-general-user.txt"
EXCLUDE_FILE = "list-exclude-user.txt"

_BEGIN = "# >>> ZapretGUI managed block (edit in the app) >>>"
_END = "# <<< ZapretGUI managed block <<<"
# winws aborts on an empty list file, so keep a harmless non-matching domain.
_PLACEHOLDER = "domain.example.abc"


@dataclass
class ServicePreset:
    id: str
    name: str
    description: str
    domains: List[str] = field(default_factory=list)


# Curated services. Extend freely — each one shows up as a checkbox.
SERVICES: List[ServicePreset] = [
    ServicePreset(
        "riot",
        "Valorant / Riot Games",
        "Valorant, League of Legends, Riot клиент, логин и сервера Riot.",
        [
            "riotgames.com",
            "riotcdn.net",
            "riotgames.co",
            "playvalorant.com",
            "valorant.com",
            "leagueoflegends.com",
            "lolesports.com",
            "pvp.net",
        ],
    ),
    ServicePreset(
        "steam",
        "Steam",
        "Магазин, клиент и контент Steam / Valve.",
        [
            "steampowered.com",
            "steamcommunity.com",
            "steamstatic.com",
            "steamcontent.com",
            "steamgames.com",
            "steamserver.net",
            "valvesoftware.com",
        ],
    ),
    ServicePreset(
        "epic",
        "Epic Games",
        "Epic Games Store, лаунчер, Fortnite.",
        [
            "epicgames.com",
            "epicgames.dev",
            "unrealengine.com",
            "fortnite.com",
        ],
    ),
    ServicePreset(
        "battlenet",
        "Battle.net / Blizzard",
        "Blizzard клиент и игры (WoW, Diablo, Overwatch).",
        [
            "battle.net",
            "blizzard.com",
            "battlenet.com.cn",
            "blzstatic.cn",
        ],
    ),
    ServicePreset(
        "roblox",
        "Roblox",
        "Roblox клиент и сайт.",
        [
            "roblox.com",
            "rbxcdn.com",
            "rbxgcdn.com",
            "rbxinfra.com",
            "robloxlabs.com",
            "rbx.com",
        ],
    ),
    ServicePreset(
        "faceit",
        "FACEIT",
        "FACEIT матчмейкинг и анти-чит.",
        [
            "faceit.com",
            "faceit-cdn.net",
        ],
    ),
    ServicePreset(
        "soundcloud",
        "SoundCloud",
        "SoundCloud — музыка, подкасты, API и CDN. "
        "В РФ заблокирован по DPI на уровне SNI. "
        "Полный список доменов (API + media + CDN + новый "
        "media-streaming) добавляется в list-general-user.txt и zapret "
        "автоматически применяет обход ко всем доменам SoundCloud.",
        [
            # Main site + API
            "soundcloud.com",
            "api.soundcloud.com",
            "api-v2.soundcloud.com",
            "edge-api.soundcloud.com",
            "mobi.soundcloud.com",
            "feeds.soundcloud.com",
            "charts.soundcloud.com",
            "promote-v2.soundcloud.com",
            "developers.soundcloud.com",
            "checkout.soundcloud.com",
            "pre-pnd.soundcloud.com",
            "pnd.soundcloud.com",
            "help.soundcloud.com",
            "support.soundcloud.com",
            # Media (audio streams) — legacy soundcloud.com media subdomains
            "media.soundcloud.com",
            "assets.soundcloud.com",
            "secure-media.soundcloud.com",
            # NEW: soundcloud.cloud — SoundCloud's modern media-streaming
            # infrastructure (replaces some *.sndcdn.com endpoints as of
            # 2024-2025). Without these, audio playback silently fails even
            # when soundcloud.com itself loads.
            "soundcloud.cloud",
            "assets.web.soundcloud.cloud",
            "playback.media-streaming.soundcloud.cloud",
            "license.media-streaming.soundcloud.cloud",
            "media-streaming.soundcloud.cloud",
            "api.media-streaming.soundcloud.cloud",
            # CDN — sndcdn.com is the primary CDN for audio & images
            "sndcdn.com",
            "cf-media.sndcdn.com",
            "cf-hls-media.sndcdn.com",
            "w1.sndcdn.com",
            "wis.sndcdn.com",
            "ec-media.sndcdn.com",
            "ec-rtmp-media.sndcdn.com",
            "i1.sndcdn.com",
            "style.sndcdn.com",
            "a-v2.sndcdn.com",
            "audiocdn.sndcdn.com",
            # NEW: additional sndcdn.com edge nodes reported by users as
            # required for audio playback in 2024-2025.
            "al.sndcdn.com",
            "va.sndcdn.com",
            "wave.sndcdn.com",
            "m1.sndcdn.com",
            "booth.sndcdn.com",
            "cf-stream.sndcdn.com",
        ],
    ),
]

# Backwards-compat alias for any older references.
PRESETS = SERVICES


def service_by_id(sid: str) -> Optional[ServicePreset]:
    for s in SERVICES:
        if s.id == sid:
            return s
    return None


def _norm(domains: Iterable[str]) -> List[str]:
    """Normalize free-form domain input (handles URLs, commas and wildcards)."""
    out: List[str] = []
    for raw in domains or []:
        chunk = (raw or "").replace(",", " ").replace(";", " ")
        for part in chunk.split():
            p = part.strip().lower()
            if not p:
                continue
            # Users often paste full URLs. zapret hostlists expect domains only.
            p = p.split("://", 1)[-1]
            p = p.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
            # Strip common wildcard/dot prefixes and optional port.
            p = p.lstrip("*.")
            if ":" in p and not p.startswith("["):
                p = p.split(":", 1)[0]
            if p and " " not in p and p not in out:
                out.append(p)
    return out


def resolve_domains(preset_ids: Iterable[str], custom: Iterable[str]) -> List[str]:
    """All domains for the enabled presets plus any custom ones."""
    ids: Set[str] = set(preset_ids or [])
    out: List[str] = []
    for svc in SERVICES:
        if svc.id in ids:
            for d in svc.domains:
                d = d.strip().lower()
                if d and d not in out:
                    out.append(d)
    for d in _norm(custom):
        if d not in out:
            out.append(d)
    return out


def _write_managed_block(path: Path, domains: List[str]) -> None:
    """Replace (or remove) our managed block in *path*, keeping other lines."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        )
    except OSError:
        return

    kept: List[str] = []
    inside = False
    for ln in existing.splitlines():
        s = ln.strip()
        if s == _BEGIN:
            inside = True
            continue
        if s == _END:
            inside = False
            continue
        if not inside:
            kept.append(ln)
    # Drop the lone placeholder and trailing blanks so the file stays tidy.
    kept = [ln for ln in kept if ln.strip() != _PLACEHOLDER]
    while kept and not kept[-1].strip():
        kept.pop()

    block: List[str] = []
    if domains:
        block = [_BEGIN] + list(domains) + [_END]

    if kept and block:
        out_lines = kept + [""] + block
    else:
        out_lines = kept + block

    text = "\n".join(out_lines).strip("\n")
    if not text:
        text = _PLACEHOLDER
    try:
        path.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass


def apply_lists(
    zapret_dir,
    *,
    include_presets: Iterable[str],
    include_custom: Iterable[str],
    exclude_presets: Iterable[str],
    exclude_custom: Iterable[str],
) -> None:
    """Write both managed blocks from the given selections."""
    lists = Path(zapret_dir) / "lists"
    _write_managed_block(
        lists / INCLUDE_FILE, resolve_domains(include_presets, include_custom)
    )
    _write_managed_block(
        lists / EXCLUDE_FILE, resolve_domains(exclude_presets, exclude_custom)
    )


def inject_exclusions(args, *_a, **_k):
    """Deprecated no-op kept for backwards-compat; lists are native now."""
    return list(args)
