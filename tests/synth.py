"""Build a tiny but format-accurate ``.sav`` (and matching ``.gpf2``) in memory,
for tests that need staff / players / names, not just notes.
"""

from __future__ import annotations

import struct

from cm0102_regen_notes.savfile import HEADER_LEN, BLOCK_TABLE_ENTRY_LEN
from cm0102_regen_notes.records import (
    STAFF_RECORD_LEN, PLAYER_RECORD_LEN, S_PLAYER_FK, S_NATION, S_CLUB,
)
from cm0102_regen_notes.names import TNAMES_RECORD_LEN
from cm0102_regen_notes.clubs import CLUB_RECORD_LEN, C_LONG_NAME, C_SHORT_NAME
from cm0102_regen_notes.gpf2 import GPF2_RECORD_LEN

GENERAL_DATE = struct.pack("<hhi", 12, 2025, 0)


def name_table(names: list[str]) -> bytes:
    out = bytearray()
    for i, nm in enumerate(names):
        rec = bytearray(TNAMES_RECORD_LEN)
        enc = nm.encode("latin-1")[:50]
        rec[0 : len(enc)] = enc
        struct.pack_into("<ii", rec, 51, i, 0)  # embedded id, nation
        out += rec
    return bytes(out)


def staff_record(staff_id: int, first: int, second: int, common: int,
                 player_fk: int, nation: int = 0, club: int = -1) -> bytes:
    rec = bytearray(STAFF_RECORD_LEN)
    struct.pack_into("<iiii", rec, 0, staff_id, first, second, common)
    struct.pack_into("<i", rec, S_NATION, nation)
    struct.pack_into("<i", rec, S_CLUB, club)
    struct.pack_into("<i", rec, S_PLAYER_FK, player_fk)
    return bytes(rec)


def club_table(clubs: list[tuple[int, str]]) -> bytes:
    """``clubs`` is a list of ``(club_id, name)``."""
    out = bytearray()
    for club_id, name in clubs:
        rec = bytearray(CLUB_RECORD_LEN)
        struct.pack_into("<i", rec, 0, club_id)
        enc = name.encode("latin-1")
        rec[C_LONG_NAME : C_LONG_NAME + len(enc)] = enc
        rec[C_SHORT_NAME : C_SHORT_NAME + len(enc)] = enc
        out += rec
    return bytes(out)


def player_record(index: int, ca: int, pa: int, rep: int = 0) -> bytes:
    rec = bytearray(PLAYER_RECORD_LEN)
    struct.pack_into("<i", rec, 0, index)
    struct.pack_into("<hhh", rec, 5, ca, pa, rep)
    return bytes(rec)


def notes_block(records: list[bytes]) -> bytes:
    return struct.pack("<i", len(records)) + b"".join(records) + b"\x00" * 124


def build_sav(blocks: list[tuple[str, bytes]]) -> bytes:
    table_start = HEADER_LEN
    data_start = table_start + len(blocks) * BLOCK_TABLE_ENTRY_LEN
    table = bytearray()
    data = bytearray()
    pos = data_start
    for name, payload in blocks:
        entry = bytearray(BLOCK_TABLE_ENTRY_LEN)
        struct.pack_into("<II", entry, 0, pos, len(payload))
        entry[8 : 8 + len(name)] = name.encode("ascii")
        table += entry
        data += payload
        pos += len(payload)
    header = struct.pack("<iii", 3, 0x16, len(blocks))
    return header + bytes(table) + bytes(data)


def gpf2_bytes(triples: list[tuple[int, int, int]]) -> bytes:
    out = bytearray()
    for i, (f, s, c) in enumerate(triples):
        out += struct.pack("<iiii", f, s, c, i)
    return bytes(out)


def make_world():
    """A 4-slot world. Slot 2's occupant changed (regen); the rest are stable.

    Returns ``(sav_bytes, gpf2_bytes, meta)``.
    """
    firsts = ["", "Lionel", "Cristiano", "Zinedine", "Reginald"]
    seconds = ["", "Messi", "Ronaldo", "Zidane", "Bloggs"]
    commons = [""]

    # day one: slots 0..3 hold Messi, Ronaldo, Zidane, Bloggs
    day1 = [(1, 1), (2, 2), (3, 3), (4, 4)]  # (first_idx, second_idx)

    # now: slot 2 (Zidane) has been regenerated into "Reginald Bloggs", at Real Madrid
    staff = [
        staff_record(101, 1, 1, 0, player_fk=0, nation=7, club=10),
        staff_record(102, 2, 2, 0, player_fk=1, nation=7, club=11),
        staff_record(103, 4, 4, 0, player_fk=2, nation=1, club=12),  # regen in Zidane's slot
        staff_record(104, 4, 4, 0, player_fk=3, nation=9, club=-1),  # no club
    ]
    players = [
        player_record(0, ca=160, pa=180),
        player_record(1, ca=170, pa=190),
        player_record(2, ca=120, pa=175),   # the regen: high PA
        player_record(3, ca=90, pa=110),
    ]
    general = b"\x00" * 3944 + GENERAL_DATE + b"\x00" * 8
    blocks = [
        ("general.dat", general),
        ("first_names.dat", name_table(firsts)),
        ("second_names.dat", name_table(seconds)),
        ("common_names.dat", name_table(commons)),
        ("club.dat", club_table([(10, "Barcelona"), (11, "Manchester United"), (12, "Real Madrid")])),
        ("staff.dat", b"".join(staff)),
        ("player.dat", b"".join(players)),
        ("notes.dat", notes_block([])),
    ]
    sav = build_sav(blocks)
    gpf2 = gpf2_bytes([(1, 1, 0), (2, 2, 0), (3, 3, 0), (4, 4, 0)])
    meta = {"regen_slot": 2, "regen_staff_id": 103, "regen_original": "Zinedine Zidane",
            "regen_club": "Real Madrid"}
    return sav, gpf2, meta
