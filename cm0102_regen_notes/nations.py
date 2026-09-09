"""The ``nation.dat`` block -- just enough to turn a ``TStaff`` nation id into
the 3-letter code CM shows on player profiles (ENG, POL, BRA, ...).

Each record is 290 bytes::

    [0:4]    int32  Id
    [4:54]   Name          Latin-1, null-terminated (e.g. "England")
    [83:87]  code          3-letter code, null-terminated (e.g. "ENG")
    ...      continent, reputation, adjective, etc. -- not needed here

Id offset from ChrisReganXP/CMScouter; the code offset was found by inspecting
a real save (ENG/POL/BRA/ARG/GER/ESP/FRA all land at byte 83). Nations are
keyed by their Id field (which equals the array position in saves seen so
far, but we map by id anyway).
"""

from __future__ import annotations

import struct

from .savfile import SavFile

NATION_RECORD_LEN = 290
N_ID = 0
N_CODE = 83
N_CODE_LEN = 4


class NationTable:
    def __init__(self, block: bytes):
        self._code: dict[int, str] = {}
        for i in range(len(block) // NATION_RECORD_LEN):
            base = i * NATION_RECORD_LEN
            nation_id = struct.unpack_from("<i", block, base + N_ID)[0]
            code = (
                block[base + N_CODE : base + N_CODE + N_CODE_LEN]
                .split(b"\x00", 1)[0].decode("latin-1").strip()
            )
            self._code[nation_id] = code

    @classmethod
    def from_sav(cls, sav: SavFile) -> "NationTable":
        return cls(sav.read_block("nation.dat"))

    def code(self, nation_id: int) -> str:
        """3-letter code for a ``TStaff`` nation id; ``""`` if unknown."""
        return self._code.get(nation_id, "")
