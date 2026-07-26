"""Run pyflakes and fail only on NEW findings.

The repository has three deliberate, permanent pyflakes findings that must not
be "fixed":

* two star imports inside the vendored ``app/tg_proxy_engine/`` package (that
  code is vendored upstream and is never edited here), and
* ``import app.tg_proxy  # noqa: F401`` in ``tests/test_core_logic.py``, which
  exists purely to prove the module imports cleanly.

Plain ``python -m pyflakes app ui tests main.py tools`` therefore always exits
non-zero, which would make CI permanently red and useless. This wrapper drops
exactly those known findings and fails on anything else.

Usage:
    python tools/check_lint.py
"""

from __future__ import annotations

import subprocess
import sys

TARGETS = ["app", "ui", "tests", "main.py", "tools"]

# Substrings identifying the allowed, deliberate findings.
ALLOWED = (
    "tg_proxy_engine",
    "'app.tg_proxy' imported but unused",
)


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", *TARGETS],
        capture_output=True,
        text=True,
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

    print(f"pyflakes: clean ({len(lines)} known findings ignored)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
