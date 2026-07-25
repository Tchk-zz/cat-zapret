"""Validation helpers for the custom strategy / domain-list editor.

The actual editing UI lives in ui/main_window.py; this module holds the
non-UI logic so it can be unit-tested and reused.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class ValidationResult:
    ok: bool
    messages: List[str]


def validate_args(args_text: str) -> ValidationResult:
    """Light sanity checks for a winws argument string."""
    msgs: List[str] = []
    text = args_text.strip()
    if not text:
        return ValidationResult(False, ["\u0410\u0440\u0433\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u0443\u0441\u0442\u044b."])
    if "--dpi-desync" not in text and "--wf-" not in text:
        msgs.append(
            "\u041d\u0435\u0442 \u043d\u0438 --wf-tcp/--wf-udp, \u043d\u0438 --dpi-desync \u2014 "
            "\u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f \u0441\u043a\u043e\u0440\u0435\u0435 \u0432\u0441\u0435\u0433\u043e \u043d\u0435 \u0437\u0430\u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442."
        )
    if text.count('"') % 2 != 0:
        msgs.append("\u041d\u0435\u043f\u0430\u0440\u043d\u044b\u0435 \u043a\u0430\u0432\u044b\u0447\u043a\u0438.")
    # Warn about cmd-style placeholders: winws.exe can't expand them and would
    # crash. The GUI saves the strategy with placeholders resolved, but a clear
    # warning at validation time lets the user fix them by hand if they prefer.
    import re as _re
    if _re.search(r"%[~A-Za-z0-9_]+%?", text):
        msgs.append(
            "\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u044b \u043f\u0435\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435 \u0432\u0438\u0434\u0430 %BIN% / %LISTS% / %~dp0. "
            "\u041f\u0440\u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0438 \u043e\u043d\u0438 \u0431\u0443\u0434\u0443\u0442 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0437\u0430\u043c\u0435\u043d\u0435\u043d\u044b "
            "\u043d\u0430 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0435 \u043f\u0443\u0442\u0438 \u043a \u043f\u0430\u043f\u043a\u0435 zapret."
        )
    ok = not any(m for m in msgs if "\u043d\u0435\u043f\u0430\u0440\u043d" in m or "\u043f\u0443\u0441\u0442" in m)
    return ValidationResult(ok, msgs or ["\u041e\u041a"])


def list_domain_files(zapret_dir: Path) -> List[Path]:
    """Return editable domain / ipset list files."""
    lists_dir = zapret_dir / "lists"
    out: List[Path] = []
    if lists_dir.exists():
        out.extend(sorted(lists_dir.glob("*.txt")))
    # Some Flowseal versions keep lists in the root too.
    out.extend(sorted(zapret_dir.glob("list-*.txt")))
    out.extend(sorted(zapret_dir.glob("ipset-*.txt")))
    # De-duplicate while preserving order.
    seen = set()
    uniq: List[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq
