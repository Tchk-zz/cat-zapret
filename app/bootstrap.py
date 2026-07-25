"""First-run setup: fetch the Flowseal zapret bundle and seed user lists.

This turns the GUI into a standalone app. The user installs one program and on
first launch it downloads everything winws.exe needs (bin/, lists/, strategy
.bat files) straight from the official Flowseal repo — nothing has to be copied
into a zapret folder by hand.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from . import updater

# Placeholder user lists that Flowseal's service.bat creates on first run.
# winws.exe aborts with "cannot access ipset file ...-user.txt" if they are
# missing, so we create them ourselves before launching any strategy.
USER_LISTS = {
    "ipset-exclude-user.txt": "203.0.113.113/32\n",
    "list-general-user.txt": "domain.example.abc\n",
    "list-exclude-user.txt": "domain.example.abc\n",
}

# Reference definition of the built-in Roblox profile, keyed by display name
# -> {description, args}. NOTE: this is no longer seeded into
# <zapret>/custom_strategies -- Roblox is an optional "combine" toggle in the
# UI, and ensure_builtin_strategies() actively deletes legacy seeded copies.
# The dict is kept because the UI and tests read the description/args from it.
# Roblox was blocked in RF on 2025-12-03; the website loads over HTTPS (domain)
# but joining a place is raw UDP to game-server IPs (ports 49152-65535, no SNI),
# so a domain bypass cannot touch it. This profile (from Flowseal's RobloxFix)
# desyncs the Roblox game-server IP ranges directly via --ipset-ip.
#
# The profile ships as ``roblox_profile.json`` at the project root so users
# can edit IP ranges when Roblox adds new subnets WITHOUT rebuilding the exe.
# The string below is the FALLBACK used when the JSON file is missing or
# unreadable (e.g. an older copy of the app was upgraded in place and the JSON
# didn't make it into the install).
_ROBLOX_FIX_ARGS = (
    "--wf-tcp=443 --wf-udp=443,49152-65535 "
    "--filter-udp=49152-65535 "
    "--ipset-ip=103.140.28.0/23,128.116.0.0/17,141.193.3.0/24,205.201.62.0/24,"
    "2620:2b:e000::/48,2620:135:6000::/40,2620:135:6004::/48,2620:135:6007::/48,"
    "2620:135:6008::/48,2620:135:6009::/48,2620:135:600a::/48,2620:135:600b::/48,"
    "2620:135:600c::/48,2620:135:600d::/48,2620:135:600e::/48,2620:135:6041::/48 "
    "--dpi-desync=fake --dpi-desync-fake-unknown-udp=0x00 "
    "--dpi-desync-any-protocol --dpi-desync-cutoff=n2 --new "
    "--filter-tcp=443 "
    "--hostlist-domains=roblox.com,rbxcdn.com,amazonaws.com,cloudflare-ech.com,voidstrapweb.netlify.app "
    "--dpi-desync=fake,multisplit --dpi-desync-fake-tls-mod=rnd,dupsid,sni=vk.me "
    "--dpi-desync-split-pos=1,host --dpi-desync-fooling=badseq "
    "--dpi-desync-badseq-increment=0 --dpi-desync-badack-increment=1"
)

# Public alias: callers should use ROBLOX_FIX_ARGS (no underscore). The
# underscore-prefixed name is kept only for backwards-compat with any code
# that imported it before this rename.
ROBLOX_FIX_ARGS = _ROBLOX_FIX_ARGS


def _roblox_profile_path() -> Optional[Path]:
    """Locate the ``roblox_profile.json`` shipped with the app.

    Looked up at:
      * ``sys._MEIPASS/roblox_profile.json`` (PyInstaller bundle)
      * ``<project_root>/roblox_profile.json`` (running from source)
    Returns None if not found.
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "roblox_profile.json")
    candidates.append(Path(__file__).resolve().parent.parent / "roblox_profile.json")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def load_roblox_profile() -> tuple[str, str]:
    """Load the Roblox bypass profile from ``roblox_profile.json``.

    Returns ``(args_string, description)``. Falls back to the hardcoded
    ``ROBLOX_FIX_ARGS`` + the standard description if the JSON is missing,
    unreadable, or doesn't contain the expected keys — so a corrupted or
    hand-edited-but-broken JSON can never break the GUI.

    The args string is NOT pre-tokenized: callers pass it through
    ``strategy_manager._tokenize_args`` (same path as a .bat line) so the
    same quoting/escaping rules apply.
    """
    fallback_desc = (
        "\u0421\u043f\u0435\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u0434\u043b\u044f Roblox: \u043e\u0431\u0445\u043e\u0434 \u0438\u0433\u0440\u043e\u0432\u044b\u0445 "
        "\u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u043f\u043e IP (UDP 49152-65535) + \u0441\u0430\u0439\u0442 \u043f\u043e \u0434\u043e\u043c\u0435\u043d\u0430\u043c. "
        "\u0417\u0430\u043f\u0443\u0441\u043a\u0430\u0439\u0442\u0435 \u0435\u0451, \u043a\u043e\u0433\u0434\u0430 \u0438\u0433\u0440\u0430\u0435\u0442\u0435 \u0432 Roblox."
    )
    p = _roblox_profile_path()
    if p is None:
        return ROBLOX_FIX_ARGS, fallback_desc
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        args = data.get("args") or ROBLOX_FIX_ARGS
        desc = data.get("description") or fallback_desc
        if not isinstance(args, str) or not args.strip():
            args = ROBLOX_FIX_ARGS
        if not isinstance(desc, str):
            desc = fallback_desc
        return args, desc
    except (OSError, ValueError):
        return ROBLOX_FIX_ARGS, fallback_desc


BUILTIN_STRATEGIES = {
    "Roblox": {
        "description": (
            "\u0421\u043f\u0435\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u0434\u043b\u044f Roblox: \u043e\u0431\u0445\u043e\u0434 \u0438\u0433\u0440\u043e\u0432\u044b\u0445 "
            "\u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432 \u043f\u043e IP (UDP 49152-65535) + \u0441\u0430\u0439\u0442 \u043f\u043e \u0434\u043e\u043c\u0435\u043d\u0430\u043c. "
            "\u0417\u0430\u043f\u0443\u0441\u043a\u0430\u0439\u0442\u0435 \u0435\u0451, \u043a\u043e\u0433\u0434\u0430 \u0438\u0433\u0440\u0430\u0435\u0442\u0435 \u0432 Roblox."
        ),
        "args": _ROBLOX_FIX_ARGS,
    },
}


def ensure_builtin_strategies(zapret_dir: Path) -> None:
    """Clean up legacy seeded strategies.

    Roblox is an optional combine toggle in the UI now, not a standalone
    strategy. Remove any previously seeded Roblox strategy files so it no
    longer appears in the strategy list.
    """
    cdir = Path(zapret_dir) / "custom_strategies"
    if not cdir.exists():
        return
    for stale in ("Roblox.json", "Roblox_Fix.json"):
        try:
            p = cdir / stale
            if p.exists():
                p.unlink()
        except OSError:
            pass


def is_installed(zapret_dir: Path) -> bool:
    """True if a usable zapret install exists in *zapret_dir*."""
    try:
        if not (zapret_dir / "bin" / "winws.exe").exists():
            return False
        # A working install needs winws.exe plus a strategy source: our own
        # strategies.json catalog (the normal state once .bat are converted and
        # deleted) or, on a fresh download, the Flowseal .bat themselves.
        if (zapret_dir / "strategies.json").exists():
            return True
        return any(zapret_dir.glob("*.bat"))
    except OSError:
        return False


def ensure_user_lists(zapret_dir: Path) -> None:
    """Create the placeholder ``*-user.txt`` files if they don't exist."""
    lists = zapret_dir / "lists"
    try:
        lists.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for name, content in USER_LISTS.items():
        path = lists / name
        if not path.exists():
            try:
                path.write_text(content, encoding="utf-8")
            except OSError:
                pass


def bundled_zapret_dir() -> Optional[Path]:
    """Return the zapret bundle embedded inside the app, if present.

    When frozen by PyInstaller the bundle is extracted to ``sys._MEIPASS/zapret``.
    When running from source it lives in ``<project>/vendor/zapret`` (filled by
    build.bat before packaging).
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "zapret")
    root = Path(__file__).resolve().parent.parent
    candidates.append(root / "vendor" / "zapret")
    for c in candidates:
        try:
            if (c / "bin" / "winws.exe").exists() and any(c.glob("*.bat")):
                return c
        except OSError:
            continue
    return None


def _install_from_bundle(src: Path, dst: Path) -> int:
    """Copy the embedded bundle into the working dir. Returns file count."""
    protected = {
        "config.json",
        "custom_strategies",
        updater.INSTALLED_MARKER,
        updater.INSTALLED_SHA256_MARKER,
    }
    count = 0
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        try:
            rel = item.relative_to(src)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in protected:
            continue
        target = dst / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
        except OSError:
            pass
    return count


def _finalize_install(zapret_dir: Path) -> None:
    """Convert freshly downloaded Flowseal .bat into our catalog and delete the
    .bat. If no .bat are present, make sure a catalog exists (seeded from the
    copy bundled with the app)."""
    from . import strategy_catalog

    try:
        if any(Path(zapret_dir).glob("*.bat")):
            strategy_catalog.rebuild_from_bats(zapret_dir, delete_bats=True)
        else:
            strategy_catalog.ensure_catalog(zapret_dir)
    except Exception:
        pass


def ensure_zapret(
    zapret_dir: Path,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """Download + extract the latest Flowseal release if not already present.

    Returns ``"ok"`` on success, otherwise a human-readable error message.
    """
    def report(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    if is_installed(zapret_dir):
        ensure_user_lists(zapret_dir)
        return "ok"

    # Preferred path: install the bundle embedded inside the app. This is
    # offline and instant \u2014 no dependency on any zapret folder on the PC.
    bundle = bundled_zapret_dir()
    if bundle is not None:
        report("\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430 \u0432\u0441\u0442\u0440\u043e\u0435\u043d\u043d\u043e\u0433\u043e \u043a\u043e\u043c\u043f\u043b\u0435\u043a\u0442\u0430 zapret...")
        try:
            zapret_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0430\u043f\u043a\u0443 \u0434\u043b\u044f zapret: " + str(exc)
        _install_from_bundle(bundle, zapret_dir)
        ensure_user_lists(zapret_dir)
        _finalize_install(zapret_dir)
        if is_installed(zapret_dir):
            report("\u0413\u043e\u0442\u043e\u0432\u043e.")
            return "ok"

    report("\u041f\u043e\u0438\u0441\u043a \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0433\u043e \u0440\u0435\u043b\u0438\u0437\u0430 zapret...")
    rel = updater.latest_release()
    if rel is None:
        return (
            "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0440\u0435\u043b\u0438\u0437 zapret \u0441 GitHub. "
            "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043a \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442\u0443 \u0438 \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u0441\u043d\u043e\u0432\u0430."
        )

    try:
        zapret_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0430\u043f\u043a\u0443 \u0434\u043b\u044f zapret: " + str(exc)

    report("\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 zapret " + (rel.tag or "") + "...")
    msg = updater.download_and_apply(rel, zapret_dir, on_status=report)
    ensure_user_lists(zapret_dir)
    _finalize_install(zapret_dir)

    if not is_installed(zapret_dir):
        return "\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u043b\u0430\u0441\u044c, \u043d\u043e winws.exe \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d. " + msg
    report("\u0413\u043e\u0442\u043e\u0432\u043e.")
    return "ok"
