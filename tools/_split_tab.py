"""Move a block of MainWindow methods into a mixin module, verbatim.

Usage: python tools/_split_tab.py <out_module> <MixinName> <first_def> <stop_def>

The methods between ``first_def`` and ``stop_def`` (exclusive) are cut from
ui/main_window.py and pasted under ``class <MixinName>:`` in ui/<out_module>.py.
MainWindow then inherits the mixin, so ``self`` keeps working exactly as before
and no call sites change.
"""

import pathlib
import sys

MW = pathlib.Path("ui/main_window.py")


def find(lines, needle, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(needle):
            return i
    raise SystemExit("not found: " + needle)


def main() -> int:
    out_name, mixin_name, first_def, stop_def = sys.argv[1:5]
    lines = MW.read_text(encoding="utf-8").splitlines(keepends=True)

    start = find(lines, "    def " + first_def + "(")
    stop = find(lines, "    def " + stop_def + "(")
    if start >= stop:
        raise SystemExit("bad range")

    # Shared import preamble: everything main_window imports, so the moved
    # code finds the same names. Unused imports are harmless.
    imp_start = find(lines, "from __future__ import annotations")
    imp_stop = find(lines, "# Asset lookup lives")
    preamble = "".join(lines[imp_start:imp_stop]).rstrip() + "\n"

    i18n_start = find(lines, "from .i18n import (")
    i18n_stop = find(lines, ")", i18n_start)
    preamble += "".join(lines[i18n_start:i18n_stop + 1])

    w_start = find(lines, "from .widgets_custom import (")
    w_stop = find(lines, ")", w_start)
    preamble += "".join(lines[w_start:w_stop + 1])

    body = "".join(lines[start:stop]).rstrip() + "\n"

    header = (
        '"""' + mixin_name + " \u2014 part of MainWindow, kept in its own file.\n"
        "\n"
        "These methods were moved out of ui/main_window.py unchanged. They are\n"
        "mixed into MainWindow, so ``self`` still refers to the window and every\n"
        "attribute they use lives there as before.\n"
        '"""\n'
        + preamble
        + "\n\n"
        + "class " + mixin_name + ":\n"
        + '    """Mixin: see module docstring."""\n\n'
    )

    out_path = pathlib.Path("ui") / (out_name + ".py")
    out_path.write_text(header + body, encoding="utf-8")

    remaining = lines[:start] + lines[stop:]
    MW.write_text("".join(remaining), encoding="utf-8")

    print("moved lines :", stop - start)
    print("wrote       :", out_path)
    print("main_window :", len(remaining), "lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
