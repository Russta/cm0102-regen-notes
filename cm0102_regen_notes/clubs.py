"""The ``club.dat`` block -- club names, keyed by ``TStaff.ClubId`` (offset 57).

Each record is 581 bytes::

    [0:4]    int32  ClubId
    [4:54]   LongName   Latin-1, null-terminated (50-byte field)
    [56:81]  Name       short name, Latin-1, null-terminated (25-byte field)
    [83:87]  int32  NationId
    [87:91]  int32  DivisionId

Offsets cross-checked against ChrisReganXP/CMScouter and verified against a
real save (staff ClubId -> the expected club). In the saves seen so far
``ClubId`` equals the record's array position, but we build an id->record map
anyway so it still works if that ever diverges.
"""

from __future__ import annotations

import struct

from .savfile import SavFile

CLUB_RECORD_LEN = 581
C_ID = 0
C_LONG_NAME = 4
C_LONG_NAME_LEN = 50
C_SHORT_NAME = 56
C_SHORT_NAME_LEN = 25


class ClubTable:
    def __init__(self, block: bytes):
        self._long: dict[int, str] = {}
        self._short: dict[int, str] = {}
        for i in range(len(block) // CLUB_RECORD_LEN):
            base = i * CLUB_RECORD_LEN
            club_id = struct.unpack_from("<i", block, base + C_ID)[0]
            long_name = (
                block[base + C_LONG_NAME : base + C_LONG_NAME + C_LONG_NAME_LEN]
                .split(b"\x00", 1)[0].decode("latin-1")
            )
            short_name = (
                block[base + C_SHORT_NAME : base + C_SHORT_NAME + C_SHORT_NAME_LEN]
                .split(b"\x00", 1)[0].decode("latin-1")
            )
            self._long[club_id] = long_name
            self._short[club_id] = short_name

    @classmethod
    def from_sav(cls, sav: SavFile) -> "ClubTable":
        return cls(sav.read_block("club.dat"))

    def name(self, club_id: int, *, short: bool = False) -> str:
        """Club name for a ``TStaff.ClubId``; ``""`` if it resolves to nothing
        (free agents / retired players carry an out-of-range id)."""
        table = self._short if short else self._long
        return table.get(club_id, "")
