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

Early. What works today:

| Piece | State |
| --- | --- |
| `.sav` container parsing (block table) | ✅ done, verified against a real 517 MB save |
| `notes.dat` read + write (overwrite in place / append new) | ✅ done, verified in-game |
| Day-one identity snapshot | ⬜ not started |
| Regen-matching algorithm | ⬜ not started (the hard part) |
| CSV export | ⬜ not started |
| GUI | ⬜ not started |
| Auto-built Windows `.exe` on release | ✅ workflow in place, untested against a real release |

See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the full reverse-engineering
notes — save format, `notes.dat` layout, the `TStaff` / `TPlayer` structs,
and the "No Reminder" sentinel that a naïve writer gets wrong.

## Safety

Every write goes to a **new output file**; the tool never modifies the save
you point it at. Still: keep your own backups. This edits an undocumented
binary format.

## Usage (from source)

```bash
pip install -e .

cm0102-regen-notes list-blocks   "path/to/save.sav"
cm0102-regen-notes dump-notes    "path/to/save.sav"
cm0102-regen-notes extract-block "path/to/save.sav" notes.dat notes.bin
cm0102-regen-notes write-note    "path/to/save.sav" "out.sav" 67524 "Robert Lewandowski"
```

`write-note` refuses to overwrite the input file.

## Development

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_notes.py` is self-contained (it fabricates a format-accurate
mini-save). `tests/verify_real_save.py` is a separate, heavier check you point
at a real `.sav` — it writes a note to a temp copy and confirms every other
block is byte-for-byte identical afterwards.

## Prior art and credit

This project is a clean-room reimplementation. No third-party code is copied
in. The save-format understanding was informed by, and cross-checked against,
these community projects:

- **[agevak/CM0102](https://github.com/agevak/CM0102)** and
  **agevak/CM0102SaveGameTacticsEditor** — C#; source of the initial
  `TStaff` / `TPlayer` / block-table layout (independently re-verified here
  against real save data). No `LICENSE` file present, so nothing from them is
  vendored.
- **GPF / GPF2 / GPF3** (Generated Player Finder) — closed-source; the
  reference for what regen matching should feel like.
- **Regen Cheat** (part of JLCollection, by Andrei Yakovenko) — renames
  regens back in place. This tool deliberately does *not* do that; it only
  annotates Notes.
- **GK Save Game Editor**, **CM Explorer** — general save-editing prior art.

## License

MIT — see [`LICENSE`](LICENSE). The point is that the workings are visible
and the tool is free to download; the specific license isn't precious.
