"""Check the Flowseal GitHub repo for newer strategy bundles and update them.

We only touch zapret content (strategies / bin / lists). Custom strategies live
in ``custom_strategies/`` and are never overwritten. The installed version is
recorded in a marker file so we never offer the same update twice.

Integrity check
---------------
Every downloaded zip is verified against the SHA-256 digest advertised by the
GitHub release API (``asset.digest``). If GitHub doesn't publish a digest
(source zipball has none), we compute and store our own digest next to the
installed marker file (``.zapret_gui_sha256``) so a later tamper/incomplete
download can still be detected on re-install. If the digest doesn't match we
refuse to extract and return a clear error message instead of silently
launching a corrupted ``winws.exe``.
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

REPO = "Flowseal/zapret-discord-youtube"
LATEST_API = "https://api.github.com/repos/" + REPO + "/releases/latest"
RELEASES_URL = "https://github.com/" + REPO + "/releases"

# Our own marker, written after a confirmed update. This is the source of truth
# for "what is installed" — the previous version compared against a file that
# was never written, so it always thought an update was available.
INSTALLED_MARKER = ".zapret_gui_version"
# Stored SHA-256 of the LAST zip we successfully extracted. Used to detect
# a re-download of the same release with different bytes (MITM / corruption).
INSTALLED_SHA256_MARKER = ".zapret_gui_sha256"
# Version files that some repo archives ship with (fallback only).
REPO_VERSION_FILES = ("version.txt", ".version", "version")


REBOOT_PENDING_MARKER = ".zapret_gui_reboot_required"
IS_WINDOWS = sys.platform.startswith("win")
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def _run_quiet(args) -> None:
    """Best-effort helper for releasing Windows locks before update."""
    if not IS_WINDOWS:
        return
    try:
        subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_NO_WINDOW,
            timeout=5,
        )
    except Exception:
        pass


def _release_windivert_locks() -> None:
    """Try to unload common winws/WinDivert holders before replacing files.

    Even when the GUI says zapret is off, the WinDivert kernel driver can stay
    loaded for a short time or be held by a leftover service. Stopping these is
    safe: winws recreates/loads WinDivert again on the next start.
    """
    if not IS_WINDOWS:
        return
    _run_quiet(["taskkill", "/F", "/IM", "winws.exe", "/T"])
    # Flowseal/winws versions use different service names across WinDivert
    # releases. Stop/delete is best-effort; failures are ignored.
    for name in ("WinDivert", "WinDivert14", "WinDivert1.4", "windivert"):
        _run_quiet(["sc", "stop", name])
    time.sleep(0.4)
    for name in ("WinDivert", "WinDivert14", "WinDivert1.4", "windivert"):
        _run_quiet(["sc", "delete", name])
    time.sleep(0.2)


def _schedule_replace_on_reboot(target: Path, data: bytes) -> bool:
    """Write a pending file and ask Windows to replace target on reboot.

    Loaded driver .sys files can remain locked after winws/AV are stopped. In
    that case failing the update forever is bad UX; scheduling a MoveFileEx
    replacement is the correct Windows-native fallback.
    """
    if not IS_WINDOWS:
        return False
    try:
        pending = target.with_name(target.name + ".zapretgui.new")
        pending.write_bytes(data)
        import ctypes
        MOVEFILE_REPLACE_EXISTING = 0x1
        MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
        ok = ctypes.windll.kernel32.MoveFileExW(
            str(pending),
            str(target),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_DELAY_UNTIL_REBOOT,
        )
        return bool(ok)
    except Exception:
        return False


@dataclass
class ReleaseInfo:
    tag: str
    name: str
    zip_url: Optional[str]
    html_url: str
    # SHA-256 of the asset's bytes, as reported by GitHub. None for source
    # zipballs (GitHub doesn't compute a digest for those) — in that case
    # we accept any bytes but record our own hash for future tamper detection.
    digest: Optional[str] = None
    # Whether ``digest`` came from GitHub (True) or was computed locally
    # after a successful download (False). Affects how strict we are on
    # re-downloads: GitHub-provided digests are mandatory; local ones are
    # informational only.
    digest_verified: bool = False


def _norm(tag: str) -> str:
    return (tag or "").strip().lstrip("vV").strip()


def local_version(zapret_dir: Path) -> str:
    """Return the installed strategy version, '' if unknown."""
    marker = zapret_dir / INSTALLED_MARKER
    if marker.exists():
        try:
            return marker.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            pass
    for name in REPO_VERSION_FILES:
        for candidate in (zapret_dir / name, zapret_dir / ".service" / name):
            if candidate.exists():
                try:
                    return candidate.read_text(encoding="utf-8", errors="ignore").strip()
                except OSError:
                    pass
    return ""


def save_local_version(zapret_dir: Path, tag: str) -> None:
    """Record the installed version so we don't re-offer the same update."""
    try:
        (zapret_dir / INSTALLED_MARKER).write_text(_norm(tag), encoding="utf-8")
    except OSError:
        pass


def latest_release(timeout: float = 10.0) -> Optional[ReleaseInfo]:
    if requests is None:
        return None
    try:
        r = requests.get(
            LATEST_API,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    zip_url = data.get("zipball_url")
    digest: Optional[str] = None
    digest_verified = False
    for asset in data.get("assets", []) or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(".zip"):
            zip_url = asset.get("browser_download_url")
            # GitHub populates `digest` as "sha256:<hex>" for release assets
            # (https://docs.github.com/en/rest/releases/assets). We strip the
            # algorithm prefix and keep just the hex digest for comparison.
            raw_digest = asset.get("digest") or ""
            if raw_digest.startswith("sha256:"):
                digest = raw_digest[len("sha256:"):].strip().lower()
                digest_verified = bool(digest)
            break
    return ReleaseInfo(
        tag=data.get("tag_name", ""),
        name=data.get("name", data.get("tag_name", "")),
        zip_url=zip_url,
        html_url=data.get("html_url", RELEASES_URL),
        digest=digest,
        digest_verified=digest_verified,
    )


def update_available(zapret_dir: Path) -> Optional[ReleaseInfo]:
    """Return a release only if it differs from the installed version."""
    rel = latest_release()
    if rel is None or not rel.tag:
        return None
    cur = _norm(local_version(zapret_dir))
    if not cur:
        # Baseline unknown: do NOT silently mark the latest release as installed.
        # That made auto-update look "strange": a stale/unknown local bundle
        # would be treated as current forever until the user forced a full
        # update. Offer the latest release so the user can install it.
        return rel
    if _norm(rel.tag) == cur:
        return None
    return rel


def _common_root(names) -> str:
    """Return the single top-level folder shared by all entries, or ''.

    GitHub *source* zipballs nest everything under one folder (strip it), but
    release *asset* zips put bin/ lists/ *.bat at the root (don't strip).

    We must NOT strip a top-level name that is itself a known content folder
    (e.g. ``bin/``). Otherwise a future release that ships only ``bin/winws.exe``
    would have its top folder stripped and the file extracted to the wrong path.
    """
    # Known top-level content folders shipped by Flowseal's zapret bundle.
    _CONTENT_TOPS = {"bin", "lists", "utils", "corz", "opt", "src", "docs"}
    norm = [n.replace("\\", "/") for n in names if n and not n.startswith("__MACOSX")]
    if not norm:
        return ""
    tops = {n.split("/")[0] for n in norm}
    if len(tops) == 1:
        only = next(iter(tops))
        # Don't treat a content folder as a "nesting root" — that would strip
        # the very prefix we need to keep.
        if only.lower() in _CONTENT_TOPS:
            return ""
        if any(n.startswith(only + "/") for n in norm):
            return only + "/"
    return ""


def _sha256_hex(data: bytes) -> str:
    """Compute the SHA-256 hex digest of ``data`` (lowercase, no separator)."""
    return hashlib.sha256(data).hexdigest()


def _load_installed_sha256(zapret_dir: Path) -> str:
    """Return the SHA-256 of the last zip we successfully extracted, or ''."""
    p = zapret_dir / INSTALLED_SHA256_MARKER
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip().lower()
        except OSError:
            pass
    return ""


def _save_installed_sha256(zapret_dir: Path, digest: str) -> None:
    try:
        (zapret_dir / INSTALLED_SHA256_MARKER).write_text(
            digest.lower(), encoding="utf-8"
        )
    except OSError:
        pass


def download_and_apply(rel: ReleaseInfo, zapret_dir: Path, timeout: float = 60.0, on_status=None) -> str:
    """Download the release zip, verify its SHA-256, and extract it in place.

    Integrity rules:
      * If GitHub advertised a digest (``rel.digest_verified == True``), the
        downloaded bytes MUST match. A mismatch is treated as a corrupted or
        tampered download — we refuse to extract and return a clear error.
      * If GitHub didn't advertise a digest (source zipball), we still compute
        and store our own hash so a re-install of the SAME tag with DIFFERENT
        bytes is caught — that's the strongest signal a MITM/proxy tampered
        with the bytes between installs.
    """
    if requests is None:
        return "\u041c\u043e\u0434\u0443\u043b\u044c requests \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d."
    if not rel.zip_url:
        return "\u0423 \u0440\u0435\u043b\u0438\u0437\u0430 \u043d\u0435\u0442 zip-\u0430\u0440\u0445\u0438\u0432\u0430."
    if on_status:
        on_status("\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 " + (rel.tag or "zapret") + "...")
    try:
        r = requests.get(rel.zip_url, timeout=timeout)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438: " + str(exc)

    # --- SHA-256 integrity check ---
    actual_digest = _sha256_hex(r.content)
    if rel.digest_verified and rel.digest:
        # GitHub gave us a digest — mandatory match.
        if actual_digest.lower() != rel.digest.lower():
            return (
                "\u041d\u0430\u0440\u0443\u0448\u0435\u043d\u0430 \u0446\u0435\u043b\u043e\u0441\u0442\u043d\u043e\u0441\u0442\u044c \u0430\u0440\u0445\u0438\u0432\u0430: "
                "SHA-256 \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442. "
                "\u0412\u043e\u0437\u043c\u043e\u0436\u043d\u043e, \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u0431\u044b\u043b\u0430 \u043f\u043e\u0432\u0440\u0435\u0436\u0434\u0435\u043d\u0430 "
                "\u0438\u043b\u0438 \u043f\u0435\u0440\u0435\u0445\u0432\u0430\u0447\u0435\u043d\u0430. \u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u043f\u043e\u043f\u044b\u0442\u043a\u0443."
            )
    else:
        # GitHub gave no digest (source zipball). Still catch a tampered
        # re-download of the SAME tag by comparing to the hash we stored last
        # time we extracted this exact tag.
        prev = _load_installed_sha256(zapret_dir)
        prev_tag = local_version(zapret_dir)
        if prev and prev_tag and _norm(prev_tag) == _norm(rel.tag) and prev != actual_digest.lower():
            return (
                "\u041f\u0440\u0435\u0434\u0443\u043f\u0440\u0435\u0436\u0434\u0435\u043d\u0438\u0435: \u0430\u0440\u0445\u0438\u0432 \u0442\u043e\u0433\u043e \u0436\u0435 \u0440\u0435\u043b\u0438\u0437\u0430 "
                "\u0441\u043a\u0430\u0447\u0430\u043b\u0441\u044f \u0441 \u0434\u0440\u0443\u0433\u0438\u043c SHA-256, \u0447\u0435\u043c \u0432 \u043f\u0440\u043e\u0448\u043b\u044b\u0439 \u0440\u0430\u0437. "
                "\u0412\u043e\u0437\u043c\u043e\u0436\u043d\u043e, \u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440 \u043f\u043e\u0434\u043c\u0435\u043d\u044f\u0435\u0442 \u0442\u0440\u0430\u0444\u0438\u043a. "
                "\u0415\u0441\u043b\u0438 \u0432\u044b \u0434\u043e\u0432\u0435\u0440\u044f\u0435\u0442\u0435 \u0441\u0435\u0442\u0438, "
                "\u0443\u0434\u0430\u043b\u0438\u0442\u0435 \u0444\u0430\u0439\u043b " + INSTALLED_SHA256_MARKER + " \u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435."
            )

    _release_windivert_locks()

    protected = {"config.json", "custom_strategies", INSTALLED_MARKER, INSTALLED_SHA256_MARKER, REBOOT_PENDING_MARKER}
    extracted = 0
    skipped = 0
    skipped_paths = []
    # If any of these are skipped, the update is not safe to call successful:
    # the core engine/driver may remain from the old release.
    critical_names = {
        "bin/winws.exe",
        "bin/WinDivert.dll",
        "bin/WinDivert64.sys",
        "bin/WinDivert32.sys",
        "bin/cygwin1.dll",
    }
    critical_skipped = []
    pending_reboot = []

    def _record_skip(rel_path: str) -> None:
        nonlocal skipped
        skipped += 1
        skipped_paths.append(rel_path)
        rel_norm = rel_path.replace("\\", "/")
        if rel_norm in critical_names or rel_norm.startswith("bin/"):
            critical_skipped.append(rel_norm)

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            # GitHub zipball nests everything under a top folder — strip it.
            root = _common_root(names)
            for member in names:
                norm = member.replace("\\", "/")
                rel_path = norm[len(root):] if root and norm.startswith(root) else norm
                if not rel_path or member.endswith("/"):
                    continue
                top = rel_path.split("/")[0]
                if top in protected:
                    continue
                rel_parts = Path(rel_path).parts
                # Security: never allow a malicious/corrupt archive entry to
                # escape zapret_dir (Zip Slip via ../ or absolute paths).
                if Path(rel_path).is_absolute() or ".." in rel_parts:
                    _record_skip(rel_path)
                    if on_status:
                        on_status("Пропущен небезопасный путь в архиве: " + rel_path)
                    continue
                target = zapret_dir / rel_path
                # A locked/in-use file (e.g. winws.exe/service/AV holding it)
                # must NOT crash the updater. But if a critical bin/* file is
                # skipped, report a partial update instead of a success.
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src:
                        data = src.read()
                    try:
                        with open(target, "wb") as dst:
                            dst.write(data)
                        extracted += 1
                    except OSError:
                        rel_norm = rel_path.replace("\\", "/")
                        # Only kernel drivers (.sys) genuinely require a reboot
                        # to be swapped: Windows keeps a loaded WinDivert driver
                        # locked even after every zapret process is gone.
                        # A locked winws.exe means something is still RUNNING,
                        # and staging it for reboot would hide a real problem
                        # behind a "success" message — report it as partial.
                        if rel_norm.lower().endswith(".sys") and _schedule_replace_on_reboot(target, data):
                            pending_reboot.append(rel_norm)
                            extracted += 1
                            if on_status:
                                on_status("Файл занят, замена запланирована после перезагрузки: " + rel_path)
                        else:
                            raise
                except OSError:
                    _record_skip(rel_path)
                    if on_status:
                        on_status("Пропущен занятый файл: " + rel_path)
    except zipfile.BadZipFile:
        return "Скачанный архив повреждён, попробуйте ещё раз."
    except Exception as exc:  # noqa: BLE001
        return "Ошибка распаковки: " + str(exc)

    if pending_reboot:
        try:
            (zapret_dir / REBOOT_PENDING_MARKER).write_text(rel.tag, encoding="utf-8")
        except OSError:
            pass
        files = ", ".join(pending_reboot[:6])
        if len(pending_reboot) > 6:
            files += ", ..."
        # The new driver bytes are staged: Windows will swap them at boot. The
        # release is deliberately NOT marked as installed, so the update is
        # re-verified after the reboot.
        return (
            "Обновление подготовлено до " + rel.tag + ": распаковано "
            + str(extracted)
            + " файлов.\n\nНекоторые драйверные файлы были заняты и будут заменены Windows при следующей перезагрузке: "
            + files
            + ".\n\nПерезагрузите компьютер, затем запустите приложение снова."
        )

    # If core binaries were not replaced, do not rebuild/mark the release as
    # installed. Otherwise the UI would say "updated" while winws/driver are
    # still old or mixed-version.
    if critical_skipped:
        crit = ", ".join(critical_skipped[:6])
        if len(critical_skipped) > 6:
            crit += ", ..."
        return (
            "Обновление выполнено частично до " + rel.tag + ": распаковано "
            + str(extracted) + " файлов, но не удалось заменить важные файлы: "
            + crit + ".\n\nЗакройте zapret, остановите службу zapret/процессы winws.exe "
            "или добавьте папку zapret в исключения антивируса, затем повторите обновление."
        )

    # Convert the freshly extracted Flowseal .bat recipes into our own catalog,
    # then delete the .bat -- the app runs winws.exe straight from the catalog.
    try:
        from . import strategy_catalog
        strategy_catalog.rebuild_from_bats(zapret_dir, delete_bats=True)
    except Exception:
        pass

    # Record the version so the same update isn't offered again.
    save_local_version(zapret_dir, rel.tag)
    # Store the digest so a re-download of the SAME tag with DIFFERENT bytes
    # (MITM / partial download / corrupted cache) is caught next time.
    _save_installed_sha256(zapret_dir, actual_digest)
    msg = "Обновлено до " + rel.tag + ": распаковано " + str(extracted) + " файлов."
    if skipped:
        shown = ", ".join(skipped_paths[:6])
        if len(skipped_paths) > 6:
            shown += ", ..."
        msg += " Пропущено " + str(skipped) + " неключевых файлов: " + shown + "."
    return msg
