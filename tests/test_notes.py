"""Self-contained tests: no real save needed.

They fabricate a minimal but format-accurate ``.sav`` in memory and exercise
the block table, note parsing, and both write paths (in-place overwrite and
append-with-downstream-shift).
"""

from __future__ import annotations

import struct

import pytest

from cm0102_regen_notes.notes import (
    NO_REMINDER_SENTINEL,
    NOTE_RECORD_LEN,
    build_updated_notes_block,
    get_current_game_date_bytes,
    parse_notes,
)
from cm0102_regen_notes.savfile import HEADER_LEN, BLOCK_TABLE_ENTRY_LEN, SavFile

GENERAL_DATE = struct.pack("<hhi", 200, 2025, 0)  # day 200, year 2025


def _note_record(staff_id: int, text: str, reminder: bytes = NO_REMINDER_SENTINEL) -> bytes:
    rec = bytearray(NOTE_RECORD_LEN)
    struct.pack_into("<i", rec, 0, staff_id)
    enc = text.encode("latin-1") + b"\x00"
    rec[4 : 4 + len(enc)] = enc
    rec[259:267] = struct.pack("<hhi", 100, 2024, 0)  # arbitrary "created"
    rec[267:275] = reminder
    return bytes(rec)


def _notes_block(records: list[bytes]) -> bytes:
    return struct.pack("<i", len(records)) + b"".join(records) + b"\x00" * 124


def _build_sav(notes_block: bytes) -> bytes:
    """general.dat, then notes.dat, then player.dat -- in that file order."""
    general = b"\x00" * 3944 + GENERAL_DATE + b"\x00" * 48  # 4000 bytes
    player = bytes(range(50))

    blocks = [("general.dat", general), ("notes.dat", notes_block), ("player.dat", player)]
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


def test_block_table_roundtrips():
    sav = SavFile(_build_sav(_notes_block([_note_record(1, "hello")])))
    assert [b.name for b in sav.blocks] == ["general.dat", "notes.dat", "player.dat"]
    assert not sav.compressed
    assert sav.block("player.dat").end == len(sav.data)


def test_current_game_date_read_from_general():
    sav = SavFile(_build_sav(_notes_block([_note_record(1, "hello")])))
    assert get_current_game_date_bytes(sav) == GENERAL_DATE


def test_parse_notes():
    block = _notes_block([_note_record(10, "Messi"), _note_record(20, "Ronaldo")])
    notes = parse_notes(block)
    assert [(n.staff_id, n.text) for n in notes] == [(10, "Messi"), (20, "Ronaldo")]
    assert all(not n.has_reminder for n in notes)


def test_overwrite_in_place_keeps_size_and_dates():
    original = _note_record(42, "old text", reminder=struct.pack("<hhi", 5, 2030, 0))
    block = _notes_block([original])
    new_block, appended = build_updated_notes_block(block, 42, "brand new text")

    assert appended is False
    assert len(new_block) == len(block)
    note = parse_notes(new_block)[0]
    assert note.text == "brand new text"
    # dates untouched -> the real reminder survives
    assert note.reminder_raw == struct.pack("<hhi", 5, 2030, 0)
    assert note.created_raw == original[259:267]


def test_append_grows_block_and_sets_no_reminder_sentinel():
    block = _notes_block([_note_record(1, "existing")])
    new_block, appended = build_updated_notes_block(block, 999, "Lewandowski", GENERAL_DATE)

    assert appended is True
    assert len(new_block) == len(block) + NOTE_RECORD_LEN
    notes = parse_notes(new_block)
    assert [n.staff_id for n in notes] == [1, 999]
    added = notes[1]
    assert added.text == "Lewandowski"
    assert added.reminder_raw == NO_REMINDER_SENTINEL
    assert added.created_raw == GENERAL_DATE


def test_write_note_shifts_downstream_blocks(tmp_path):
    from cm0102_regen_notes.notes import write_note

    src = tmp_path / "in.sav"
    dst = tmp_path / "out.sav"
    src.write_bytes(_build_sav(_notes_block([_note_record(1, "existing")])))

    before = SavFile.load(src)
    player_before = before.read_block("player.dat")

    write_note(src, dst, staff_id=777, text="Zidane")

    after = SavFile.load(dst)
    assert after.block("general.dat").position == before.block("general.dat").position
    shift = after.block("player.dat").position - before.block("player.dat").position
    assert shift == NOTE_RECORD_LEN
    # downstream block content preserved byte-for-byte
    assert after.read_block("player.dat") == player_before
    assert after.read_block("general.dat") == before.read_block("general.dat")
    assert [n.staff_id for n in parse_notes(after.read_block("notes.dat"))] == [1, 777]


def test_text_too_long_rejected():
    block = _notes_block([_note_record(1, "x")])
    with pytest.raises(ValueError):
        build_updated_notes_block(block, 2, "A" * 255)
