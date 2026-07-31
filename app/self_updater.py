"""Self-update checker for Zapret GUI.

Checks our own GitHub releases page (Tchk-zz/cat-zapret) for a newer
installer and downloads + launches it so the user gets a seamless update
without having to find the releases page manually.

Flow:
  1. Fetch latest release tag from GitHub API.
  2. Compare against local VERSION file.
  3. If newer -> return AppRelease info to the caller (UI decides what to do).
  4. On user confirm -> download installer to a temp dir, verify its SHA-256
     against the digest published by GitHub, then launch it detached.
     The Inno Setup installer handles file replacement; we just start the wizard.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import requests as _requests
except ImportError:  # pragma: no cover
    _requests = None  # type: ignore

OWN_REPO = "Tchk-zz/cat-zapret"
RELEASES_API = "https://api.github.com/repos/" + OWN_REPO + "/releases/latest"
INSTALLER_ASSET = "ZapretGUI-Setup.exe"

# Prefix for the downloaded installer in %TEMP%. Kept in a constant because
# _purge_stale_installers() uses it to find leftovers from previous runs.
_TMP_PREFIX = "ZapretGUI-Setup-"

# Versions are compared as fixed-width tuples so that "1.8" and "1.8.0" are
# treated as the same version (see _norm).
_VERSION_PARTS = 3


@dataclass
class AppRelease:
    tag: str           # e.g. "v1.8.0"
    version: str       # e.g. "1.8.0" (tag without leading v)
    download_url: str
    size: int          # bytes
    sha256: str = ""   # lowercase hex digest published by GitHub, "" if absent
    # Release description from GitHub (Markdown). Shown to the user in the
    # "what's new" popup after a silent self-update relaunches the app.
    notes: str = ""


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def _norm(ver: str) -> tuple:
    """Convert "v1.8.0" or "1.8.0" -> (1, 8, 0) for comparison.

    Short versions are zero-padded to _VERSION_PARTS components. Without the
    padding Python compares tuples of different length lexicographically, so
    (1, 8) < (1, 8, 0) would be True and the app would report a bogus update
    whenever the tag was written as "v1.8" and VERSION as "1.8.0".
    Extra components are preserved, so "1.8.0.1" still sorts above "1.8.0".
    """
    clean = ver.lstrip("vV").strip()
    parts: list[int] = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < _VERSION_PARTS:
        parts.append(0)
    return tuple(parts)


def local_version() -> str:
    """Read the VERSION file bundled with the running app.

    NOTE: installer.iss MUST ship VERSION next to the exe. If it is missing,
    this returns "" -- check_update() then reports "error" instead of offering
    the same release forever (see the comment there).
    """
    if getattr(sys, "frozen", False):
        # Frozen exe: VERSION is next to the executable.
        base = Path(sys.executable).resolve().parent
    else:
        # Dev mode: VERSION is at the project root (two levels up from app/).
        base = Path(__file__).resolve().parent.parent
    try:
        return (base / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def _parse_digest(asset: dict) -> str:
    """Extract the lowercase sha256 hex digest from a GitHub asset entry.

    GitHub publishes it as ``"digest": "sha256:<hex>"``. Older API responses
    (and GitHub Enterprise) may not have the field at all, in which case we
    return "" and download_and_launch() refuses to run the installer: an
    unverifiable file must never be executed with admin rights.
    """
    digest = str(asset.get("digest") or "").strip()
    prefix = "sha256:"
    if digest.lower().startswith(prefix):
        return digest[len(prefix):].strip().lower()
    return ""


def latest_release(timeout: float = 10.0) -> Optional[AppRelease]:
    """Fetch the latest GitHub release of Zapret GUI.

    Returns None if the network is unavailable or the response is malformed.
    """
    if _requests is None:
        return None
    try:
        resp = _requests.get(
            RELEASES_API,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        # No network, GitHub down or rate limited. The UI only says "the check
        # failed", so record the real reason in the log file.
        from .applog import get_logger
        get_logger("update").warning("update check failed", exc_info=True)
        return None

    tag = data.get("tag_name", "")
    if not tag:
        return None

    for asset in data.get("assets", []):
        if asset.get("name") == INSTALLER_ASSET:
            return AppRelease(
                tag=tag,
                version=tag.lstrip("vV"),
                download_url=asset["browser_download_url"],
                size=asset.get("size", 0),
                sha256=_parse_digest(asset),
                notes=str(data.get("body") or "").strip(),
            )
    return None


def update_available() -> Optional[AppRelease]:
    """Return the latest release if it is newer than the installed version.

    Returns None if we are already up to date or the check fails.
    """
    status, rel = check_update()
    return rel if status == "update" else None


def check_update() -> tuple:
    """Check GitHub and report *why* there is nothing to install.

    ``update_available()`` collapses "already up to date" and "the check
    failed" into a single ``None``, so the UI silently did nothing when GitHub
    was unreachable and the user thought the button was broken. This variant
    returns a ``(status, release)`` pair:

    * ``("update", release)``  -- a newer release is available.
    * ``("uptodate", None)``   -- the installed version is current.
    * ``("error", None)``      -- the check itself failed (no network, GitHub
      down, rate limited, no installer asset in the latest release, or the
      local version is unknown).
    """
    rel = latest_release()
    if rel is None:
        return ("error", None)
    cur = local_version()
    if not cur:
        # VERSION is missing next to the exe (broken installer / manual copy).
        # This used to fall through to ("update", rel), so the app offered the
        # very same release over and over: an empty local version can never
        # compare as up to date, and reinstalling did not create the missing
        # file either. Reporting an error makes the UI say "the check failed"
        # instead of walking the user through the installer forever.
        return ("error", None)
    if _norm(rel.tag) <= _norm(cur):
        return ("uptodate", None)
    return ("update", rel)


# ---------------------------------------------------------------------------
# Download and launch
# ---------------------------------------------------------------------------

def _purge_stale_installers(keep: str = "") -> None:
    """Delete installers left in %TEMP% by previous update runs.

    Each update downloads a ~55 MB exe that we intentionally do not delete
    while the installer is running. Without this cleanup those files pile up
    in the temp folder forever. Files that are still locked (an installer is
    running right now) simply fail to delete and are skipped.
    """
    try:
        tmp_dir = Path(tempfile.gettempdir())
        for entry in tmp_dir.glob(_TMP_PREFIX + "*.exe"):
            if keep and str(entry) == keep:
                continue
            try:
                entry.unlink()
            except OSError:
                # Locked by a running installer or removed concurrently.
                pass
    except Exception:
        # Cleanup is best-effort and must never block an update.
        pass


def _discard(path: str) -> None:
    """Remove a partially downloaded / corrupted installer, ignoring errors."""
    try:
        os.unlink(path)
    except OSError:
        pass


_PENDING_CHANGELOG_NAME = "pending_update.json"


def pending_changelog_path() -> Path:
    """Location of the marker the silently-relaunched app reads on startup."""
    from .config import default_data_dir
    return default_data_dir() / _PENDING_CHANGELOG_NAME


def _write_pending_changelog(release: "AppRelease") -> None:
    """Best-effort: record what changed so the next launch can show it.

    A silent install (/VERYSILENT) shows no window at all, so without this
    the user would have no idea anything happened beyond the app briefly
    disappearing and reappearing. installer.iss relaunches ZapretGUI.exe
    right after the silent install finishes; that fresh process reads this
    file once via take_pending_changelog() and shows a popup.
    """
    try:
        path = pending_changelog_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"version": release.version, "tag": release.tag, "notes": release.notes},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        # Never let this convenience feature block the actual update.
        pass


def take_pending_changelog() -> Optional[dict]:
    """Read and delete the pending "what's new" marker, if any.

    Returns a dict with "version" / "tag" / "notes" keys, or None on a normal
    launch where no silent update just happened. The file is removed either
    way so a corrupted marker can never re-show the popup forever.
    """
    path = pending_changelog_path()
    data = None
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = None
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    return data if isinstance(data, dict) else None


def download_and_launch(
    release: AppRelease,
    on_status: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> str:
    """Download *release* installer to a temp file, verify it and start it.

    Args:
        release: the release to install.
        on_status: called with human-readable status lines.
        on_progress: called with the download completion percentage (0-100).
            Only fires when the server reports a content length.
        should_cancel: polled during the download; when it returns True the
            download is aborted and the partial file is deleted.

    Returns:
        ``"ok"``       if the installer was launched successfully.
        ``"cancelled"`` if *should_cancel* asked us to stop.
        A string starting with ``"Ошибка"`` on failure.

    The successfully launched installer file is intentionally NOT deleted --
    Windows locks it while the installer runs. It is cleaned up on the next
    update run by _purge_stale_installers().
    """
    if _requests is None:
        return "Ошибка: библиотека requests не установлена."

    def _report(msg: str) -> None:
        if on_status:
            on_status(msg)

    def _pct(value: int) -> None:
        if on_progress:
            on_progress(value)

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    # Reclaim disk space from previous updates before pulling another ~55 MB.
    _purge_stale_installers()

    size_mb = release.size // (1024 * 1024) if release.size else "?"
    _report(f"Загрузка установщика {release.tag} (~{size_mb} МБ)...")

    try:
        resp = _requests.get(release.download_url, timeout=300, stream=True)
        resp.raise_for_status()
    except Exception as exc:
        return "Ошибка загрузки: " + str(exc)

    # Prefer the length reported by the CDN; fall back to the API-reported size.
    try:
        total = int(resp.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        total = release.size or 0

    tmp_path = ""
    digest = hashlib.sha256()
    downloaded = 0
    last_pct = -1
    cancelled = False
    try:
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".exe",
            prefix=_TMP_PREFIX,
        )
        tmp_path = tmp.name
        with tmp:
            for chunk in resp.iter_content(chunk_size=65536):
                if _cancelled():
                    # Only leave the loop here. Windows refuses to delete a
                    # file that is still open, so discarding it inside the
                    # `with` block silently failed and left a partial ~55 MB
                    # installer in %TEMP% forever (covered by
                    # tests/test_self_updater.py).
                    cancelled = True
                    break
                if not chunk:
                    continue
                tmp.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = min(100, downloaded * 100 // total)
                    if pct != last_pct:
                        last_pct = pct
                        _pct(pct)
    except Exception as exc:
        if tmp_path:
            _discard(tmp_path)
        return "Ошибка сохранения: " + str(exc)
    finally:
        resp.close()

    if cancelled:
        # The file is closed by now, so this delete actually succeeds.
        _discard(tmp_path)
        _report("Загрузка обновления отменена.")
        return "cancelled"

    # Verify the download before executing it. The installer runs elevated, so
    # a truncated download or a tampered mirror would be executed with admin
    # rights -- exactly the check app/updater.py already does for the zapret
    # bundle. If GitHub did not publish a digest we can only check the size.
    if release.sha256:
        actual = digest.hexdigest()
        if actual != release.sha256:
            _discard(tmp_path)
            return (
                "Ошибка: контрольная сумма установщика не совпала. "
                f"Ожидалась {release.sha256[:16]}..., получена {actual[:16]}.... "
                "Файл удалён, установка отменена."
            )
        _report("Контрольная сумма SHA-256 совпала.")
    else:
        # No published digest: a size match proves nothing about the contents,
        # and this file is about to be executed with admin rights. Refuse.
        _discard(tmp_path)
        return (
            "Ошибка: для этого релиза не опубликована контрольная сумма SHA-256, "
            "поэтому подлинность установщика проверить невозможно. "
            "Файл удалён, установка отменена. "
            "Скачайте обновление вручную со страницы релизов на GitHub."
        )

    _pct(100)
    _report(f"Загружено {downloaded // 1024 // 1024} МБ. Устанавливаю без окон...")

    # Leave a note for the next launch so it can show a "что нового" popup --
    # a silent install has no UI of its own to tell the user anything changed.
    _write_pending_changelog(release)

    # The installer must NOT stay a child of this process. Setup closes the
    # running ZapretGUI.exe with taskkill before copying files; any variant of
    # that call using /T walks the process tree and would kill Setup itself,
    # leaving the old version installed (measured: DETACHED_PROCESS does not
    # break the parent/child link, it only detaches the console). Launching
    # through `cmd /c start` inserts a throwaway cmd that exits immediately, so
    # Setup is orphaned and survives whatever happens to this process.
    #
    # /VERYSILENT /SUPPRESSMSG /NORESTART run the whole Inno Setup wizard in
    # the background: no window, no clicks, no "installation complete"
    # message box. installer.iss then relaunches ZapretGUI.exe itself once
    # the silent install finishes (its Run entry guarded by WizardSilent), so
    # the app reappears on its own with the changelog popup above.
    silent_args = ["/VERYSILENT", "/SUPPRESSMSG", "/NORESTART"]
    try:
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            kwargs["close_fds"] = True
            # The empty "" is the window title argument of `start`; without it
            # a quoted path would be taken as the title and nothing would run.
            subprocess.Popen(
                ["cmd", "/c", "start", "", tmp_path] + silent_args,
                shell=False, **kwargs
            )
        else:
            subprocess.Popen([tmp_path] + silent_args, **kwargs)
    except Exception as exc:
        _discard(tmp_path)
        return "Ошибка запуска установщика: " + str(exc)

    return "ok"
