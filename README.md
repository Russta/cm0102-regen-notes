# CM 01/02 Regen Notes Tool

A Windows tool for **Championship Manager 01/02** that identifies
which of your current players are **regens** of original players, and
writes the original name into each regen's in-game **Notes** directly in
the `.sav` without launching the game.

It's the same idea as the community's Generated Player Finder (GPF2/GPF3),
rebuilt from scratch as a single double-click `.exe` with the source in the
open.

## How it works

1. **On day one of a new save**, take a snapshot (`Career.sav.rnw`) — one
   record per `player.dat` slot: the occupant's name plus CA and PA.
2. **Later**, the tool compares the live save to that snapshot. `player.dat`
   slots are fixed for the life of a save, so a slot whose current occupant's
   name differs from its day-one name is holding a regen — and the day-one
   name is who they replaced. The slot number *is* the link; there's no
   attribute-fingerprint guessing. On the reference save it rediscovers every
   known regen (Messi, Ronaldo, Lewandowski, etc).
3. **Filter** by minimum PA (of the current player — the same thing GPF2's
   "potential >=" button does), or by name.
4. **Export** the list to CSV, and/or **write** each original name into its
   regen's Notes tab.

## What it does that the older tools don't

- **Writes the results back into the save.** GPF2/GPF3 only show you a list;
  this annotates every regen's in-game Notes for you, offline, in one pass
  without renaming the player itself.
- **Reads GPF2's `.gpf2` directly.** If you already snapshot with GPF2 this
  is backward compatible with your old files. It also has its own `.rnw` file
  format snapshot, which additionally stores CA and PA, plus each player's
  nation as an index into `nation.dat` — nothing reads the nation yet, it's
  just captured as additional assistance for later.
- **CSV export that opens cleanly in Excel.** Specifically formatted as UTF-8
  with BOM, so accented names ("Tchouaméni", "Müller", etc.) aren't mojibaked.
- **Shows Player ID and Staff ID.** The `player.dat` index and the
  `staff.dat` id to allow for reverse lookups to other editors and tools.
- **Accent-insensitive search.** Searching for "Aurelien" finds "Aurélien".
- **Safe writes.** Temp-file-plus-atomic-replace, optional timestamped
  backup, and a warning if CM01/02 is running to prevent Note overwrites.
  Byte-for-byte integrity checked against 500 MB+ saves.
- **Open source (MIT).** Plain `.exe` to be user friendly and nothing
  hidden about what it's doing to your save.

See [`docs/HANDOFF.md`](docs/HANDOFF.md) and
[`docs/gpf2-and-matching.md`](docs/gpf2-and-matching.md) for the
reverse-engineering notes — save format, `notes.dat` layout, the `TStaff` /
`TPlayer` structs, the `.gpf2` format, and the "No Reminder" sentinel a naïve
writer gets wrong.

## Safety

The GUI writes into the save you pick (temp file + atomic replace, with a
"back up save" checkbox on by default). `annotate` on the command line
defaults to a new output file. Either way the input is only overwritten when
you ask for it, and every non-`notes.dat` block is preserved byte-for-byte.
Keep your own backups anyway — this edits an undocumented binary format.

## Usage

Double-click the `.exe` (or run `python -m cm0102_regen_notes.gui` from
source) for the GUI: pick your save and a **regen file** (a `.gpf2` from
GPF2, or a `.rnw` from **Take snapshot now**), set the minimum PA, **Find
Regens**, filter by name if you want, then **Export CSV…** or **Write notes
to save**. Writing goes **into the save you picked** (with a "back up save"
checkbox, on by default, that drops a timestamped copy alongside it); it's
done via a temp file + atomic replace so a crash can't corrupt the save.

### Command line (from source)

```bash
pip install -e .

# on day one of a new save (immediately after the first save), take a baseline:
cm0102-regen-notes snapshot "Career.sav"              # -> Career.sav.rnw
#   ...or just use GPF2's Career.sav.gpf2 if you already run GPF2

# later, after regens have appeared:
cm0102-regen-notes match    "Career.sav" "Career.sav.gpf2" --potential-min 150 --csv regens.csv
cm0102-regen-notes annotate "Career.sav" "Career.sav.gpf2" "Career_annotated.sav" --potential-min 150
cm0102-regen-notes annotate "Career.sav" "Career.sav.gpf2" --in-place --backup --potential-min 150

# low-level helpers:
cm0102-regen-notes list-blocks   "Career.sav"
cm0102-regen-notes dump-notes    "Career.sav"
cm0102-regen-notes extract-block "Career.sav" notes.dat notes.bin
cm0102-regen-notes write-note    "Career.sav" "out.sav" 67524 "Robert Lewandowski"
```

`match` and `annotate` accept either a `.gpf2` (from GPF2) or a `.rnw` (from
`snapshot`) as the day-one baseline. `annotate` writes to a new `OUT_SAVE`,
or edits `SAVE` directly with `--in-place` (add `--backup` for a timestamped
copy first; the write is a temp-file + atomic replace either way).
`write-note` always writes a new file. `annotate --dry-run` shows what it
would write without touching anything.

## Development

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_notes.py` and `tests/test_match.py` are self-contained (they
fabricate a format-accurate mini-save via `tests/synth.py`).
`tests/verify_real_save.py` is a separate, heavier check you point at a real
`.sav` — it writes a note to a temp copy and confirms every other block is
byte-for-byte identical afterwards.

## Prior art and credit

This project is a clean-room reimplementation. No third-party code is copied
in. The save-format understanding was informed by, and cross-checked against,
these community projects:

- **[agevak/CM0102](https://github.com/agevak/CM0102)** and
  **agevak/CM0102SaveGameTacticsEditor** — C#; source of the initial
  `TStaff` / `TPlayer` / block-table layout (independently re-verified here
  against real save data). No `LICENSE` file present, so nothing from them is
  vendored.
- **[ChrisReganXP/CMScouter](https://github.com/ChrisReganXP/CMScouter)** —
  C#; cross-checked the `TPlayer` attribute offsets (CA at byte 5, PA at byte
  7, etc.) and the `staff.dat` / `player.dat` / name-table record sizes
  against its data classes. Verified against real save data; no code copied.
- **GPF / GPF2 / GPF3** (Generated Player Finder) — closed-source; the
  reference for what regen matching should feel like. We read GPF2's `.gpf2`
  sidecar (a day-one name snapshot) but reimplemented the matching from
  scratch.
- **Regen Cheat** (part of JLCollection, by Andrei Yakovenko) — renames
  regens back in place. This tool deliberately does *not* do that; it only
  annotates Notes.
- **GK Save Game Editor**, **CM Explorer** — general save-editing prior art.

## License

MIT — see [`LICENSE`](LICENSE). The point is that the workings are visible
and the tool is free to download; the specific license isn't precious.
