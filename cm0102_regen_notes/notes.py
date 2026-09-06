"""The ``notes.dat`` block -- the in-game per-player "Notes" tab -- and the
function that writes into it.

Block layout (little-endian)::

    offset 0            int32   entry count N
    offset 4            N x 276-byte records, densely packed:
        [0:4]     int32   TStaff.ID   (same ID space as staff.dat)
        [4:259]   note text, Latin-1, null-terminated (254 usable chars)
        [259:267] "created" date  -- TCMDate, 8 bytes
        [267:275] "reminder" date -- TCMDate, 8 bytes
        [275]     unused (0 in every observed record)
    offset 4+N*276     124 bytes, always zero (trailer / reserve)

    total size = 4 + N*276 + 124

TCMDate is ``int16 day`` (0-indexed day-of-year), ``int16 year``,
``int32 leap_year``.

**The reminder field is not "zero means none".** The game's real
"No Reminder" sentinel is the exact bytes ``EA 00 B3 07 00 00 00 00``
(day 234, year 1971, leap_year 0) -- identical across every hand-created
note in the reference save. Writing plain zeros instead shows a bogus
"01.01.0000" reminder in-game, so any new record must use this sentinel
unless a real reminder is intended.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .savfile import SavFile

NOTE_RECORD_LEN = 276
TEXT_OFFSET = 4
TEXT_FIELD_LEN = 255  # bytes 4..258 inclusive
NOTE_TEXT_MAX = TEXT_FIELD_LEN - 1  # room for the null terminator
CREATED_OFFSET = 259
REMINDER_OFFSET = 267
TCMDATE_LEN = 8
TRAILER_LEN = 124

#: The game's "No Reminder" marker -- day 234, year 1971, leap_year 0.
NO_REMINDER_SENTINEL = bytes.fromhex("EA00B30700000000")

#: TCMDate lives at this offset inside general.dat; mirrors
#: SaveReader.GetCurrentGameDate() in the agevak reference.
GENERAL_DAT_DATE_OFFSET = 3944


@dataclass(frozen=True)
class TCMDate:
    day: int  # 0-indexed day of year
    year: int
    leap_year: int

    @classmethod
    def unpack(cls, raw: bytes) -> "TCMDate":
        day, year, leap_year = struct.unpack("<hhi", raw)
        return cls(day=day, year=year, leap_year=leap_year)

    def pack(self) -> bytes:
        return struct.pack("<hhi", self.day, self.year, self.leap_year)


@dataclass(frozen=True)
class Note:
    staff_id: int
    text: str
    created_raw: bytes
    reminder_raw: bytes

    @property
    def created(self) -> TCMDate:
        return TCMDate.unpack(self.created_raw)

    @property
    def has_reminder(self) -> bool:
        return self.reminder_raw != NO_REMINDER_SENTINEL


def parse_notes(block: bytes) -> list[Note]:
    """Parse a raw ``notes.dat`` block into :class:`Note` records."""
    count = struct.unpack_from("<i", block, 0)[0]
    expected = 4 + count * NOTE_RECORD_LEN + TRAILER_LEN
    if len(block) != expected:
        raise ValueError(
            f"notes.dat is {len(block)} bytes but count={count} implies {expected}"
        )

    notes = []
    for i in range(count):
        base = 4 + i * NOTE_RECORD_LEN
        staff_id = struct.unpack_from("<i", block, base)[0]
        text = (
            block[base + TEXT_OFFSET : base + TEXT_OFFSET + TEXT_FIELD_LEN]
            .split(b"\x00", 1)[0]
            .decode("latin-1")
        )
        created_raw = block[base + CREATED_OFFSET : base + CREATED_OFFSET + TCMDATE_LEN]
        reminder_raw = block[base + REMINDER_OFFSET : base + REMINDER_OFFSET + TCMDATE_LEN]
        notes.append(Note(staff_id, text, created_raw, reminder_raw))
    return notes


def get_current_game_date_bytes(sav: SavFile) -> bytes:
    """The current in-game date, as raw TCMDate bytes, read from general.dat."""
    general = sav.block("general.dat")
    start = general.position + GENERAL_DAT_DATE_OFFSET
    return sav.data[start : start + TCMDATE_LEN]


def build_updated_notes_block(
    notes_bytes: bytes,
    staff_id: int,
    text: str,
    created_date_bytes: bytes | None = None,
) -> tuple[bytes, bool]:
    """Return ``(new_block_bytes, appended)``.

    If ``staff_id`` already has a note, its **text** is overwritten in place and
    both dates are left exactly as they were (preserving any real reminder the
    human manager set). ``appended`` is False and the block size is unchanged.

    Otherwise a new 276-byte record is inserted just before the trailer: the
    given text, ``created_date_bytes`` as the created date (zeros if omitted),
    and :data:`NO_REMINDER_SENTINEL` as the reminder. ``appended`` is True and
    the block grows by exactly one record.
    """
    encoded = text.encode("latin-1")
    if len(encoded) > NOTE_TEXT_MAX:
        raise ValueError(
            f"note text is {len(encoded)} bytes; max is {NOTE_TEXT_MAX}"
        )
    text_bytes = encoded + b"\x00"

    count = struct.unpack_from("<i", notes_bytes, 0)[0]

    for i in range(count):
        base = 4 + i * NOTE_RECORD_LEN
        if struct.unpack_from("<i", notes_bytes, base)[0] == staff_id:
            out = bytearray(notes_bytes)
            text_start = base + TEXT_OFFSET
            # Clear the whole text field, then lay down the new string.
            out[text_start : text_start + TEXT_FIELD_LEN] = b"\x00" * TEXT_FIELD_LEN
            out[text_start : text_start + len(text_bytes)] = text_bytes
            return bytes(out), False

    insert_at = 4 + count * NOTE_RECORD_LEN
    record = bytearray(NOTE_RECORD_LEN)
    struct.pack_into("<i", record, 0, staff_id)
    record[TEXT_OFFSET : TEXT_OFFSET + len(text_bytes)] = text_bytes
    if created_date_bytes:
        record[CREATED_OFFSET : CREATED_OFFSET + TCMDATE_LEN] = created_date_bytes
    record[REMINDER_OFFSET : REMINDER_OFFSET + TCMDATE_LEN] = NO_REMINDER_SENTINEL

    out = bytearray(notes_bytes)
    struct.pack_into("<i", out, 0, count + 1)
    out[insert_at:insert_at] = record
    return bytes(out), True


def write_note(
    in_path: str | Path,
    out_path: str | Path,
    staff_id: int,
    text: str,
) -> dict:
    """Write one note into ``in_path`` and save the result to ``out_path``.

    The input file is read but never modified. Returns a summary dict.
    """
    sav = SavFile.load(in_path)
    if sav.compressed:
        raise NotImplementedError("compressed saves are not supported for writing")

    notes_block = sav.block("notes.dat")
    p, s = notes_block.position, notes_block.size
    old_notes = sav.data[p : p + s]

    created = get_current_game_date_bytes(sav)
    new_notes, appended = build_updated_notes_block(old_notes, staff_id, text, created)
    delta = len(new_notes) - len(old_notes)

    result = bytearray(sav.data)

    if delta != 0:
        # Patch the block table: notes.dat's own size, and the position of
        # every block physically stored after it.
        for b in sav.blocks:
            if b.name == "notes.dat":
                struct.pack_into("<I", result, b.table_off + 4, len(new_notes))
            elif b.position > p:
                struct.pack_into("<I", result, b.table_off, b.position + delta)

    result[p : p + s] = new_notes

    Path(out_path).write_bytes(result)

    return {
        "staff_id": staff_id,
        "action": "appended" if appended else "overwrote",
        "notes_size_before": s,
        "notes_size_after": len(new_notes),
        "delta": delta,
        "out_path": str(out_path),
    }
