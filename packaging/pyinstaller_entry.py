"""PyInstaller entry point for the packaged Windows .exe.

Double-clicked (no arguments) it opens the GUI. Run from a terminal with
arguments it behaves as the CLI, so the single .exe covers both.

A frozen script has no package context, so this can't be
``cm0102_regen_notes/__main__.py`` (that uses ``from .cli``); absolute
imports here work because PyInstaller bundles the package.
"""

import io
import sys

# A --windowed build has no console: sys.stdout / sys.stderr are None, and any
# print() (argparse --version, CLI output) would then crash. Give them a sink.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()


def main() -> int:
    if len(sys.argv) > 1:
        from cm0102_regen_notes.cli import main as cli_main
        return cli_main()
    from cm0102_regen_notes.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
