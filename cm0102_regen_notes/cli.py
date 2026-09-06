"""Command-line entry point.

    cm0102-regen-notes list-blocks   SAVE
    cm0102-regen-notes extract-block SAVE BLOCK_NAME OUT_FILE
    cm0102-regen-notes write-note    SAVE OUT_SAVE STAFF_ID TEXT
    cm0102-regen-notes dump-notes    SAVE

The snapshot / match / annotate subcommands land here as they're built.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .notes import parse_notes, write_note
from .savfile import SavFile


def _cmd_list_blocks(args: argparse.Namespace) -> int:
    sav = SavFile.load(args.save)
    print(
        f"marker={sav.marker} (compressed={sav.compressed})  "
        f"unknown_hdr=0x{sav.unknown_hdr:X}  blocks={sav.block_count}\n"
    )
    for block in sorted(sav.blocks, key=lambda b: b.name):
        print(f"{block.name:<32} pos=0x{block.position:010X}  size={block.size:>13,}")
    return 0


def _cmd_extract_block(args: argparse.Namespace) -> int:
    sav = SavFile.load(args.save)
    data = sav.read_block(args.block)
    Path(args.out).write_bytes(data)
    print(f"wrote {len(data):,} bytes from block {args.block!r} to {args.out}")
    return 0


def _cmd_dump_notes(args: argparse.Namespace) -> int:
    sav = SavFile.load(args.save)
    notes = parse_notes(sav.read_block("notes.dat"))
    print(f"{len(notes)} note(s) in {args.save}\n")
    for note in notes:
        d = note.created
        reminder = "reminder set" if note.has_reminder else "no reminder"
        print(f"  staff_id={note.staff_id:<8} [{reminder}] created(day={d.day},year={d.year})")
        print(f"    {note.text!r}")
    return 0


def _cmd_write_note(args: argparse.Namespace) -> int:
    if Path(args.out).resolve() == Path(args.save).resolve():
        print("refusing to write over the input save; choose a different OUT_SAVE", file=sys.stderr)
        return 2
    summary = write_note(args.save, args.out, args.staff_id, args.text)
    print(
        f"staff_id={summary['staff_id']}: {summary['action']} record. "
        f"notes.dat {summary['notes_size_before']:,} -> {summary['notes_size_after']:,} "
        f"(delta {summary['delta']:+}). output: {summary['out_path']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cm0102-regen-notes", description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-blocks", help="list every named block in a save")
    p.add_argument("save")
    p.set_defaults(func=_cmd_list_blocks)

    p = sub.add_parser("extract-block", help="write one block's raw bytes to a file")
    p.add_argument("save")
    p.add_argument("block")
    p.add_argument("out")
    p.set_defaults(func=_cmd_extract_block)

    p = sub.add_parser("dump-notes", help="print every note record in a save")
    p.add_argument("save")
    p.set_defaults(func=_cmd_dump_notes)

    p = sub.add_parser("write-note", help="write one note into a save (to a new file)")
    p.add_argument("save")
    p.add_argument("out")
    p.add_argument("staff_id", type=int)
    p.add_argument("text")
    p.set_defaults(func=_cmd_write_note)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
