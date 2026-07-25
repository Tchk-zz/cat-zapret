"""Telegram MTProto proxy integration (Flowseal/tg-ws-proxy).

This module embeds the upstream ``tg-ws-proxy`` engine (from
https://github.com/Flowseal/tg-ws-proxy, MIT, Flowseal) directly into the Zapret
GUI process — there is NO separate ``TgWsProxy.exe`` subprocess and therefore no
second tray icon or duplicate application. The proxy's asyncio loop runs in a
background thread inside our own process; we expose start/stop/status just like
the zapret ``ProcessRunner`` does.

The proxy exposes a local MTProto endpoint (``127.0.0.1:1443`` by default) that
Telegram Desktop connects to. The proxy then tunnels traffic through WebSocket
to Telegram DCs, bypassing blocks without needing a third-party server.

Stop semantics
--------------
``stop()`` is **non-blocking** from the caller's perspective: it signals the
asyncio loop to shut down and launches a daemon "joiner" thread that waits for
the engine thread to finish (max 5s). This way the GUI thread never freezes.
``is_running()`` immediately reflects the user's intent (False right after
stop), even if the engine thread is still cleaning up.

We still ship the optional ``ensure_installed``/``latest_release`` helpers for
backwards-compatibility — they no longer download ``TgWsProxy.exe``; instead
they are placeholders so callers don't crash if they invoke them.
"""
from __future__ import annotations

import asyncio
import io
import json
import ipaddress
import importlib
import logging
import logging.handlers
import os
import sys
import threading
import time
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

# Default endpoint shown to the user before the proxy has written its config.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1443

# File where we persist our proxy instance's config so the GUI can show the
# secret/link. The upstream engine accepts a secret via --secret; if none is
# provided it auto-generates one and logs it. We persist a generated secret
# ourselves so the link stays stable across restarts.
CONFIG_FILENAME = "tg_proxy_config.json"
LOG_FILENAME = "tg_proxy.log"

# User-facing log anti-spam. When Cloudflare returns HTTP 429 or times out,
# tg-ws-proxy can emit the same fallback failure for every Telegram connection.
# The engine may log these as INFO/WARNING in some runtime versions, so we
# filter at the GUI boundary too (not only inside bridge.py). This keeps the
# log readable while preserving one periodic diagnostic line.
_TG_NOISY_LOG_RE = re.compile(
    r"\[[^\]]+\]\s+(DC\d+[^:]*\s+CF proxy failed|TCP fallback to [^ ]+ failed|DC\d+[^:]*\s+no fallback available|DC\d+\s+not in config -> fallback|DC\d+[^-]*-> trying CF proxy|bad handshake \(wrong secret(?: or |/)proto)"
)
_TG_NOISY_DETAIL_RE = re.compile(r"(HTTP 429|Too Many Requests|TimeoutError\(\)|not in config -> fallback|-> trying CF proxy|bad handshake \(wrong secret(?: or |/)proto)")
_TG_PROGRESS_NOISE_MARKERS = (
    "-> wss://",
    "WS connect timed out via",
    "WS connect to ",
    " timed out -> fallback",
    "-> fronting fallback",
    "fronting failed",
    "WS cooldown",
    "WS session closed",
    "fallback closed",
    "Switched active CF domain",
    "-> TCP fallback to",
)


class _TGGuiLogDeduper:
    def __init__(self, min_interval: float = 60.0):
        self.min_interval = min_interval
        self._last = {}
        self._suppressed = {}
        self._lock = threading.Lock()

    def _key(self, msg: str) -> str:
        # Remove volatile local ports so identical failures on new localhost
        # connections collapse into the same bucket.
        msg = re.sub(r"\[127\.0\.0\.1:\d+\]", "[127.0.0.1:*]", msg)
        msg = re.sub(r"DC\d+", lambda m: m.group(0), msg)
        msg = re.sub(r"WsHandshakeError\('HTTP 429: HTTP/1\.1 429 Too Many Requests'\)", "HTTP429", msg)
        msg = re.sub(r"TimeoutError\(\)", "Timeout", msg)
        msg = re.sub(r"bad handshake \(wrong secret(?: or |/)proto[^)]*\)", "bad_handshake", msg)
        msg = re.sub(r"wss://[^ ]+", "wss://*", msg)
        msg = re.sub(r"Host [^)]+", "Host *", msg)
        msg = re.sub(r"via [0-9]{1,3}(?:\.[0-9]{1,3}){3}", "via *", msg)
        msg = re.sub(r"to [0-9]{1,3}(?:\.[0-9]{1,3}){3}:443", "to *:443", msg)
        msg = re.sub(r"\^\d+(?:\.\d+)?[KMG]?B \(\d+ pkts\) v\d+(?:\.\d+)?[KMG]?B \(\d+ pkts\) in \d+(?:\.\d+)?s", "session-stats", msg)
        msg = re.sub(r"DC(\d+)", r"DC\1", msg)
        return msg

    def should_emit(self, msg: str):
        progress_noise = "[127.0.0.1:" in msg and any(m in msg for m in _TG_PROGRESS_NOISE_MARKERS)
        noisy = bool(_TG_NOISY_LOG_RE.search(msg)) or progress_noise
        # `no fallback available` and progress lines often repeat per Telegram
        # connection even without exception text in the same line.
        has_noisy_detail = bool(_TG_NOISY_DETAIL_RE.search(msg) or "no fallback available" in msg) or progress_noise
        if not (noisy and has_noisy_detail):
            return True, msg
        key = self._key(msg)
        now = time.monotonic()
        with self._lock:
            last = self._last.get(key, 0.0)
            if now - last >= self.min_interval:
                suppressed = self._suppressed.pop(key, 0)
                self._last[key] = now
                if suppressed:
                    return True, f"{msg} (повторялось ещё {suppressed} раз; похожие ошибки скрываются {int(self.min_interval)}с)"
                return True, f"{msg} (похожие ошибки будут скрываться {int(self.min_interval)}с)"
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return False, ""


# Upstream GitHub repo (used by the "Check for updates" feature).
REPO = "Flowseal/tg-ws-proxy"
LATEST_API = "https://api.github.com/repos/" + REPO + "/releases/latest"
RELEASES_URL = "https://github.com/" + REPO + "/releases"


@dataclass
class TGProxyConfig:
    """Subset of the proxy's runtime config that we surface in the GUI."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    secret: str = ""


@dataclass
class TGProxyReleaseInfo:
    tag: str
    name: str
    zip_url: str
    html_url: str


@dataclass
class TGProxyUpdateResult:
    ok: bool
    status: str  # updated | up_to_date | available | error
    message: str
    tag: str = ""
    current: str = ""
    needs_restart: bool = False


_FALLBACK_ONLY_TOKEN = "__fallback_only__"
_FALLBACK_ONLY_INPUTS = {"fallback-only", "fallback_only", "fallback", "none", "clear", "empty", "off", "disabled"}


def _default_dc_ips():
    """User-facing recommended DC->IP preset from upstream tg-ws-proxy.

    Flowseal's README recommends trying only ``4:149.154.167.220`` for
    photo/video issues, and clearing the field if that still fails. The runtime
    below uses a broader *auto* map by default to avoid unnecessary CF fallback
    for known DCs, while this helper remains the UI placeholder/recommended
    manual preset.
    """
    return ["4:149.154.167.220"]


def _resolve_dc_ips(user_overrides: Optional[list] = None) -> list:
    """Validate user DC->IP overrides.

    Empty input means "auto": use the embedded engine's DC_DEFAULT_IPS for all
    known DCs. Advanced users can force fallback-only by storing one of
    ``fallback-only``, ``none``, ``clear`` or ``off`` in the list.
    """
    out = []
    for entry in user_overrides or []:
        if not isinstance(entry, str):
            continue
        s = entry.strip()
        if not s:
            continue
        if s.lower() in _FALLBACK_ONLY_INPUTS:
            return [_FALLBACK_ONLY_TOKEN]
        if ":" not in s:
            continue
        dc_part, _, ip_part = s.partition(":")
        try:
            dc_num = int(dc_part)
            ip_text = str(ipaddress.ip_address(ip_part.strip()))
        except ValueError:
            continue
        out.append(f"{dc_num}:{ip_text}")
    return out


def _engine_default_dc_redirects(pkg: str) -> dict:
    """Return the engine's built-in DC_DEFAULT_IPS as {dc: ip}.

    This is the real fix for repeated "DC not in config -> fallback": if the
    user has not configured DC->IP manually, known DCs should still have a
    direct WebSocket target and should not jump to CF proxy immediately.
    """
    try:
        utils_mod = importlib.import_module(pkg + ".utils")
        raw = getattr(utils_mod, "DC_DEFAULT_IPS", {}) or {}
        out = {}
        for dc, ip in dict(raw).items():
            out[int(dc)] = str(ipaddress.ip_address(str(ip)))
        if out:
            return out
    except Exception:
        pass
    return {
        1: "149.154.175.50",
        2: "149.154.167.51",
        3: "149.154.175.100",
        4: "149.154.167.91",
        5: "149.154.171.5",
        203: "91.105.192.100",
    }


def _effective_dc_redirects(pkg: str, parse_dc_ip_list, dc_ips: Optional[list]) -> dict:
    """Build runtime dc_redirects from user config.

    Empty config follows upstream tg-ws-proxy behavior: leave DC->IP empty and
    let the fallback chain work. The previous AUTO default forced direct
    Telegram IP/WebSocket routes on networks where they time out, breaking TG
    proxy and creating massive log spam.

    - [] / missing: upstream fallback chain.
    - ["auto"]: optional full built-in DC map for users whose network allows it.
    - ["fallback-only"] or similar: explicitly empty (same as default).
    - explicit "DC:IP" entries: exactly those validated entries.
    """
    raw = [str(x).strip().lower() for x in (dc_ips or []) if isinstance(x, str)]
    if any(x in {"auto", "default", "dc-defaults", "builtin", "built-in"} for x in raw):
        return _engine_default_dc_redirects(pkg)
    resolved = _resolve_dc_ips(dc_ips)
    if resolved == [_FALLBACK_ONLY_TOKEN]:
        return {}
    if resolved:
        return parse_dc_ip_list(resolved)
    return {}


def _resolve_domains(domains: Optional[list]) -> list:
    """Normalize optional CF proxy/worker domain overrides."""
    out = []
    seen = set()
    for entry in domains or []:
        if not isinstance(entry, str):
            continue
        for chunk in entry.replace(",", " ").replace(";", " ").split():
            d = chunk.strip().lower().strip(".")
            if not d or "://" in d or "/" in d:
                continue
            if d not in seen:
                seen.add(d)
                out.append(d)
    return out


def tg_proxy_dir(data_dir: Path) -> Path:
    """Folder where the proxy config and log live."""
    return Path(data_dir) / "tg-ws-proxy"


def runtime_engine_dir(data_dir: Path) -> Path:
    """Writable engine override directory.

    The bundled engine inside ``app/tg_proxy_engine`` cannot be modified in a
    PyInstaller exe. Updates therefore go here and are imported as a normal
    Python package before falling back to the bundled copy.
    """
    return tg_proxy_dir(data_dir) / "engine" / "tg_proxy_engine_runtime"


def config_path(data_dir: Path) -> Path:
    return tg_proxy_dir(data_dir) / CONFIG_FILENAME


def log_path(data_dir: Path) -> Path:
    return tg_proxy_dir(data_dir) / LOG_FILENAME


def is_installed(data_dir: Path) -> bool:
    """Always True — the proxy engine is now embedded as Python code.

    Kept for backwards-compat with the previous subprocess-based version.
    """
    return True


def local_version(data_dir: Path) -> str:
    """Return the embedded tg-ws-proxy engine version.

    Do not import ``app.tg_proxy_engine`` here: importing the package before an
    update would cache the old ``__version__`` in memory and make a freshly
    downloaded engine look stale until the whole GUI restarts. Reading the
    package VERSION file directly keeps update checks accurate.
    """
    try:
        rp = runtime_engine_dir(data_dir) / "VERSION"
        if rp.exists():
            text = rp.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return text
    except Exception:
        pass
    try:
        p = Path(__file__).resolve().parent / "tg_proxy_engine" / "VERSION"
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return text
    except Exception:
        pass
    try:
        from app.tg_proxy_engine import __version__
        return __version__
    except Exception:
        return ""


def save_local_version(data_dir: Path, tag: str) -> None:
    """Persist the embedded engine version marker."""
    try:
        p = runtime_engine_dir(data_dir) / "VERSION"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_norm(tag), encoding="utf-8")
    except OSError:
        pass


def _version_key(v: str) -> tuple:
    """Comparable semantic-ish version key: v1.8.1 > v1.7.3."""
    import re
    nums = [int(x) for x in re.findall(r"\d+", _norm(v))]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:4])


def _release_from_json(data: dict) -> Optional[TGProxyReleaseInfo]:
    tag = data.get("tag_name", "") or data.get("name", "")
    zip_url = data.get("zipball_url", "")
    if not tag or not zip_url:
        return None
    return TGProxyReleaseInfo(
        tag=tag,
        name=data.get("name", tag),
        zip_url=zip_url,
        html_url=data.get("html_url", RELEASES_URL),
    )


def latest_release(timeout: float = 10.0) -> Optional[TGProxyReleaseInfo]:
    """Fetch the newest upstream tg-ws-proxy release from GitHub.

    We intentionally query the releases list and select the highest semantic
    tag instead of trusting GitHub's single ``/latest`` flag. Upstream has had
    cases where mirrors/indexes show a newer tag while the GitHub "Latest"
    label lags behind; selecting by version makes the button less confusing.
    """
    if requests is None:
        return None
    try:
        r = requests.get(
            "https://api.github.com/repos/" + REPO + "/releases?per_page=30",
            timeout=timeout,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ZapretGUI-tg-proxy",
            },
        )
        r.raise_for_status()
        releases = r.json()
        if isinstance(releases, list):
            candidates = []
            for item in releases:
                if not isinstance(item, dict) or item.get("draft"):
                    continue
                rel = _release_from_json(item)
                if rel is not None:
                    candidates.append(rel)
            if candidates:
                return max(candidates, key=lambda rel: _version_key(rel.tag))
    except Exception:
        pass
    try:
        r = requests.get(
            LATEST_API,
            timeout=timeout,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ZapretGUI-tg-proxy",
            },
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return _release_from_json(data)
    except Exception:
        pass
    return None


def _rel_tag(rel) -> str:
    if isinstance(rel, TGProxyReleaseInfo):
        return rel.tag
    if isinstance(rel, dict):
        return rel.get("tag_name", "") or rel.get("name", "")
    return getattr(rel, "tag", "") or getattr(rel, "name", "") or ""


def update_available(data_dir: Path):
    """Return release info if a newer engine version is on GitHub, else None.

    Kept compatible with older tests/callers that monkeypatch ``latest_release``
    to return raw GitHub JSON dicts.
    """
    rel = latest_release()
    if rel is None:
        return None
    cur = local_version(data_dir)
    tag = _rel_tag(rel)
    if not tag:
        return None
    if cur and _version_key(tag) <= _version_key(cur):
        return None
    return rel


def _norm(v: str) -> str:
    """Normalise a version string for comparison: trim, strip leading v/V."""
    return (v or "").strip().lstrip("vV").strip()


def _common_root(names) -> str:
    norm = [n.replace("\\", "/") for n in names if n and not n.startswith("__MACOSX")]
    if not norm:
        return ""
    tops = {n.split("/")[0] for n in norm}
    if len(tops) == 1:
        only = next(iter(tops))
        if any(n.startswith(only + "/") for n in norm):
            return only + "/"
    return ""


def _bundled_engine_package_dir() -> Path:
    return Path(__file__).resolve().parent / "tg_proxy_engine"


def _runtime_engine_parent(data_dir: Path) -> Path:
    return runtime_engine_dir(data_dir).parent


def _engine_modules_loaded() -> bool:
    import sys as _sys
    return any(
        name.startswith("app.tg_proxy_engine.") or name.startswith("tg_proxy_engine_runtime.")
        for name in _sys.modules
    )


def _runtime_engine_package(data_dir: Path) -> Optional[str]:
    pkg_dir = runtime_engine_dir(data_dir)
    if not (pkg_dir / "tg_ws_proxy.py").exists():
        return None
    parent = str(_runtime_engine_parent(data_dir))
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return "tg_proxy_engine_runtime"


def _engine_package_name(data_dir: Path) -> str:
    return _runtime_engine_package(data_dir) or "app.tg_proxy_engine"


def download_and_apply_update(
    rel: TGProxyReleaseInfo,
    data_dir: Path,
    timeout: float = 60.0,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> TGProxyUpdateResult:
    """Download upstream source zip and refresh embedded proxy modules.

    The upstream project is Python. For the source distribution we copy only
    ``proxy/*.py`` into our embedded package and keep our own ``__init__.py`` /
    integration wrapper. If the proxy modules were already imported in this
    process, the new files are written but the user must restart ZapretGUI for
    Python to load them cleanly.
    """
    if requests is None:
        return TGProxyUpdateResult(False, "error", "Модуль requests не установлен.")
    if progress_cb:
        progress_cb("Загрузка tg-ws-proxy " + rel.tag + "...")
    try:
        r = requests.get(rel.zip_url, timeout=timeout, headers={"User-Agent": "ZapretGUI-tg-proxy"})
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return TGProxyUpdateResult(False, "error", "Ошибка загрузки tg-ws-proxy: " + str(exc), tag=rel.tag)

    package_dir = runtime_engine_dir(data_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    # The runtime package needs an __init__.py for relative imports inside the
    # upstream proxy modules. Keep it tiny and version-file based.
    init_py = package_dir / "__init__.py"
    if not init_py.exists():
        init_py.write_text(
            "from pathlib import Path\n"
            "def _read_version():\n"
            "    p = Path(__file__).resolve().parent / 'VERSION'\n"
            "    return p.read_text(encoding='utf-8').strip() if p.exists() else '0.0.0'\n"
            "__version__ = _read_version()\n",
            encoding="utf-8",
        )
    copied = 0
    skipped = 0
    was_loaded = _engine_modules_loaded()
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            root = _common_root(zf.namelist())
            for member in zf.namelist():
                norm = member.replace("\\", "/")
                rel_path = norm[len(root):] if root and norm.startswith(root) else norm
                if not rel_path or norm.endswith("/"):
                    continue
                if not rel_path.startswith("proxy/") or not rel_path.endswith(".py"):
                    continue
                name = rel_path.split("/", 1)[1]
                if not name or "/" in name or name == "__init__.py":
                    skipped += 1
                    continue
                target = package_dir / name
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_bytes(zf.read(member))
                os.replace(tmp, target)
                copied += 1
                if progress_cb:
                    progress_cb("Обновлён TG module: " + name)
            # Keep upstream license close to the embedded engine.
            for member in zf.namelist():
                norm = member.replace("\\", "/")
                rel_path = norm[len(root):] if root and norm.startswith(root) else norm
                if rel_path == "LICENSE":
                    (package_dir / "LICENSE").write_bytes(zf.read(member))
                    break
    except zipfile.BadZipFile:
        return TGProxyUpdateResult(False, "error", "Скачанный архив tg-ws-proxy повреждён.", tag=rel.tag)
    except Exception as exc:  # noqa: BLE001
        return TGProxyUpdateResult(False, "error", "Ошибка распаковки tg-ws-proxy: " + str(exc), tag=rel.tag)

    if copied <= 0:
        return TGProxyUpdateResult(False, "error", "В архиве tg-ws-proxy не найдены proxy/*.py файлы.", tag=rel.tag)
    save_local_version(data_dir, rel.tag)
    msg = f"tg-ws-proxy обновлён до {_norm(rel.tag)}: {copied} модулей."
    if skipped:
        msg += f" Пропущено: {skipped}."
    if was_loaded:
        msg += " Перезапустите ZapretGUI, чтобы Python загрузил новую версию движка."
    return TGProxyUpdateResult(True, "updated", msg, tag=rel.tag, current=_norm(rel.tag), needs_restart=was_loaded)


def check_and_update(
    data_dir: Path,
    apply_update: bool = False,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> TGProxyUpdateResult:
    cur = local_version(data_dir)
    rel = latest_release()
    if rel is None:
        return TGProxyUpdateResult(False, "error", "Не удалось проверить обновление tg-ws-proxy. Проверьте интернет/GitHub.", current=cur)
    if cur and _version_key(rel.tag) <= _version_key(cur):
        return TGProxyUpdateResult(True, "up_to_date", f"У вас последняя версия tg-ws-proxy: {cur}.", tag=rel.tag, current=cur)
    if not apply_update:
        return TGProxyUpdateResult(True, "available", f"Доступна новая версия tg-ws-proxy: {rel.tag} (у вас {cur or 'unknown'}).", tag=rel.tag, current=cur)
    return download_and_apply_update(rel, data_dir, progress_cb=progress_cb)


def ensure_installed(
    data_dir: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
    force: bool = False,
) -> str:
    """No-op: the engine is embedded. Always returns "ok".

    Kept so any existing caller (e.g. the bootstrap worker) doesn't crash.
    """
    if progress_cb:
        progress_cb("tg-ws-proxy engine is bundled — no download needed.")
    return "ok"


def _generate_secret() -> str:
    """Generate a fresh 32-hex-char MTProto secret."""
    return os.urandom(16).hex()


def _valid_secret(secret: str) -> bool:
    """True for the 32-hex-char MTProto secret format used by dd links."""
    if not isinstance(secret, str) or len(secret.strip()) != 32:
        return False
    try:
        bytes.fromhex(secret.strip())
        return True
    except ValueError:
        return False


def _ensure_config(data_dir: Path) -> TGProxyConfig:
    """Load (or generate) the proxy config file. Returns the resolved config.

    A hand-edited config must never crash the embedded engine: bad ports and
    invalid secrets are repaired here before ``bytes.fromhex`` is reached.
    """
    p = config_path(data_dir)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            host = str(data.get("host") or DEFAULT_HOST).strip() or DEFAULT_HOST
            try:
                port = int(data.get("port") or DEFAULT_PORT)
            except (TypeError, ValueError):
                port = DEFAULT_PORT
            if not (1 <= port <= 65535):
                port = DEFAULT_PORT
            secret = str(data.get("secret") or "").strip().lower()
            if not _valid_secret(secret):
                secret = _generate_secret()
            cfg = TGProxyConfig(host=host, port=port, secret=secret)
            _save_config(data_dir, cfg)
            return cfg
        except (OSError, ValueError, TypeError):
            pass
    # First run: generate a stable secret so the tg:// link stays valid.
    cfg = TGProxyConfig(secret=_generate_secret())
    _save_config(data_dir, cfg)
    return cfg


def _save_config(data_dir: Path, cfg: TGProxyConfig) -> None:
    try:
        tg_proxy_dir(data_dir).mkdir(parents=True, exist_ok=True)
        config_path(data_dir).write_text(
            json.dumps(
                {
                    "host": cfg.host,
                    "port": cfg.port,
                    "secret": cfg.secret,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def read_config(data_dir: Path) -> TGProxyConfig:
    """Read the proxy config from disk (used by the GUI to display the link)."""
    return _ensure_config(data_dir)


def regenerate_secret(data_dir: Path) -> TGProxyConfig:
    """Generate a new random secret, persist it, and return the new config.

    Used by the "Rotate secret" button in the GUI. After calling this, the user
    must reconnect Telegram Desktop with the new ``tg://proxy`` link — the old
    link becomes invalid immediately.
    """
    cfg = _ensure_config(data_dir)
    cfg.secret = _generate_secret()
    _save_config(data_dir, cfg)
    return cfg


def proxy_link(cfg: TGProxyConfig) -> str:
    """Build the ``tg://proxy`` URL that auto-configures Telegram Desktop.

    Returns an empty string if the secret isn't known yet.
    """
    if not cfg.secret:
        return ""
    return f"tg://proxy?server={cfg.host}&port={cfg.port}&secret={cfg.secret}"


class TGProxyRunner:
    """Runs the embedded tg-ws-proxy asyncio engine in a background thread.

    Same locking pattern as the zapret ``ProcessRunner``: a single ``RLock``
    serializes start/stop so the GUI thread and a worker can't race.

    Stop is **non-blocking** from the caller's perspective: ``stop()`` signals
    the engine and returns immediately. ``is_running()`` flips to False right
    away so the UI updates instantly; a daemon "joiner" thread waits for the
    engine thread to finish in the background.
    """

    def __init__(
        self,
        data_dir: Path,
        log_cb: Optional[Callable[[str], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
        dc_ips: Optional[list] = None,
        cfproxy_domains: Optional[list] = None,
        cfworker_domains: Optional[list] = None,
    ):
        self.data_dir = Path(data_dir)
        self._log_cb = log_cb or (lambda _m: None)
        self._on_exit = on_exit
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._lock = threading.RLock()
        self._stopping = False
        self._started = False
        self._cfg: Optional[TGProxyConfig] = None
        # Background "joiner" thread — daemon, so it never blocks app exit.
        self._joiner: Optional[threading.Thread] = None
        # User-specified DC IP overrides (list of "DC:IP" strings). When empty
        # or invalid, the engine uses the hardcoded Flowseal defaults. Stored
        # on the instance so a running engine can be restarted with new DC IPs
        # via set_dc_ips() without recreating the runner.
        self._dc_ips: list = _resolve_dc_ips(dc_ips)
        self._cfproxy_domains: list = _resolve_domains(cfproxy_domains)
        self._cfworker_domains: list = _resolve_domains(cfworker_domains)

    def set_dc_ips(self, dc_ips: Optional[list]) -> None:
        """Update DC->IP overrides. Empty means: no forced DC->IP."""
        with self._lock:
            self._dc_ips = _resolve_dc_ips(dc_ips)

    def set_cf_domains(self, cfproxy_domains: Optional[list], cfworker_domains: Optional[list]) -> None:
        """Update optional CF proxy/worker domain overrides for next start."""
        with self._lock:
            self._cfproxy_domains = _resolve_domains(cfproxy_domains)
            self._cfworker_domains = _resolve_domains(cfworker_domains)

    def get_dc_ips(self) -> list:
        """Return the currently effective DC IP list (a copy)."""
        with self._lock:
            return list(self._dc_ips)

    def get_cf_domains(self) -> tuple:
        with self._lock:
            return list(self._cfproxy_domains), list(self._cfworker_domains)

    def log(self, msg: str) -> None:
        try:
            self._log_cb(msg)
        except Exception:
            pass

    def is_running(self) -> bool:
        """Reflects the user's intent: True if started and not stopping.

        Note: the engine thread may still be alive for a few hundred ms after
        stop() is called, but ``is_running()`` returns False immediately so
        the UI can update without waiting for the engine to clean up.
        """
        with self._lock:
            if self._stopping:
                return False
            return self._started and self._thread is not None and self._thread.is_alive()

    def pid(self) -> Optional[int]:
        # No separate process — return our own PID for diagnostics.
        return os.getpid() if self.is_running() else None

    def current_config(self) -> Optional[TGProxyConfig]:
        with self._lock:
            return self._cfg

    def start(self) -> int:
        """Start the proxy in a background asyncio thread.

        Returns the current process PID (the proxy runs in-process, so there's
        no child PID).
        """
        with self._lock:
            if self.is_running():
                return os.getpid()
            # If a previous engine thread is still winding down, leave it —
            # the daemon joiner will reap it. Start a fresh thread now.
            self._stopping = False
            # Load (or generate) the config so we know which port/host/secret
            # the engine should listen on.
            self._cfg = _ensure_config(self.data_dir)
            self.log(
                f"[TG] Starting embedded proxy on {self._cfg.host}:{self._cfg.port}..."
            )
            self._started = True
            self._thread = threading.Thread(
                target=self._run_thread, name="tg-ws-proxy", daemon=True
            )
            self._thread.start()
            return os.getpid()

    def _run_thread(self) -> None:
        """Background thread entry point — runs the asyncio engine.

        Critical: we capture the loop in a LOCAL variable and only clear the
        shared ``self._loop`` / ``self._stop_event`` if THIS thread still owns
        the slot. Otherwise a rapid stop+start (e.g. ``tg_rotate_secret``)
        would let the old thread's finally block clobber the new engine's
        state — the runner would lose all references to the running engine.
        """
        loop: Optional[asyncio.AbstractEventLoop] = None
        my_thread = threading.current_thread()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            with self._lock:
                self._loop = loop
                self._stop_event = asyncio.Event()
                my_stop_event = self._stop_event
            loop.run_until_complete(self._run_async(my_stop_event))
        except Exception as exc:
            self.log(f"[TG] Engine crashed: {exc}")
        finally:
            # Cancel any leftover tasks before closing the loop — otherwise
            # asyncio prints "Task was destroyed but it is pending!" + a
            # stack trace when the loop closes. Use the LOCAL loop, never
            # self._loop (may belong to a newer engine after a restart).
            try:
                if loop is not None:
                    pending = asyncio.all_tasks(loop)
                    for t in pending:
                        t.cancel()
                    if pending:
                        try:
                            loop.run_until_complete(
                                asyncio.gather(*pending, return_exceptions=True)
                            )
                        except Exception:
                            pass
                    loop.close()
            except Exception:
                pass
            # Only clear shared state if THIS thread still owns the slot —
            # a newer engine may already have replaced us.
            with self._lock:
                if self._thread is my_thread:
                    self._loop = None
                    self._stop_event = None
                    self._started = False
            self.log("[TG] Engine stopped.")
            cb = self._on_exit
            if cb is not None and not self._stopping:
                try:
                    cb(0)
                except Exception:
                    pass

    async def _run_async(self, stop_event: asyncio.Event) -> None:
        """Run the upstream ``_run`` coroutine with our config applied.

        ``stop_event`` is the asyncio.Event created by this run; the engine
        watches it and exits cleanly when set.
        """
        try:
            pkg = _engine_package_name(self.data_dir)
            engine = importlib.import_module(pkg + ".tg_ws_proxy")
            cfg_mod = importlib.import_module(pkg + ".config")
            proxy_config = cfg_mod.proxy_config
            parse_dc_ip_list = cfg_mod.parse_dc_ip_list
        except Exception as exc:
            self.log(f"[TG] Cannot import engine: {exc}")
            return

        cfg = self._cfg
        if cfg is None:
            cfg = _ensure_config(self.data_dir)
            self._cfg = cfg

        # Configure the engine before starting the loop. These attributes match
        # what engine.main() sets when run as a CLI.
        proxy_config.port = cfg.port
        proxy_config.host = cfg.host
        proxy_config.secret = cfg.secret
        try:
            # Follow upstream tg-ws-proxy semantics: empty DC->IP stays empty
            # and lets the fallback chain decide. Users can opt into the full
            # built-in map with "auto" or set explicit DC:IP values.
            proxy_config.dc_redirects = _effective_dc_redirects(pkg, parse_dc_ip_list, self._dc_ips)
        except Exception:
            proxy_config.dc_redirects = {}
        # Sensible defaults for the rest.
        proxy_config.buffer_size = 256 * 1024
        proxy_config.pool_size = 4
        proxy_config.fallback_cfproxy = True
        proxy_config.cfproxy_user_domains = list(self._cfproxy_domains)
        proxy_config.cfproxy_worker_domains = list(self._cfworker_domains)
        proxy_config.fake_tls_domain = ""
        proxy_config.proxy_protocol = False
        # v1.8.0 upstream rolled back WS keepalive because reports showed it
        # caused more problems. Do not force the old 30s behavior from our
        # wrapper; disable if the engine exposes the setting.
        if hasattr(proxy_config, "ws_keepalive_interval"):
            proxy_config.ws_keepalive_interval = 0.0

        # Route engine log output to our GUI log. Attach the handler to the
        # engine's OWN logger (not the root logger) so we don't capture
        # unrelated libraries' INFO messages.
        try:
            engine_log = logging.getLogger("tg-mtproto-proxy")
            deduper = _TGGuiLogDeduper(min_interval=60.0)
            # If an older GUI handler already exists (after stop/start), force
            # it back to INFO. Older/runtime-updated engines may emit fallback
            # failures at INFO/WARNING, so the handler itself also deduplicates.
            for old_h in list(engine_log.handlers):
                if getattr(old_h, "_tg_gui", False):
                    old_h.setLevel(logging.INFO)
            if not any(getattr(h, "_tg_gui", False) for h in engine_log.handlers):
                class _GuiHandler(logging.Handler):
                    def __init__(self, cb, dedupe):
                        super().__init__()
                        self._cb = cb
                        self._dedupe = dedupe

                    def emit(self, record):
                        try:
                            raw = record.getMessage()
                            ok, msg = self._dedupe.should_emit(raw)
                            if ok:
                                self._cb("[TG] " + msg)
                        except Exception:
                            pass

                h = _GuiHandler(self.log, deduper)
                h._tg_gui = True  # type: ignore[attr-defined]
                h.setLevel(logging.INFO)
                fmt = logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", "%H:%M:%S")
                h.setFormatter(fmt)
                engine_log.addHandler(h)
            # Keep fallback debug noise out of the user-facing GUI log.
            engine_log.setLevel(logging.INFO)
            # Don't double-route to the root logger (which would also log to
            # stderr in dev) — keep the engine's output isolated.
            engine_log.propagate = False
            logging.getLogger("asyncio").setLevel(logging.WARNING)
        except Exception:
            pass

        self.log(f"[TG] Listening on {cfg.host}:{cfg.port} (secret: {cfg.secret[:8]}...)")
        try:
            await engine._run(stop_event)
        except Exception as exc:
            self.log(f"[TG] _run() error: {exc}")

    def stop(self) -> None:
        """Non-blocking stop. Signals the engine to shut down and returns
        immediately. ``is_running()`` will return False right away. A daemon
        "joiner" thread waits for the engine thread to finish (max 5s) so we
        don't leak resources but the UI thread never blocks."""
        with self._lock:
            if not self._started and self._thread is None:
                # Nothing to stop.
                return
            self._stopping = True
            # Signal the asyncio loop to stop. The engine's _run() coroutine
            # watches this event and returns cleanly.
            ev = self._stop_event
            loop = self._loop
            if ev is not None and loop is not None and loop.is_running():
                try:
                    loop.call_soon_threadsafe(ev.set)
                except Exception:
                    pass
            # Spawn a daemon "joiner" so the GUI thread doesn't block on
            # thread.join(timeout=5). The joiner cleans up _thread/_loop after
            # the engine thread exits.
            thread = self._thread
            if thread is not None and thread.is_alive() and (
                self._joiner is None or not self._joiner.is_alive()
            ):
                self._joiner = threading.Thread(
                    target=self._join_engine, args=(thread,), name="tg-ws-proxy-joiner", daemon=True
                )
                self._joiner.start()
            # Mark stopped immediately so is_running() reflects user intent.
            self._started = False

    def _join_engine(self, thread: threading.Thread) -> None:
        """Daemon thread that waits for the engine thread to finish, then
        clears the references. Bounded by ``_JOIN_TIMEOUT``."""
        try:
            thread.join(timeout=5.0)
        except Exception:
            pass
        with self._lock:
            if self._thread is thread:
                self._thread = None
                self._loop = None
                self._stop_event = None
            self._joiner = None

    def wait_for_stop(self, timeout: float = 6.0) -> bool:
        """Block until the engine thread has fully exited, or timeout.

        Used by quit_app to make sure the engine is really dead before the
        process exits (otherwise asyncio may print warnings on shutdown).
        Returns True if the thread exited within the timeout.
        """
        with self._lock:
            thread = self._thread
            joiner = self._joiner
        if thread is None:
            return True
        # If the joiner is still alive, wait on it; it will clear _thread.
        if joiner is not None and joiner.is_alive():
            joiner.join(timeout=timeout)
        with self._lock:
            return self._thread is None
