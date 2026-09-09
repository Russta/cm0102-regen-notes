"""Command-line entry point.

    cm0102-regen-notes list-blocks    SAVE
    cm0102-regen-notes extract-block  SAVE BLOCK_NAME OUT_FILE
    cm0102-regen-notes dump-notes     SAVE
    cm0102-regen-notes write-note     SAVE OUT_SAVE STAFF_ID TEXT
    cm0102-regen-notes snapshot       SAVE [OUT.rnw]
    cm0102-regen-notes match          SAVE BASELINE(.gpf2|.rnw) [--potential-min N] [--csv OUT]
    cm0102-regen-notes annotate       SAVE BASELINE OUT_SAVE [--potential-min N] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .annotate import apply_annotations, apply_annotations_in_place, plan_annotations
from .match import find_regens, write_csv
from .notes import parse_notes, write_note
from .savfile import SavFile
from .snapshot import write_snapshot


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
    s = write_note(args.save, args.out, args.staff_id, args.text)
    print(
        f"staff_id={s['staff_id']}: {s['action']} record. "
        f"notes.dat {s['notes_size_before']:,} -> {s['notes_size_after']:,} "
        f"(delta {s['delta']:+}). output: {s['out_path']}"
    )
    return 0


def _cmd_snapshot(args: argparse.Namespace) -> int:
    out, data = write_snapshot(args.save, args.out)
    gd = data["game_date"]
    print(f"snapshot written: {out}  ({out.stat().st_size:,} bytes, {data['player_count']:,} slots)")
    print(f"in-game date in this save: day {gd['day']} of {gd['year']}")
    print("note: a snapshot is only a useful baseline if taken on (or near) day one of a new save.")
    return 0


def _cmd_match(args: argparse.Namespace) -> int:
    matches = find_regens(
        args.save, args.baseline,
        potential_min=args.potential_min,
        original_potential_min=args.original_potential_min,
    )
    print(f"{len(matches)} regen(s)"
          + (f" with current PA >= {args.potential_min}" if args.potential_min else "")
          + f"  (baseline: {Path(args.baseline).name})\n")
    for m in sorted(matches, key=lambda m: (-m.current_pa, m.slot))[: args.limit]:
        origin = m.original_name or "(empty slot)"
        opa = f" origPA={m.original_pa}" if m.original_pa is not None else ""
        club = f" @ {m.current_club}" if m.current_club else ""
        print(f"  slot {m.slot:<7} PA={m.current_pa:<4} CA={m.current_ca:<4} "
              f"{m.current_name!r:<26}{club:<24} <- regen of {origin!r}{opa}")
    if args.limit and len(matches) > args.limit:
        print(f"  ... {len(matches) - args.limit} more (raise --limit or use --csv)")
    if args.csv:
        write_csv(matches, args.csv)
        print(f"\nfull list -> {args.csv}")
    return 0


def _cmd_annotate(args: argparse.Namespace) -> int:
    if not args.in_place and not args.out:
        print("give an OUT_SAVE, or pass --in-place to write back into SAVE", file=sys.stderr)
        return 2
    if args.out and not args.in_place and Path(args.out).resolve() == Path(args.save).resolve():
        print("OUT_SAVE is the same file as SAVE; pass --in-place if that's intended", file=sys.stderr)
        return 2

    plan = plan_annotations(
        args.save, args.baseline,
        potential_min=args.potential_min,
        original_potential_min=args.original_potential_min,
        annotate_empty_origin=args.include_empty_origin,
    )
    print(f"{len(plan.to_write)} note(s) to write; "
          f"{len(plan.skipped_empty_origin)} skipped (empty-slot origin); "
          f"{len(plan.skipped_too_long)} skipped (name too long)")
    for m in sorted(plan.to_write, key=lambda m: (-m.current_pa, m.slot))[:20]:
        print(f"  staff {m.current_staff_id:<7} {m.current_name!r:<26} <- {m.original_name!r}")
    if len(plan.to_write) > 20:
        print(f"  ... and {len(plan.to_write) - 20} more")
    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    if args.in_place:
        s = apply_annotations_in_place(args.save, plan, backup=args.backup)
        if s.get("backup"):
            print(f"backup: {s['backup']}")
    else:
        s = apply_annotations(args.save, args.out, plan)
    print(f"\nwrote {s['notes_written']} note(s) ({s['appended']} new, {s['overwrote']} updated), "
          f"notes.dat delta {s['delta']:+}. output: {s['out_path']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cm0102-regen-notes", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-blocks", help="list every named block in a save")
    p.add_argument("save")
    p.set_defaults(func=_cmd_list_blocks)

    p = sub.add_parser("extract-block", help="write one block's raw bytes to a file")
    p.add_argument("save"); p.add_argument("block"); p.add_argument("out")
    p.set_defaults(func=_cmd_extract_block)

    p = sub.add_parser("dump-notes", help="print every note record in a save")
    p.add_argument("save")
    p.set_defaults(func=_cmd_dump_notes)

    p = sub.add_parser("write-note", help="write one note into a save (to a new file)")
    p.add_argument("save"); p.add_argument("out")
    p.add_argument("staff_id", type=int); p.add_argument("text")
    p.set_defaults(func=_cmd_write_note)

    p = sub.add_parser("snapshot", help="write a day-one .rnw snapshot next to a save")
    p.add_argument("save")
    p.add_argument("out", nargs="?", help="defaults to <save>.rnw")
    p.set_defaults(func=_cmd_snapshot)

    p = sub.add_parser("match", help="list regens: current name vs day-one baseline name")
    p.add_argument("save")
    p.add_argument("baseline", help="a .gpf2 (from GPF2) or a .rnw (from snapshot)")
    p.add_argument("--potential-min", type=int, default=None,
                   help="only regens whose CURRENT player has PA >= this (GPF2's filter)")
    p.add_argument("--original-potential-min", type=int, default=None,
                   help="only regens whose ORIGINAL (day-one) player had PA >= this; needs a .rnw baseline")
    p.add_argument("--limit", type=int, default=40, help="max rows to print (default 40)")
    p.add_argument("--csv", default=None, help="also write the full list to this CSV")
    p.set_defaults(func=_cmd_match)

    p = sub.add_parser("annotate", help="write each regen's original identity into their Notes")
    p.add_argument("save")
    p.add_argument("baseline")
    p.add_argument("out", nargs="?", help="output save file; omit and pass --in-place to edit SAVE")
    p.add_argument("--in-place", action="store_true",
                   help="write back into SAVE (atomic replace via a temp file)")
    p.add_argument("--backup", action="store_true",
                   help="with --in-place, copy SAVE to a timestamped backup first")
    p.add_argument("--potential-min", type=int, default=None)
    p.add_argument("--original-potential-min", type=int, default=None)
    p.add_argument("--include-empty-origin", action="store_true",
                   help="also annotate regens whose slot had no day-one occupant")
    p.add_argument("--dry-run", action="store_true", help="show what would be written, write nothing")
    p.set_defaults(func=_cmd_annotate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
