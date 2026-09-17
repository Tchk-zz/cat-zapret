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
import json
import os
import stat
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .applog import get_logger

_log = get_logger("zapret-update")

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
MANIFEST_FILENAME = ".zapret_gui_manifest.json"
MANIFEST_VERSION = 1

# User-owned files must survive every full bundle update, even if a future
# upstream archive starts shipping placeholders with the same names.
_PRESERVED_RUNTIME_PATHS = {"utils/game_filter.enabled"}

# Defensive archive limits. The official bundle is only a few MiB; these
# generous caps reject zip bombs/corrupt releases before any file is replaced.
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 4096
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024

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
        # Best-effort helper command; the update itself can still succeed.
        _log.warning("helper command failed", exc_info=True)


def _release_windivert_locks(on_status=None) -> None:
    """Stop winws/WinDivert holders of a file we failed to replace.

    Called ONLY after a real write error: the WinDivert kernel driver can stay
    loaded for a short time or be held by a leftover service. Stopping is safe
    (winws loads WinDivert again on the next start), but `sc delete` is not:
    it removed the service registration outright, which could break a running
    system zapret service, so it is no longer done here.
    """
    if not IS_WINDOWS:
        return
    if on_status:
        on_status("Файлы заняты: останавливаю winws.exe и драйвер WinDivert...")
    _log.info("releasing winws/WinDivert locks before retrying a locked file")
    _run_quiet(["taskkill", "/F", "/IM", "winws.exe", "/T"])
    # Flowseal/winws versions use different service names across WinDivert
    # releases. Stopping is best-effort; failures are ignored.
    for name in ("WinDivert", "WinDivert14", "WinDivert1.4", "windivert"):
        _run_quiet(["sc", "stop", name])
    time.sleep(0.6)


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
    # Release assets intentionally omit Flowseal's hidden .service directory.
    # Keep the tag source zipball so HOSTS/IPSet service data can be merged into
    # the otherwise verified official bundle.
    source_zip_url: Optional[str] = None


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
        # Without this marker the same update is offered again next time.
        _log.warning(
            "could not record the installed strategy version in %s",
            zapret_dir / INSTALLED_MARKER,
            exc_info=True,
        )


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
        source_zip_url=data.get("zipball_url"),
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
    _CONTENT_TOPS = {".service", "bin", "lists", "utils", "corz", "opt", "src", "docs"}
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


def _normalise_rel_path(rel_path: str) -> str:
    """Return a slash-normalised relative archive path."""
    rel = (rel_path or "").replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _is_preserved_path(rel_path: str) -> bool:
    """True for app/user-owned paths that an upstream archive cannot replace."""
    rel = _normalise_rel_path(rel_path)
    if not rel:
        return True
    parts = rel.split("/")
    top = parts[0].casefold()
    internal = {
        "config.json",
        "custom_strategies",
        "strategies.json",
        INSTALLED_MARKER.casefold(),
        INSTALLED_SHA256_MARKER.casefold(),
        REBOOT_PENDING_MARKER.casefold(),
        MANIFEST_FILENAME.casefold(),
    }
    if top in internal or top.startswith(".zapret_gui_"):
        return True
    if top == "lists" and parts[-1].casefold().endswith("-user.txt"):
        return True
    return rel.casefold() in _PRESERVED_RUNTIME_PATHS


def _load_managed_files(zapret_dir: Path) -> set[str]:
    """Load files owned by the previous upstream bundle, if known."""
    path = Path(zapret_dir) / MANIFEST_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return set()
    result: set[str] = set()
    for raw in data.get("files", []) if isinstance(data, dict) else []:
        if not isinstance(raw, str):
            continue
        rel = _normalise_rel_path(raw)
        parts = Path(rel).parts
        if not rel or Path(rel).is_absolute() or ".." in parts or _is_preserved_path(rel):
            continue
        result.add(rel)
    return result


def _save_managed_files(zapret_dir: Path, tag: str, files) -> None:
    """Atomically record the exact upstream files installed for stale cleanup."""
    path = Path(zapret_dir) / MANIFEST_FILENAME
    payload = {
        "version": MANIFEST_VERSION,
        "source": REPO,
        "tag": _norm(tag),
        "files": sorted({_normalise_rel_path(str(item)) for item in files}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


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


# Архив читается кусками: раньше весь файл тянулся одним requests.get с
# общим таймаутом 60 с, и на медленном канале загрузка гарантированно
# рвалась на полпути. Лимит размера защищает от сервера, который отдаёт
# бесконечный поток в память.
_DOWNLOAD_CHUNK = 256 * 1024
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def _progress_text(tag: str, done: int, total: int) -> str:
    name = tag or "zapret"
    done_mb = format(done / 1048576, ".1f")
    if total > 0:
        return (
            "Загрузка " + name + ": " + done_mb + " / "
            + format(total / 1048576, ".1f") + " МБ"
        )
    return "Загрузка " + name + ": " + done_mb + " МБ"


def _download(url: str, tag: str, timeout: float, on_status=None) -> bytes:
    """Stream the release archive into memory, reporting progress.

    ``timeout`` is passed as a (connect, read) pair, so it limits a single
    stalled read instead of the whole download: a large archive on a slow but
    healthy link is no longer aborted after a minute.
    """
    connect_timeout = min(float(timeout), 15.0)
    buf = bytearray()
    last_report = 0.0
    with requests.get(
        url, timeout=(connect_timeout, float(timeout)), stream=True
    ) as resp:
        resp.raise_for_status()
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except (AttributeError, TypeError, ValueError):
            total = 0
        if total > _MAX_ARCHIVE_BYTES:
            raise ValueError(
                "архив слишком большой: " + str(total) + " байт"
            )
        for chunk in resp.iter_content(_DOWNLOAD_CHUNK):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > _MAX_ARCHIVE_BYTES:
                raise ValueError("архив слишком большой, загрузка прервана")
            if on_status:
                now = time.monotonic()
                if now - last_report >= 0.5:
                    last_report = now
                    on_status(_progress_text(tag, len(buf), total))
    return bytes(buf)


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
        payload = _download(rel.zip_url, rel.tag, timeout, on_status)
    except Exception as exc:  # noqa: BLE001
        return "\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438: " + str(exc)

    if len(payload) > MAX_DOWNLOAD_BYTES:
        return (
            "Архив zapret слишком большой (лимит "
            + str(MAX_DOWNLOAD_BYTES // (1024 * 1024))
            + " МБ). Обновление отменено."
        )

    # --- SHA-256 integrity check ---
    actual_digest = _sha256_hex(payload)
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

    # The official release asset omits dot-directories on Windows. Download the
    # immutable tag zipball as a supplement and merge only .service/* from it.
    # This is why older GUI updates refreshed strategies/lists but never HOSTS
    # or ipset-service.txt. Fetch it before touching the live installation.
    source_payload = None
    if rel.source_zip_url and rel.source_zip_url != rel.zip_url:
        if on_status:
            on_status(
                "Загрузка служебных HOSTS/IPSet файлов "
                + (rel.tag or "zapret")
                + "..."
            )
        try:
            source_payload = _download(
                rel.source_zip_url, rel.tag, timeout, on_status
            )
        except Exception as exc:  # noqa: BLE001
            return "Ошибка загрузки полного комплекта zapret: " + str(exc)
        if len(source_payload) > MAX_DOWNLOAD_BYTES:
            return "Исходный архив zapret слишком большой. Обновление отменено."

    # Блокировки снимаем лениво. Раньше апдейтер на КАЖДОМ обновлении
    # убивал winws.exe и удалял службы WinDivert ещё до распаковки — даже
    # если ни один файл не был занят и пользователь нарочно держал обход
    # включённым. Теперь — только при реальной ошибке записи и один раз.
    locks_released = False

    old_managed = _load_managed_files(zapret_dir)
    new_managed: set[str] = set()
    write_failures: list[str] = []
    removed_stale = 0
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
    # Original bytes for every touched path. This lets us restore the previous
    # coherent bundle if any critical replacement or catalog rebuild fails.
    backups = {}

    def _remember_original(target: Path) -> None:
        if target in backups:
            return
        backups[target] = target.read_bytes() if target.exists() else None

    def _rollback() -> None:
        for target, original in reversed(list(backups.items())):
            try:
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(original)
            except OSError:
                _log.error("rollback failed for %s", target, exc_info=True)

    # Критичны только исполняемые файлы движка в bin/. Раньше любой пропущенный
    # файл из bin/ (readme, конфиг, случайный .txt) превращал удачное
    # обновление в пугающее сообщение о частичном обновлении.
    critical_suffixes = (".exe", ".dll", ".sys")

    def _record_skip(rel_path: str) -> None:
        nonlocal skipped
        skipped += 1
        skipped_paths.append(rel_path)
        rel_norm = rel_path.replace("\\", "/")
        is_engine_binary = (
            rel_norm.startswith("bin/")
            and rel_norm.lower().endswith(critical_suffixes)
        )
        if rel_norm in critical_names or is_engine_binary:
            critical_skipped.append(rel_norm)

    def _install_bytes(rel_path: str, data: bytes) -> None:
        """Install one validated member while preserving rollback information."""
        nonlocal extracted, locks_released
        rel_norm = _normalise_rel_path(rel_path)
        if _is_preserved_path(rel_norm):
            return
        rel_parts = Path(rel_norm).parts
        if Path(rel_norm).is_absolute() or ".." in rel_parts:
            _record_skip(rel_norm)
            return
        target = zapret_dir / rel_norm
        try:
            target_resolved = target.resolve(strict=False)
            if os.path.commonpath(
                [str(root_resolved), str(target_resolved)]
            ) != str(root_resolved):
                _record_skip(rel_norm)
                write_failures.append(rel_norm)
                return
        except (OSError, ValueError):
            _record_skip(rel_norm)
            write_failures.append(rel_norm)
            return

        new_managed.add(rel_norm)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            _remember_original(target)
            try:
                with open(target, "wb") as dst:
                    dst.write(data)
                extracted += 1
                return
            except OSError:
                if not locks_released:
                    locks_released = True
                    _release_windivert_locks(on_status)
                    try:
                        with open(target, "wb") as dst:
                            dst.write(data)
                        extracted += 1
                        return
                    except OSError:
                        pass
                if rel_norm.lower().endswith(".sys"):
                    pending_path = target.with_name(
                        target.name + ".zapretgui.new"
                    )
                    _remember_original(pending_path)
                    if _schedule_replace_on_reboot(target, data):
                        pending_reboot.append(rel_norm)
                        extracted += 1
                        if on_status:
                            on_status(
                                "Файл занят, замена запланирована после перезагрузки: "
                                + rel_norm
                            )
                        return
                raise
        except OSError:
            _record_skip(rel_norm)
            write_failures.append(rel_norm)
            if on_status:
                on_status("Не удалось заменить файл: " + rel_norm)

    root_resolved = zapret_dir.resolve()

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                return "В архиве zapret слишком много файлов. Обновление отменено."
            total_size = 0
            for info in infos:
                total_size += info.file_size
                if info.file_size > MAX_MEMBER_BYTES:
                    return "Файл в архиве zapret превышает безопасный размер: " + info.filename
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    return "Распакованный архив zapret превышает безопасный размер."
                if info.flag_bits & 0x1:
                    return "Зашифрованные файлы в архиве zapret не поддерживаются."
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    return "Символические ссылки в архиве zapret запрещены: " + info.filename
            names = [info.filename for info in infos]
            # GitHub zipball nests everything under a top folder — strip it.
            root = _common_root(names)
            rel_names = {
                (name.replace("\\", "/")[len(root):]
                 if root and name.replace("\\", "/").startswith(root)
                 else name.replace("\\", "/"))
                for name in names
            }
            required = {
                "bin/winws.exe",
                "bin/WinDivert.dll",
                "bin/WinDivert64.sys",
            }
            if rel.source_zip_url:
                # Normal GitHub releases use the verified Windows asset as the
                # primary archive. Calling that update complete is only valid
                # when it also carries the runtime lists and service launcher.
                required.update({
                    "lists/list-general.txt",
                    "lists/list-exclude.txt",
                    "lists/ipset-all.txt",
                    "service.bat",
                })
            missing = sorted(required - rel_names)
            has_strategy = any(
                "/" not in name
                and Path(name).name.casefold().startswith("general")
                and name.casefold().endswith(".bat")
                for name in rel_names
            )
            if missing or not has_strategy:
                detail = ", ".join(missing) if missing else "стратегии general*.bat"
                return "Архив zapret неполный, отсутствуют: " + detail + "."
            root_resolved = zapret_dir.resolve()
            for member in names:
                norm = member.replace("\\", "/")
                rel_path = norm[len(root):] if root and norm.startswith(root) else norm
                if not rel_path or member.endswith("/"):
                    continue
                rel_parts = Path(rel_path).parts
                # Security: never allow a malicious/corrupt archive entry to
                # escape zapret_dir (Zip Slip via ../ or absolute paths).
                if Path(rel_path).is_absolute() or ".." in rel_parts:
                    _record_skip(rel_path)
                    if on_status:
                        on_status("Пропущен небезопасный путь в архиве: " + rel_path)
                    continue
                with zf.open(member) as src:
                    data = src.read()
                _install_bytes(rel_path, data)
    except zipfile.BadZipFile:
        _rollback()
        return "Скачанный архив повреждён, попробуйте ещё раз."
    except Exception as exc:  # noqa: BLE001
        _rollback()
        return "Ошибка распаковки: " + str(exc)

    # Merge hidden service data from the tag source archive. The official
    # release asset currently contains no .service directory at all.
    if source_payload is not None:
        try:
            with zipfile.ZipFile(io.BytesIO(source_payload)) as source_zf:
                infos = source_zf.infolist()
                if len(infos) > MAX_ARCHIVE_ENTRIES:
                    raise ValueError("слишком много файлов в исходном архиве")
                total_size = sum(info.file_size for info in infos)
                if total_size > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        "исходный архив превышает безопасный размер"
                    )
                if any(info.file_size > MAX_MEMBER_BYTES for info in infos):
                    raise ValueError(
                        "файл в исходном архиве превышает безопасный размер"
                    )
                if any(info.flag_bits & 0x1 for info in infos):
                    raise ValueError(
                        "зашифрованный исходный архив не поддерживается"
                    )
                for info in infos:
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise ValueError(
                            "символическая ссылка в исходном архиве: "
                            + info.filename
                        )
                source_root = _common_root(
                    [info.filename for info in infos]
                )
                service_found: set[str] = set()
                for info in infos:
                    norm = info.filename.replace("\\", "/")
                    rel_path = (
                        norm[len(source_root):]
                        if source_root and norm.startswith(source_root)
                        else norm
                    )
                    if (
                        not rel_path
                        or info.is_dir()
                        or not rel_path.startswith(".service/")
                    ):
                        continue
                    if (
                        Path(rel_path).is_absolute()
                        or ".." in Path(rel_path).parts
                    ):
                        raise ValueError(
                            "небезопасный путь в исходном архиве: "
                            + rel_path
                        )
                    service_found.add(rel_path.casefold())
                    if rel_path not in new_managed:
                        _install_bytes(rel_path, source_zf.read(info))
                required_service = {
                    ".service/hosts",
                    ".service/ipset-service.txt",
                }
                missing_service = sorted(
                    required_service - service_found
                )
                if missing_service:
                    raise ValueError(
                        "не найдены служебные файлы: "
                        + ", ".join(missing_service)
                    )
        except zipfile.BadZipFile:
            _rollback()
            return "Исходный архив zapret повреждён. Обновление отменено."
        except Exception as exc:  # noqa: BLE001
            _rollback()
            return "Ошибка подготовки полного комплекта zapret: " + str(exc)

    # Whether the tag source was the primary archive or a supplement, a modern
    # release must actually install the two service inputs that were previously
    # lost by the updater. Validate the final staged ownership set, not merely
    # the archive listing.
    if rel.source_zip_url:
        installed_casefold = {name.casefold() for name in new_managed}
        required_service = {
            ".service/hosts",
            ".service/ipset-service.txt",
        }
        missing_service = sorted(required_service - installed_casefold)
        if missing_service:
            _rollback()
            return (
                "Полный комплект zapret не установлен, отсутствуют: "
                + ", ".join(missing_service)
                + ". Обновление отменено."
            )

    # A complete bundle update is all-or-nothing. Silently accepting any failed
    # helper/list write recreates the mixed-version installs this prevents.
    if write_failures:
        _rollback()
        failed = ", ".join(dict.fromkeys(write_failures[:8]))
        if len(write_failures) > 8:
            failed += ", ..."
        return (
            "Обновление выполнено частично до " + rel.tag
            + ": не удалось заменить файлы: " + failed
            + ". Все уже записанные файлы возвращены к предыдущей версии. "
            "Закройте zapret/службу или добавьте папку в исключения антивируса "
            "и повторите обновление."
        )

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

    # Remove only files recorded in the previous upstream manifest. Unknown
    # local files are never guessed/deleted during migration; from this update
    # onward, files removed by Flowseal disappear cleanly on the next update.
    for rel_path in sorted(old_managed - new_managed):
        if _is_preserved_path(rel_path):
            continue
        target = zapret_dir / rel_path
        try:
            if target.exists() and target.is_file():
                _remember_original(target)
                target.unlink()
                removed_stale += 1
        except OSError as exc:
            _rollback()
            return (
                "Не удалось удалить устаревший файл "
                + rel_path
                + ": "
                + str(exc)
            )

    # If core binaries were not replaced, do not rebuild/mark the release as
    # installed. Otherwise the UI would say "updated" while winws/driver are
    # still old or mixed-version.
    if critical_skipped:
        _rollback()
        crit = ", ".join(critical_skipped[:6])
        if len(critical_skipped) > 6:
            crit += ", ..."
        return (
            "Обновление выполнено частично до " + rel.tag + ": распаковано "
            + str(extracted) + " файлов, но не удалось заменить важные файлы: "
            + crit + ".\n\nЗакройте zapret, остановите службу zapret/процессы winws.exe "
            "или добавьте папку zapret в исключения антивируса, затем повторите обновление."
        )

    # Convert Flowseal's recipes into the app catalog while retaining every
    # upstream BAT (especially service.bat) as part of the complete bundle.
    try:
        from . import strategy_catalog
        _remember_original(zapret_dir / strategy_catalog.CATALOG_FILENAME)
        strategy_count = strategy_catalog.rebuild_from_bats(
            zapret_dir, delete_bats=False
        )
        if strategy_count <= 0:
            raise ValueError(
                "в архиве не удалось распознать ни одной стратегии"
            )
    except Exception as exc:
        # Never mark a release installed when its executable files changed but
        # the matching strategies could not be rebuilt. That mixed state must
        # remain visible and retryable instead of being reported as success.
        _log.error("could not rebuild the strategy catalog after the update", exc_info=True)
        _rollback()
        return (
            "Файлы zapret распакованы, но каталог стратегий не обновлён: "
            + str(exc)
            + ". Обновление не отмечено завершённым; повторите попытку."
        )

    # Record the exact upstream ownership set only after files and strategy
    # catalog are coherent. This enables safe deletion of upstream-removed files
    # on later updates without ever guessing which local files belong to users.
    manifest_path = zapret_dir / MANIFEST_FILENAME
    try:
        _remember_original(manifest_path)
        _save_managed_files(zapret_dir, rel.tag, new_managed)
    except OSError as exc:
        _rollback()
        return (
            "Не удалось записать манифест полного обновления zapret: "
            + str(exc)
        )

    # Record the version so the same update isn't offered again.
    save_local_version(zapret_dir, rel.tag)
    # Store the digest so a re-download of the SAME tag with DIFFERENT bytes
    # (MITM / partial download / corrupted cache) is caught next time.
    _save_installed_sha256(zapret_dir, actual_digest)
    msg = "Обновлено до " + rel.tag + ": распаковано " + str(extracted) + " файлов."
    if removed_stale:
        msg += " Удалено устаревших файлов: " + str(removed_stale) + "."
    if skipped:
        shown = ", ".join(skipped_paths[:6])
        if len(skipped_paths) > 6:
            shown += ", ..."
        msg += " Пропущено " + str(skipped) + " неключевых файлов: " + shown + "."
    return msg
