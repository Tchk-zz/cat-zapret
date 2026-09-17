"""Update Flowseal zapret list files and manage Windows hosts snippets.

The original Flowseal bundle exposes menu actions such as "Update IPset list"
and "Update Hosts File". In ZapretGUI we keep the same idea but make it safer:

* list updates touch only upstream-owned zapret list files under ``lists/`` and
  service data under ``.service/``;
* user files (``*-user.txt``), custom strategies and config are never touched;
* Windows ``hosts`` is never changed in the background — the GUI shows the
  generated block and applies it only after an explicit user action.
"""
from __future__ import annotations

import io
import ipaddress
import os
import shutil
import stat
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


_SERVICE_DATA_FILES = {
    ".service/hosts",
    ".service/ipset-service.txt",
    ".service/version.txt",
}


def _is_service_data(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("/").lower()
    return rel in _SERVICE_DATA_FILES


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
    """Atomically refresh lists, IPSet and hidden ``.service`` data.

    Flowseal's Windows release asset omits the hidden ``.service`` directory.
    We therefore merge service data from the tagged source zipball, while
    continuing to take runtime binaries/lists from the verified release asset.
    Every ``lists/*-user.txt`` file remains strictly user-owned.
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

    source_url = getattr(rel, "source_zip_url", None)
    downloads = [(rel.zip_url, False)]
    if source_url and source_url != rel.zip_url:
        downloads.append((source_url, True))

    payloads = []
    for url, service_only in downloads:
        label = "служебных HOSTS/IPSet" if service_only else "списков"
        report("Загрузка " + label + " zapret " + (rel.tag or "") + "...")
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            raw_length = getattr(response, "headers", {}).get(
                "Content-Length", "0"
            )
            try:
                content_length = int(raw_length or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length > updater.MAX_DOWNLOAD_BYTES:
                raise ValueError("архив превышает безопасный размер")
            payload = response.content
            if len(payload) > updater.MAX_DOWNLOAD_BYTES:
                raise ValueError("архив превышает безопасный размер")
        except Exception as exc:  # noqa: BLE001
            return ListUpdateResult(
                False,
                message="Ошибка загрузки " + label + ": " + str(exc),
            )
        if (
            not service_only
            and getattr(rel, "digest_verified", False)
            and getattr(rel, "digest", None)
            and updater._sha256_hex(payload).lower() != rel.digest.lower()
        ):
            return ListUpdateResult(
                False,
                message="SHA-256 архива списков zapret не совпадает.",
            )
        payloads.append((payload, service_only))

    prepared: dict[str, bytes] = {}
    skipped = 0
    try:
        for payload, service_only in payloads:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                infos = zf.infolist()
                if len(infos) > updater.MAX_ARCHIVE_ENTRIES:
                    raise ValueError("слишком много файлов в архиве")
                total_size = 0
                for info in infos:
                    total_size += info.file_size
                    if info.file_size > updater.MAX_MEMBER_BYTES:
                        raise ValueError(
                            "файл превышает безопасный размер: " + info.filename
                        )
                    if total_size > updater.MAX_UNCOMPRESSED_BYTES:
                        raise ValueError(
                            "распакованный архив превышает безопасный размер"
                        )
                    if info.flag_bits & 0x1:
                        raise ValueError("зашифрованный архив не поддерживается")
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if stat.S_ISLNK(mode):
                        raise ValueError(
                            "символическая ссылка в архиве: " + info.filename
                        )
                root = updater._common_root(
                    [info.filename for info in infos]
                )
                for info in infos:
                    norm = info.filename.replace("\\", "/")
                    rel_path = (
                        norm[len(root):]
                        if root and norm.startswith(root)
                        else norm
                    )
                    if not rel_path or info.is_dir():
                        continue
                    wanted = _is_service_data(rel_path)
                    if not service_only:
                        wanted = wanted or _is_upstream_list(rel_path)
                    if not wanted:
                        continue
                    safe = _safe_rel_path(rel_path)
                    if safe is None:
                        skipped += 1
                        continue
                    data = zf.read(info)
                    if not data.strip():
                        skipped += 1
                        continue
                    prepared[safe.as_posix()] = data
    except zipfile.BadZipFile:
        return ListUpdateResult(False, message="Скачанный архив повреждён.")
    except Exception as exc:  # noqa: BLE001
        return ListUpdateResult(
            False, message="Ошибка подготовки списков: " + str(exc)
        )

    if source_url:
        required = {
            "lists/list-general.txt",
            "lists/list-exclude.txt",
            "lists/ipset-all.txt",
            ".service/hosts",
            ".service/ipset-service.txt",
        }
        missing = sorted(required - set(prepared))
        if missing:
            return ListUpdateResult(
                False,
                skipped=skipped,
                message=(
                    "Полный комплект списков неполный, отсутствуют: "
                    + ", ".join(missing)
                    + "."
                ),
            )

    if not prepared:
        return ListUpdateResult(
            False,
            skipped=skipped,
            message="В релизе не найдено подходящих list/IPSet/HOSTS файлов.",
        )

    updated = 0
    unchanged = 0
    backups: dict[Path, Optional[bytes]] = {}
    try:
        for rel_path, data in sorted(prepared.items()):
            target = Path(zapret_dir) / rel_path
            try:
                old = target.read_bytes() if target.exists() else None
            except OSError:
                old = None
            if old == data:
                unchanged += 1
                report("Без изменений: " + rel_path)
                continue
            backups[target] = old
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
            updated += 1
            report("Обновлён список: " + rel_path)
    except OSError as exc:
        for target, old in reversed(list(backups.items())):
            try:
                if old is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(old)
            except OSError:
                _log.error("list update rollback failed for %s", target, exc_info=True)
        return ListUpdateResult(
            False,
            updated=0,
            skipped=skipped + 1,
            unchanged=unchanged,
            message="Не удалось атомарно обновить списки: " + str(exc),
        )

    if updated <= 0:
        msg = f"Списки/HOSTS/IPSet уже актуальны: проверено {len(prepared)} файлов."
    else:
        msg = f"Списки/HOSTS/IPSet обновлены: {updated} файлов."
    if unchanged:
        msg += f" Без изменений: {unchanged}."
    if skipped:
        msg += f" Пропущено: {skipped}."
    return ListUpdateResult(
        True,
        updated=updated,
        skipped=skipped,
        unchanged=unchanged,
        message=msg,
    )


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
