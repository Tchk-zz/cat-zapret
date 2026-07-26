"""Run pyflakes over our own code and fail on any finding.

Two deliberate exceptions:

* ``app/tg_proxy_engine/`` is a vendored third-party engine that is never
  edited in this repository. It is EXCLUDED from the scan entirely instead of
  having its findings filtered out afterwards. The previous wrapper scanned it
  and then dropped the results, so the "known findings" counter silently grew
  from 3 to 65 whenever the vendored engine changed -- and a real problem in
  our own code could hide inside that pile.
* ``import app.tg_proxy  # noqa: F401`` in ``tests/test_core_logic.py`` exists
  purely to prove the module imports cleanly, so pyflakes reports it as an
  unused import. That single finding stays ignored.

Everything else is a failure.

Usage:
    python tools/check_lint.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Our own code. Directories are scanned recursively.
TARGET_DIRS = ("app", "ui", "tests", "tools")
TARGET_FILES = ("main.py",)

# Any path containing one of these directory names is skipped: vendored code
# and build leftovers are not ours to fix.
EXCLUDED_DIR_NAMES = frozenset({"tg_proxy_engine", "__pycache__"})

# Substrings identifying the allowed, deliberate findings.
ALLOWED = ("'app.tg_proxy' imported but unused",)


def collect_targets() -> list[str]:
    """Return the Python files that should be linted."""
    files: list[Path] = []
    for name in TARGET_FILES:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for dir_name in TARGET_DIRS:
        base = ROOT / dir_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if EXCLUDED_DIR_NAMES.intersection(path.parts):
                continue
            files.append(path)
    return [str(p) for p in files]


def main() -> int:
    targets = collect_targets()
    if not targets:
        print("check_lint: no Python files found -- wrong working directory?")
        return 1

    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", *targets],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    unexpected = [ln for ln in lines if not any(a in ln for a in ALLOWED)]

    if result.stderr.strip():
        print(result.stderr.strip())

    if unexpected:
        print("pyflakes found new issues:")
        for line in unexpected:
            print("  " + line)
        return 1

    known = len(lines)
    noun = "finding" if known == 1 else "findings"
    print(f"pyflakes: clean ({known} known {noun} ignored, {len(targets)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
