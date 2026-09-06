"""CM 01/02 Regen Notes Tool.

Reads Championship Manager 01/02 ``.sav`` files, matches current regenerated
players back to the original players they replaced, and writes the original
identity into each regen's in-game Notes field -- additively, without renaming
anyone in place.

Nothing here mutates a save unless you explicitly ask it to, and every write
goes to a new output file; the input is never touched.
"""

__version__ = "0.1.0"
