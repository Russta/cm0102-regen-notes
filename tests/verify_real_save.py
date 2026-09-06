"""Full byte-integrity check of the write path against a real save.

Not part of the pytest suite (needs a large real file). Run it directly::

    python tests/verify_real_save.py "C:/path/to/real.sav" [STAFF_ID] [TEXT]

It writes a note to a temp copy, then verifies:
  * every block except notes.dat is byte-for-byte identical to the original;
  * notes.dat gained exactly one record (or was overwritten in place);
  * the block table is internally consistent (positions contiguous, sizes fit);
  * the whole file grew by exactly the size delta and nothing else moved.

Exits 0 on success, 1 on any mismatch.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cm0102_regen_notes.notes import parse_notes, write_note  # noqa: E402
from cm0102_regen_notes.savfile import SavFile  # noqa: E402


def verify(real_save: str, staff_id: int, text: str) -> int:
    src = SavFile.load(real_save)
    print(f"loaded {real_save}  ({len(src.data):,} bytes, {src.block_count} blocks)")
    if src.compressed:
        print("FAIL: save is compressed; write path does not support it")
        return 1

    notes_before = parse_notes(src.read_block("notes.dat"))
    existing = {n.staff_id for n in notes_before}
    appending = staff_id not in existing
    print(f"notes.dat: {len(notes_before)} records; staff_id {staff_id} "
          f"{'absent -> will append' if appending else 'present -> will overwrite'}")

    with tempfile.TemporaryDirectory() as td:
        out = str(Path(td) / "verify_out.sav")
        summary = write_note(real_save, out, staff_id, text)
        print(f"write_note: {summary['action']}, delta {summary['delta']:+} bytes")

        dst = SavFile.load(out)
        problems: list[str] = []

        expected_len = len(src.data) + summary["delta"]
        if len(dst.data) != expected_len:
            problems.append(f"file length {len(dst.data):,} != expected {expected_len:,}")

        if dst.block_count != src.block_count:
            problems.append(f"block count changed {src.block_count} -> {dst.block_count}")

        p_notes = src.block("notes.dat").position
        for sb in src.blocks:
            db = dst.block(sb.name)
            if sb.name == "notes.dat":
                if db.size != sb.size + summary["delta"]:
                    problems.append(f"notes.dat size {sb.size} -> {db.size}, expected delta {summary['delta']:+}")
                continue
            expected_pos = sb.position + (summary["delta"] if sb.position > p_notes else 0)
            if db.position != expected_pos:
                problems.append(f"{sb.name}: position {sb.position:#x} -> {db.position:#x}, expected {expected_pos:#x}")
            if db.size != sb.size:
                problems.append(f"{sb.name}: size {sb.size} -> {db.size}")
            if src.read_block(sb.name) != dst.read_block(sb.name):
                problems.append(f"{sb.name}: block CONTENT differs")

        # block table internal consistency on the output
        ordered = sorted(dst.blocks, key=lambda b: b.position)
        for a, b in zip(ordered, ordered[1:]):
            if a.position + a.size > b.position:
                problems.append(f"overlap: {a.name} ends {a.position + a.size:#x} > {b.name} at {b.position:#x}")
        if ordered[-1].position + ordered[-1].size > len(dst.data):
            problems.append("last block runs past end of file")

        notes_after = parse_notes(dst.read_block("notes.dat"))
        if appending and len(notes_after) != len(notes_before) + 1:
            problems.append(f"note count {len(notes_before)} -> {len(notes_after)}, expected +1")
        if not appending and len(notes_after) != len(notes_before):
            problems.append(f"note count changed on overwrite: {len(notes_before)} -> {len(notes_after)}")
        match = next((n for n in notes_after if n.staff_id == staff_id), None)
        if match is None or match.text != text:
            problems.append(f"written note not found / text mismatch (got {match!r})")
        elif appending and match.has_reminder:
            problems.append("appended note has a reminder set; expected the No-Reminder sentinel")

    if problems:
        print(f"\nFAIL ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"\nOK: {src.block_count - 1} other blocks byte-identical, "
          f"table consistent, note written correctly.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    save = sys.argv[1]
    sid = int(sys.argv[2]) if len(sys.argv) > 2 else 67524  # Michal Jankowski in the reference save
    txt = sys.argv[3] if len(sys.argv) > 3 else "verify_real_save integrity check"
    raise SystemExit(verify(save, sid, txt))
