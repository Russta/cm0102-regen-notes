"""Reader for the ``.gpf2`` sidecar produced by the community GPF2 tool.

GPF2, pointed at a brand-new save, writes ``<savename>.sav.gpf2`` next to it:
one 16-byte record per ``player.dat`` slot, in slot order::

    int32  firstNameIndex
    int32  secondNameIndex
    int32  commonNameIndex   (0 = none)
    int32  slotNumber        (0, 1, 2, ... -- just the record's own position)

That's the whole file -- it's a day-one **name** snapshot per player slot and
nothing else (no ids, no abilities). We only ever read it; GPF2 owns writing it.

Decoding verified against a real save: all 12 hand-made regen notes in that
save resolve to the correct day-one name via these indices.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

GPF2_RECORD_LEN = 16


@dataclass(frozen=True)
class Gpf2Snapshot:
    """Day-one name indices per player slot. ``entries[slot] = (first, second, common)``."""

    entries: list[tuple[int, int, int]]
    path: str

    def __len__(self) -> int:
        return len(self.entries)

    @classmethod
    def load(cls, path: str | Path) -> "Gpf2Snapshot":
        raw = Path(path).read_bytes()
        if len(raw) % GPF2_RECORD_LEN != 0:
            raise ValueError(
                f"{path}: size {len(raw)} is not a multiple of {GPF2_RECORD_LEN}"
            )
        n = len(raw) // GPF2_RECORD_LEN
        entries: list[tuple[int, int, int]] = []
        for i in range(n):
            first, second, common, slot = struct.unpack_from("<iiii", raw, i * GPF2_RECORD_LEN)
            if slot != i:
                raise ValueError(
                    f"{path}: record {i} has slot field {slot}; expected sequential order"
                )
            entries.append((first, second, common))
        return cls(entries=entries, path=str(path))

    @staticmethod
    def sidecar_path(save_path: str | Path) -> Path:
        """GPF2 names its file ``<save>.gpf2`` (i.e. keeps the ``.sav``)."""
        p = Path(save_path)
        return p.with_name(p.name + ".gpf2")
