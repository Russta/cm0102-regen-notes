"""PyInstaller entry point.

A frozen script has no package context, so ``cm0102_regen_notes/__main__.py``
(which uses ``from .cli import main``) can't be the entry point. This file uses
an absolute import instead and is what the build workflow points PyInstaller at.
``python -m cm0102_regen_notes`` still goes through ``__main__.py`` as normal.
"""

from cm0102_regen_notes.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
