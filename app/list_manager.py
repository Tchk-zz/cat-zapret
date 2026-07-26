"""Update Flowseal zapret list files and manage Windows hosts snippets.

The original Flowseal bundle exposes menu actions such as "Update IPset list"
and "Update Hosts File". In ZapretGUI we keep the same idea but make it safer:

* list updates touch only upstream-owned zapret list files under ``lists/`` and
  ``.service/hosts``;
* user files (``*-user.txt``), custom strategies and config are never touched;
* Windows ``hosts`` is never changed in the background — the GUI shows the
  generated block and applies it only after an explicit user action.
"""
from __future__ import annotations

import io
import ipaddress
import os
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .applog import get_logger

_log = get_logger("lists")

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from . import updater

HOSTS_BEGIN = "# >>> ZapretGUI managed hosts >>>"
HOSTS_END = "# <<< ZapretGUI managed hosts <<<"
RAW_HOSTS_URL = (
    "https://raw.githubusercontent.com/Flowseal/"
    "zapret-discord-youtube/main/.service/hosts"
)


@dataclass
class ListUpdateResult:
    ok: bool
    updated: int = 0
    skipped: int = 0
    unchanged: int = 0
    message: str = ""


def _is_user_list(rel_path: str) -> bool:
    name = Path(rel_path).name.lower()
    return name.endswith("-user.txt")


def _is_upstream_list(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("/")
    if not rel.startswith("lists/"):
        return False
    if not rel.lower().endswith(".txt"):
        return False
    if _is_user_list(rel):
        return False
    return True


def _is_hosts_template(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("/").lower()
    return rel == ".service/hosts"


def _safe_rel_path(rel_path: str) -> Optional[Path]:
    rel = rel_path.replace("\\", "/").lstrip("/")
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        return None
    return p


def update_zapret_lists(
    zapret_dir: Path,
    timeout: float = 60.0,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> ListUpdateResult:
    """Download latest Flowseal release and update only list/hosts data.

    This is intentionally narrower than a full zapret update. It refreshes
    ``lists/*.txt`` (except user-managed ``*-user.txt`` files) and the
    ``.service/hosts`` template used by the HOSTS dialog.
    """
    def report(msg: str) -> None:
        if progress_cb is not None:
            progress_cb(msg)

    if requests is None:
        return ListUpdateResult(False, message="Модуль requests не установлен.")

    report("Поиск последнего релиза zapret...")
    rel = updater.latest_release(timeout=min(timeout, 15.0))
    if rel is None or not rel.zip_url:
        return ListUpdateResult(
            False,
            message="Не удалось получить релиз zapret с GitHub.",
        )

    report("Загрузка списков zapret " + (rel.tag or "") + "...")
    try:
        r = requests.get(rel.zip_url, timeout=timeout)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return ListUpdateResult(False, message="Ошибка загрузки списков: " + str(exc))

    updated = 0
    skipped = 0
    unchanged = 0
    checked = 0
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            root = updater._common_root(zf.namelist())
            for member in zf.namelist():
                norm = member.replace("\\", "/")
                rel = norm[len(root):] if root and norm.startswith(root) else norm
                if not rel or norm.endswith("/"):
                    continue
                if not (_is_upstream_list(rel) or _is_hosts_template(rel)):
                    continue
                safe = _safe_rel_path(rel)
                if safe is None:
                    skipped += 1
                    continue
                target = Path(zapret_dir) / safe
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = zf.read(member)
                    if not data.strip():
                        skipped += 1
                        continue
                    checked += 1
                    try:
                        old = target.read_bytes() if target.exists() else None
                    except OSError:
                        old = None
                    if old == data:
                        unchanged += 1
                        report("Без изменений: " + rel)
                        continue
                    tmp = target.with_suffix(target.suffix + ".tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, target)
                    updated += 1
                    report("Обновлён список: " + rel)
                except OSError:
                    skipped += 1
    except zipfile.BadZipFile:
        return ListUpdateResult(False, message="Скачанный архив повреждён.")
    except Exception as exc:  # noqa: BLE001
        return ListUpdateResult(False, message="Ошибка распаковки списков: " + str(exc))

    if checked <= 0:
        return ListUpdateResult(
            False,
            updated=0,
            skipped=skipped,
            unchanged=unchanged,
            message="В релизе не найдено подходящих list/ipset/hosts файлов.",
        )
    if updated <= 0:
        msg = f"Списки/IPset уже актуальны: проверено {checked} файлов."
        if skipped:
            msg += f" Пропущено: {skipped}."
        return ListUpdateResult(True, updated=0, skipped=skipped, unchanged=unchanged, message=msg)
    msg = f"Списки обновлены: {updated} файлов."
    if unchanged:
        msg += f" Без изменений: {unchanged}."
    if skipped:
        msg += f" Пропущено: {skipped}."
    return ListUpdateResult(True, updated=updated, skipped=skipped, unchanged=unchanged, message=msg)


def _valid_hostname(host: str) -> bool:
    if not host or len(host) > 253 or host.startswith(".") or host.endswith("."):
        return False
    labels = host.split(".")
    if len(labels) < 2:
        return False
    for label in labels:
        if not label or len(label) > 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not all(ch.isalnum() or ch == "-" for ch in label):
            return False
    return True


def normalize_hosts_lines(text: str) -> List[str]:
    """Return safe ``IP hostname`` lines from a hosts template."""
    out: List[str] = []
    seen = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Remove inline comments while keeping the actual hosts fields.
        line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            ip = str(ipaddress.ip_address(parts[0]))
        except ValueError:
            continue
        for host in parts[1:]:
            h = host.strip().lower().rstrip(".")
            if not _valid_hostname(h):
                continue
            item = f"{ip} {h}"
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def render_hosts_block(lines: Iterable[str]) -> str:
    clean = normalize_hosts_lines("\n".join(lines))
    if not clean:
        return ""
    return "\n".join([HOSTS_BEGIN, *clean, HOSTS_END]) + "\n"


def load_hosts_template(
    zapret_dir: Path,
    timeout: float = 15.0,
    allow_network: bool = True,
) -> str:
    """Load Flowseal's ``.service/hosts`` template from disk or GitHub."""
    local = Path(zapret_dir) / ".service" / "hosts"
    try:
        if local.exists():
            text = local.read_text(encoding="utf-8", errors="ignore")
            if normalize_hosts_lines(text):
                return text
    except OSError:
        # Cached hosts snippet unreadable; we fall back to the network below.
        _log.warning("could not read the cached hosts file %s", local, exc_info=True)

    if allow_network and requests is not None:
        try:
            r = requests.get(
                RAW_HOSTS_URL,
                timeout=timeout,
                headers={"User-Agent": "ZapretGUI-hosts"},
            )
            r.raise_for_status()
            text = r.text
            if normalize_hosts_lines(text):
                try:
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_text(text, encoding="utf-8")
                except OSError:
                    # Caching is optional: the snippet is still returned.
                    _log.warning(
                        "could not cache the hosts snippet in %s", local, exc_info=True
                    )
                return text
        except Exception:
            # No network / GitHub unreachable: the caller reports "no data".
            _log.warning("could not download the hosts snippet", exc_info=True)
    return ""


def build_hosts_block(zapret_dir: Path, allow_network: bool = True) -> str:
    """Build the managed hosts block shown to the user."""
    template = load_hosts_template(zapret_dir, allow_network=allow_network)
    return render_hosts_block(normalize_hosts_lines(template))


def system_hosts_path() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("SystemRoot") or r"C:\Windows"
        return Path(root) / "System32" / "drivers" / "etc" / "hosts"
    return Path("/etc/hosts")


def _replace_managed_block(existing: str, block: str) -> str:
    lines = existing.splitlines()
    kept: List[str] = []
    inside = False
    for line in lines:
        if line.strip() == HOSTS_BEGIN:
            inside = True
            continue
        if line.strip() == HOSTS_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    if block.strip():
        if kept:
            kept.append("")
        kept.extend(block.strip("\n").splitlines())
    return "\n".join(kept).rstrip("\n") + "\n"


def apply_hosts_block(block: str, hosts_path: Optional[Path] = None) -> str:
    """Apply the managed block to Windows hosts after explicit user action."""
    if hosts_path is None and not sys.platform.startswith("win"):
        return "HOSTS применяется автоматически только в Windows. Скопируйте строки вручную."
    clean_block = render_hosts_block(normalize_hosts_lines(block))
    if not clean_block:
        return "Нет валидных строк HOSTS для применения."
    path = Path(hosts_path) if hosts_path is not None else system_hosts_path()
    try:
        existing = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        new_text = _replace_managed_block(existing, clean_block)
        if existing.replace("\r\n", "\n") == new_text:
            return "HOSTS уже содержит актуальный блок ZapretGUI. Изменения не нужны."
        if path.exists():
            backup = path.with_name(path.name + ".zapretgui.bak")
            shutil.copy2(path, backup)
        path.write_text(new_text, encoding="utf-8")
        return "HOSTS обновлён. Бэкап: " + str(path.with_name(path.name + ".zapretgui.bak"))
    except PermissionError:
        return "Нет прав на запись в HOSTS. Запустите ZapretGUI от имени администратора."
    except OSError as exc:
        return "Не удалось обновить HOSTS: " + str(exc)


def hosts_block_is_current(block: str, hosts_path: Optional[Path] = None) -> bool:
    """Return True if system hosts already contains exactly this managed block."""
    if hosts_path is None and not sys.platform.startswith("win"):
        return False
    clean_block = render_hosts_block(normalize_hosts_lines(block))
    if not clean_block:
        return False
    path = Path(hosts_path) if hosts_path is not None else system_hosts_path()
    try:
        existing = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    except OSError:
        return False
    return existing.replace("\r\n", "\n") == _replace_managed_block(existing, clean_block)

def remove_hosts_block(hosts_path: Optional[Path] = None) -> str:
    if hosts_path is None and not sys.platform.startswith("win"):
        return "HOSTS применяется автоматически только в Windows. Удалите блок вручную."
    path = Path(hosts_path) if hosts_path is not None else system_hosts_path()
    try:
        existing = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        if HOSTS_BEGIN not in existing:
            return "Блок ZapretGUI в HOSTS не найден."
        backup = path.with_name(path.name + ".zapretgui.bak")
        shutil.copy2(path, backup)
        path.write_text(_replace_managed_block(existing, ""), encoding="utf-8")
        return "Блок ZapretGUI удалён из HOSTS. Бэкап: " + str(backup)
    except PermissionError:
        return "Нет прав на запись в HOSTS. Запустите ZapretGUI от имени администратора."
    except OSError as exc:
        return "Не удалось изменить HOSTS: " + str(exc)


def should_auto_update_lists(last_update: int, interval_hours: int, now: Optional[int] = None) -> bool:
    if interval_hours <= 0:
        return False
    current = int(time.time()) if now is None else int(now)
    try:
        last = int(last_update or 0)
    except (TypeError, ValueError):
        last = 0
    # Never updated before: run once as soon as zapret is ready.
    if last <= 0:
        return True
    return current - last >= int(interval_hours) * 3600
