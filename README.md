# CM 01/02 Regen Notes Tool

A small, open-source Windows tool for **Championship Manager 01/02** that:

1. On day one of a new save, takes a snapshot of every player's identity and
   stable attributes (like the community's `.gpf` / `.gpf2` tools).
2. Later, works out which current players are **regens** of which original
   players — optionally only showing matches where the *original* player's
   PA was 140+.
3. Writes the matched original identity into each regen's in-game **Notes**
   field, directly in the `.sav` — **additively**. It never renames a player
   in place.
4. Optionally exports the match list to CSV.

It's distributed as a plain `.exe` (no Python or command line needed to use
it), and the full source is here so anyone can read exactly what it does to
their save.

## Status

What works today:

| Piece | State |
| --- | --- |
| `.sav` container parsing (block table) | ✅ verified against a real 517 MB save |
| `notes.dat` read + write (overwrite in place / append new / bulk) | ✅ verified in-game |
| Day-one identity snapshot (`.rnw` sidecar) | ✅ names + CA/PA/nation per slot |
| Read GPF2's `.gpf2` day-one snapshot | ✅ decoded (names + slot) |
| Regen matching (current name vs day-one name, by `player.dat` slot) | ✅ rediscovers all 12 known regens in the reference save |
| `potential >=` filter + CSV export | ✅ |
| Write matched originals into every regen's Notes | ✅ `annotate`, byte-integrity-checked |
| GUI (Tkinter) | ✅ snapshot / find regens / filter / CSV / write notes |
| Auto-built Windows `.exe` on release | ✅ workflow in place, untested against a real release |

### How the matching works

`player.dat` slots are fixed for the life of a save; when a player retires, a
newgen is eventually written into a freed slot. So a slot whose **current**
occupant's name differs from its **day-one** name is holding a regen, and the
day-one name is who they replaced. The slot number is the link — no
attribute-fingerprint guessing. The day-one names come from either GPF2's
`.gpf2` or our own `.rnw` snapshot.

`--potential-min` filters on the *current* player's PA (this is what GPF2's
"Build changes list, potential >=" button does). `--original-potential-min`
filters on the day-one player's PA and needs a `.rnw` baseline (the `.gpf2`
stores no abilities).

See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the full reverse-engineering
notes — save format, `notes.dat` layout, the `TStaff` / `TPlayer` structs,
and the "No Reminder" sentinel that a naïve writer gets wrong.

## Safety

Every write goes to a **new output file**; the tool never modifies the save
you point it at. Still: keep your own backups. This edits an undocumented
binary format.

## Usage

Double-click the `.exe` (or run `python -m cm0102_regen_notes.gui` from
source) for the GUI: pick your save and a day-one baseline (`.gpf2` or
`.rnw`), set the minimum PA, **Find regens**, then **Export CSV** or **Write
Notes to new save**. There's a **Take snapshot now** button for day one.

### Command line (from source)

```bash
pip install -e .

# on day one of a new save (immediately after the first save), take a baseline:
cm0102-regen-notes snapshot "Career.sav"              # -> Career.sav.rnw
#   ...or just use GPF2's Career.sav.gpf2 if you already run GPF2

# later, after regens have appeared:
cm0102-regen-notes match    "Career.sav" "Career.sav.gpf2" --potential-min 150 --csv regens.csv
cm0102-regen-notes annotate "Career.sav" "Career.sav.gpf2" "Career_annotated.sav" --potential-min 150

# low-level helpers:
cm0102-regen-notes list-blocks   "Career.sav"
cm0102-regen-notes dump-notes    "Career.sav"
cm0102-regen-notes extract-block "Career.sav" notes.dat notes.bin
cm0102-regen-notes write-note    "Career.sav" "out.sav" 67524 "Robert Lewandowski"
```

`match` and `annotate` accept either a `.gpf2` (from GPF2) or a `.rnw` (from
`snapshot`) as the day-one baseline. `annotate` and `write-note` always write
to a new file and refuse to overwrite the input. `annotate --dry-run` shows
what it would write without touching anything.

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
