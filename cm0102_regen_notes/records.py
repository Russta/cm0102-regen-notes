"""Fixed-layout record readers for ``staff.dat`` (TStaff, 110 B) and
``player.dat`` (TPlayer, 70 B).

Field offsets cross-checked against ChrisReganXP/CMScouter's data classes and
verified against a real save (staff IDs resolve to the right names; regen CA/PA
read back in the expected 0-200 range). Nothing from that project is copied
here -- these are our own readers.

Only the fields this tool needs are pulled out. The full structs carry much
more (wages, contracts, personality, etc.).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

STAFF_RECORD_LEN = 110
PLAYER_RECORD_LEN = 70

# -- TStaff -------------------------------------------------------------
S_ID = 0
S_FIRST_NAME = 4
S_SECOND_NAME = 8
S_COMMON_NAME = 12
S_DOB = 16  # TCMDate-ish; not decoded here
S_NATION = 26
S_SECONDARY_NATION = 30
S_CLUB = 57
S_PLAYER_FK = 97  # 0x61 -- index into player.dat, or -1 if this person doesn't play

# -- TPlayer -----------------------------------------------------------
P_ID = 0
P_CA = 5  # int16 LE
P_PA = 7  # int16 LE (can be negative: a masked/random potential -> use abs)
P_REPUTATION = 9

#: TPlayer position-suitability bytes (0-20), by field name -> offset.
PLAYER_POSITIONS = {
    "GK": 15, "SW": 16, "DF": 17, "DM": 18, "MF": 19, "AM": 20, "ST": 21,
    "WingBack": 22, "Right": 23, "Left": 24, "Centre": 25, "FreeRole": 26,
}

#: TPlayer footedness bytes (0-20).
PLAYER_FEET = {"LeftFoot": 48, "RightFoot": 59}

#: The handful of attributes reported as stable across regeneration
#: (forum lore, not gospel) -- handy for eyeballing a match.
PLAYER_STABLE_ATTRS = {"Bravery": 32, "Flair": 40, "Versatility": 66}


@dataclass(frozen=True)
class StaffRecord:
    index: int
    staff_id: int
    first_name: int
    second_name: int
    common_name: int
    nation: int
    club: int  # ClubId; links to club.dat (see clubs.py). <0 or unknown = no club.
    player_fk: int

    @classmethod
    def unpack(cls, buf: bytes, index: int) -> "StaffRecord":
        base = index * STAFF_RECORD_LEN
        sid, fn, sn, cn = struct.unpack_from("<iiii", buf, base + S_ID)
        nation = struct.unpack_from("<i", buf, base + S_NATION)[0]
        club = struct.unpack_from("<i", buf, base + S_CLUB)[0]
        player_fk = struct.unpack_from("<i", buf, base + S_PLAYER_FK)[0]
        return cls(index, sid, fn, sn, cn, nation, club, player_fk)


@dataclass(frozen=True)
class PlayerRecord:
    index: int
    player_id: int
    ca: int
    pa: int
    reputation: int

    @classmethod
    def unpack(cls, buf: bytes, index: int) -> "PlayerRecord":
        base = index * PLAYER_RECORD_LEN
        pid = struct.unpack_from("<i", buf, base + P_ID)[0]
        ca, pa, rep = struct.unpack_from("<hhh", buf, base + P_CA)
        return cls(index, pid, ca, pa, rep)

    @property
    def effective_pa(self) -> int:
        """Absolute potential. A negative PA in CM 01/02 is a masked value
        (the game rolls a real PA up to this magnitude); for filtering and
        display we want the magnitude."""
        return abs(self.pa)


def iter_staff(buf: bytes):
    for i in range(len(buf) // STAFF_RECORD_LEN):
        yield StaffRecord.unpack(buf, i)


def iter_players(buf: bytes):
    for i in range(len(buf) // PLAYER_RECORD_LEN):
        yield PlayerRecord.unpack(buf, i)


def read_attr_byte(buf: bytes, player_index: int, offset: int) -> int:
    return buf[player_index * PLAYER_RECORD_LEN + offset]
