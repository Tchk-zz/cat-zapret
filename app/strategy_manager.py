"""Parse Flowseal zapret ``.bat`` files into a catalog of strategies.

Each ``general*.bat`` / ``discord*.bat`` in the zapret root launches
``winws.exe`` with a specific set of DPI-desync arguments. Instead of
hardcoding strategies we parse the batch files, so new strategies shipped by
Flowseal are picked up automatically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Batch files that are NOT user-selectable strategies.
_EXCLUDE = {
    "service.bat",
    "service_install.bat",
    "service_remove.bat",
    "check_updates.bat",
    "cleanup.bat",
    "preset_russia.bat",
}

# Matches `set "NAME=VALUE"` or `set NAME=VALUE` in batch files.
_SET_RE = re.compile(r'set\s+"?([A-Za-z0-9_]+)=([^"\r\n]*)"?', re.IGNORECASE)
# Matches the winws launch line and captures everything after the exe.
_WINWS_RE = re.compile(r'winws\.exe"?\s*(.*)', re.IGNORECASE)
# %VAR% expansion token.
_VAR_RE = re.compile(r"%([A-Za-z0-9_]+)%")
# Placeholders kept verbatim in the portable JSON catalog (resolved at runtime).
PORTABLE_VARS = {
    "BIN",
    "LISTS",
    "ZAPRET",
    "GAMEFILTER",
    "GAMEFILTERTCP",
    "GAMEFILTERUDP",
}


@dataclass
class Strategy:
    name: str
    source_file: Path
    args: List[str]
    description: str = ""
    custom: bool = False

    @property
    def key(self) -> str:
        return self.name


def _pretty_name(filename: str) -> str:
    """`general (ALT2).bat` -> `General \u2014 ALT2`."""
    stem = Path(filename).stem
    m = re.match(r"^(?P<base>[^(]+?)\s*\((?P<variant>.+)\)\s*$", stem)
    if m:
        base = m.group("base").strip().capitalize()
        variant = m.group("variant").strip()
        return f"{base} \u2014 {variant}"
    return stem.capitalize()


def _tokenize_args(raw: str) -> List[str]:
    """Split a winws argument string into tokens, honouring quotes."""
    tokens: List[str] = []
    cur = ""
    quoted = False
    for ch in raw:
        if ch == '"':
            quoted = not quoted
            continue
        if ch.isspace() and not quoted:
            if cur:
                tokens.append(cur)
                cur = ""
            continue
        cur += ch
    if cur:
        tokens.append(cur)
    # Drop trailing line-continuations.
    return [t for t in tokens if t not in ("^", "")]


def _expand_vars(value: str, env: Dict[str, str]) -> str:
    """Expand %VAR% (and the cmd %~dp0) tokens repeatedly until stable."""
    dp0 = env.get("~DP0")
    if dp0 and "%~dp0" in value.lower():
        value = re.sub(r"%~dp0", lambda _m: dp0, value, flags=re.IGNORECASE)
    for _ in range(10):
        new = _VAR_RE.sub(lambda m: env.get(m.group(1).upper(), m.group(0)), value)
        if new == value:
            break
        value = new
    return value


def _game_filter_env(zapret_dir: Path) -> Dict[str, str]:
    """Replicate service.bat's load_game_filter / game_switch_status.

    When the game filter is disabled (no utils/game_filter.enabled), Flowseal
    uses the placeholder port "12" so the winws command stays valid.
    """
    gf = {"GAMEFILTER": "12", "GAMEFILTERTCP": "12", "GAMEFILTERUDP": "12"}
    flag = zapret_dir / "utils" / "game_filter.enabled"
    try:
        if flag.exists():
            mode = ""
            for line in flag.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip():
                    mode = line.strip().lower()
                    break
            full = "1024-65535"
            if mode == "all":
                gf = {"GAMEFILTER": full, "GAMEFILTERTCP": full, "GAMEFILTERUDP": full}
            elif mode == "tcp":
                gf = {"GAMEFILTER": full, "GAMEFILTERTCP": full, "GAMEFILTERUDP": "12"}
            elif mode == "udp":
                gf = {"GAMEFILTER": full, "GAMEFILTERTCP": "12", "GAMEFILTERUDP": full}
    except OSError:
        pass
    return gf


def _clean_token(token: str, keep=None) -> str:
    """Drop unsafe/unknown tokens and tidy dangling commas.

    Safety net so an unknown variable never reaches winws.exe as a literal
    `%VAR%`, which it rejects with errors like "bad value for --wf-tcp".
    Variables named in ``keep`` (portable catalog placeholders) are preserved.

    Some Flowseal batch recipes contain cmd-escaped ``^!`` in fake TLS slots.
    When stored in our JSON catalog and launched without cmd.exe, winws treats
    that value as a file path and exits with "could not read ^!".  Drop that
    catalog artifact at load time; neighboring fake TLS arguments remain.
    """
    token = token.strip()
    if not token:
        return ""
    if token in ("^", "^!", "!") or token.endswith("=^!") or token.endswith("=!"):
        return ""
    keep = keep or set()

    def _sub(m):
        name = m.group(1).strip("~").upper()
        return m.group(0) if name in keep else ""

    if "%" in token:
        token = re.sub(r"%([~A-Za-z0-9_]+)%?", _sub, token)
    token = re.sub(r",{2,}", ",", token)
    token = token.replace("=,", "=").rstrip(",")
    if token in ("^", "^!", "!") or token.endswith("=^!") or token.endswith("=!"):
        return ""
    return token


def parse_bat(path: Path, zapret_dir: Path, portable: bool = False) -> Optional[Strategy]:
    """Parse a single .bat file into a Strategy, or None if it has no winws call."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    # Join lines that use ^ continuation so the whole winws command is one line.
    text = re.sub(r"\^\s*\r?\n", " ", text)

    # Read the .bat's own `set` statements first, then force the variables we
    # resolve ourselves so they always win over raw cmd constructs we cannot
    # evaluate literally (e.g. `set "BIN=%~dp0bin\"`).
    env: Dict[str, str] = {}
    for m in _SET_RE.finditer(text):
        env[m.group(1).upper()] = m.group(2).strip()
    if portable:
        # Keep paths and game-filter values as placeholders so the catalog is
        # independent of where zapret is installed.
        env["BIN"] = "%BIN%"
        env["LISTS"] = "%LISTS%"
        env["~DP0"] = "%ZAPRET%"
        env["GAMEFILTER"] = "%GAMEFILTER%"
        env["GAMEFILTERTCP"] = "%GAMEFILTERTCP%"
        env["GAMEFILTERUDP"] = "%GAMEFILTERUDP%"
    else:
        env["BIN"] = str(zapret_dir / "bin") + "\\"
        env["LISTS"] = str(zapret_dir / "lists") + "\\"
        env["~DP0"] = str(zapret_dir) + "\\"
        # GameFilter* come from `service.bat load_game_filter`. Leaving them
        # unexpanded produced `--wf-tcp=...,%GameFilterTCP%` -> winws "bad value".
        env.update(_game_filter_env(zapret_dir))

    launch: Optional[str] = None
    for line in text.splitlines():
        m = _WINWS_RE.search(line)
        if m:
            launch = m.group(1)
            break
    if launch is None:
        return None

    keep = PORTABLE_VARS if portable else None
    expanded = _expand_vars(launch, env)
    args = []
    for t in _tokenize_args(expanded):
        tok = _clean_token(_expand_vars(t, env), keep)
        if tok:
            args.append(tok)
    if not args:
        return None

    return Strategy(
        name=_pretty_name(path.name),
        source_file=path,
        args=args,
        description=_describe(args),
    )


def _describe(args: List[str]) -> str:
    """Build a short human description from the desync arguments."""
    bits: List[str] = []
    joined = " ".join(args)
    if "fake" in joined:
        bits.append("fake")
    if "split" in joined or "multisplit" in joined:
        bits.append("split")
    if "disorder" in joined:
        bits.append("disorder")
    if "--wf-udp" in joined or "udp" in joined:
        bits.append("UDP/QUIC")
    if "fakedsplit" in joined:
        bits.append("fakedsplit")
    return ", ".join(dict.fromkeys(bits)) or "DPI-desync"


def expand_portable_args(args: List[str], zapret_dir: Path) -> List[str]:
    """Resolve portable catalog placeholders (%BIN% etc.) for *zapret_dir*."""
    env: Dict[str, str] = {
        "BIN": str(zapret_dir / "bin") + "\\",
        "LISTS": str(zapret_dir / "lists") + "\\",
        "ZAPRET": str(zapret_dir) + "\\",
    }
    env.update(_game_filter_env(zapret_dir))
    out: List[str] = []
    for a in args:
        tok = _clean_token(_expand_vars(a, env))
        if tok:
            out.append(tok)
    return out


def _split_wf(args):
    """Split winws args into (wf_tcp, wf_udp, other_wf_globals, profile_body)."""
    wf_tcp = None
    wf_udp = None
    others = []
    body = []
    for a in args:
        if a.startswith("--wf-tcp="):
            wf_tcp = a[len("--wf-tcp="):]
        elif a.startswith("--wf-udp="):
            wf_udp = a[len("--wf-udp="):]
        elif a.startswith("--wf-"):
            others.append(a)
        else:
            body.append(a)
    return wf_tcp, wf_udp, others, body


def _merge_ports(*specs):
    """Union comma-separated WinDivert port specs, preserving order, deduped."""
    seen: List[str] = []
    for spec in specs:
        if not spec:
            continue
        for part in spec.split(","):
            part = part.strip()
            if part and part not in seen:
                seen.append(part)
    return ",".join(seen)


def combine_with_roblox(base_args, extra_args):
    """Merge a base strategy with extra winws profiles into ONE invocation.

    winws can run several profiles in a single process: one set of --wf-tcp/
    --wf-udp WinDivert filters followed by profiles separated by --new. We union
    the port filters of both strategies and chain their profile bodies, so the
    base bypass (YouTube/Discord) and the Roblox profiles run together.
    """
    b_tcp, b_udp, b_other, b_body = _split_wf(list(base_args))
    e_tcp, e_udp, e_other, e_body = _split_wf(list(extra_args))
    out: List[str] = []
    tcp = _merge_ports(b_tcp, e_tcp)
    udp = _merge_ports(b_udp, e_udp)
    if tcp:
        out.append("--wf-tcp=" + tcp)
    if udp:
        out.append("--wf-udp=" + udp)
    for o in b_other + e_other:
        if o not in out:
            out.append(o)
    out += b_body
    if b_body and e_body and b_body[-1] != "--new" and e_body[0] != "--new":
        out.append("--new")
    out += e_body
    return out


class StrategyManager:
    """Discovers and caches strategies from the zapret folder."""

    def __init__(self, zapret_dir: Path):
        self.zapret_dir = Path(zapret_dir)
        self.custom_dir = self.zapret_dir / "custom_strategies"
        self._strategies: List[Strategy] = []

    @property
    def strategies(self) -> List[Strategy]:
        return list(self._strategies)

    def winws_path(self) -> Path:
        return self.zapret_dir / "bin" / "winws.exe"

    def reload(self, force_rebuild: bool = False) -> List[Strategy]:
        from . import strategy_catalog

        # The JSON catalog is the ONLY source of truth. We never parse foreign
        # .bat files on a normal launch. ``force_rebuild`` is used right after a
        # zapret update: it converts the freshly downloaded .bat into the
        # catalog and then deletes them. Otherwise we just make sure a catalog
        # exists (seeded on first run from the copy bundled with the app).
        cpath = strategy_catalog.catalog_path(self.zapret_dir)
        try:
            if force_rebuild:
                strategy_catalog.rebuild_from_bats(self.zapret_dir, delete_bats=True)
            strategy_catalog.ensure_catalog(self.zapret_dir)
        except Exception:
            pass

        found: List[Strategy] = []
        try:
            if cpath.exists():
                found = strategy_catalog.load_catalog(self.zapret_dir)
        except Exception:
            found = []

        if not found:
            # Safety net only: if the catalog is missing/corrupt and a .bat
            # somehow remains, parse it directly. It will be removed on the next
            # successful update.
            for bat in sorted(self.zapret_dir.glob("*.bat")):
                if bat.name.lower() in _EXCLUDE:
                    continue
                strat = parse_bat(bat, self.zapret_dir)
                if strat:
                    found.append(strat)

        # Custom strategies stored as JSON next to the app.
        found.extend(self._load_custom())
        # Order: 'general' first, then alphabetic; popular ones bubble up.
        found.sort(key=self._sort_key)
        self._strategies = found
        return self.strategies

    @staticmethod
    def _sort_key(s: Strategy):
        name = s.name.lower()
        # Plain "general" and "discord" first \u2014 they are the most common.
        priority = 0
        if name == "general":
            priority = -3
        elif name.startswith("general"):
            priority = -2
        elif name.startswith("discord"):
            priority = -1
        return (s.custom, priority, name)

    def get(self, name: str) -> Optional[Strategy]:
        for s in self._strategies:
            if s.name == name:
                return s
        return None

    # --- custom strategies -------------------------------------------------
    def _load_custom(self) -> List[Strategy]:
        import json

        out: List[Strategy] = []
        if not self.custom_dir.exists():
            return out
        for jf in sorted(self.custom_dir.glob("*.json")):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                args = data.get("args")
                if isinstance(args, str):
                    args = _tokenize_args(args)
                out.append(
                    Strategy(
                        name=data.get("name", jf.stem),
                        source_file=jf,
                        args=list(args or []),
                        description=data.get("description", "custom"),
                        custom=True,
                    )
                )
            except (OSError, ValueError):
                continue
        return out

    def save_custom(self, name: str, args, description: str = "") -> Strategy:
        """Save a user-authored custom strategy.

        ``%BIN%`` / ``%LISTS%`` / ``%ZAPRET%`` / ``%~dp0`` placeholders are
        resolved to the real zapret paths at save time, because winws.exe has
        no shell to expand them and would crash with "could not access file
        %BIN%..." at launch. The cleaned args are stored as the canonical form.
        """
        import json

        self.custom_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(args, str):
            args = _tokenize_args(args)
        # Resolve any cmd-style placeholders so the saved strategy works
        # straight away without surprises.
        env = {
            "BIN": str(self.zapret_dir / "bin") + "\\",
            "LISTS": str(self.zapret_dir / "lists") + "\\",
            "ZAPRET": str(self.zapret_dir) + "\\",
            "~DP0": str(self.zapret_dir) + "\\",
        }
        cleaned: List[str] = []
        for tok in args:
            expanded = _expand_vars(tok, env)
            cleaned_tok = _clean_token(expanded)
            if cleaned_tok:
                cleaned.append(cleaned_tok)
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "custom"
        path = self.custom_dir / f"{safe}.json"
        path.write_text(
            json.dumps(
                {"name": name, "args": list(cleaned), "description": description},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.reload()
        return self.get(name) or Strategy(name, path, list(cleaned), description, True)

    def delete_custom(self, name: str) -> bool:
        s = self.get(name)
        if s and s.custom and s.source_file.exists():
            try:
                s.source_file.unlink()
                self.reload()
                return True
            except OSError:
                return False
        return False

    # --- ordering for auto-selection --------------------------------------
    def ordered_for_autoselect(self, preferred: Optional[List[str]] = None) -> List[Strategy]:
        """Return strategies in the order the auto-selector should try them.

        Order: explicitly preferred names first (in the given order), then the
        remaining strategies in their natural catalog order. Names that are not
        found are simply skipped.
        """
        if not self._strategies:
            self.reload()
        preferred = preferred or []
        by_name = {s.name: s for s in self._strategies}
        ordered: List[Strategy] = []
        seen = set()
        for name in preferred:
            s = by_name.get(name)
            if s is not None and s.name not in seen:
                ordered.append(s)
                seen.add(s.name)
        for s in self._strategies:
            if s.name not in seen:
                ordered.append(s)
                seen.add(s.name)
        return ordered
