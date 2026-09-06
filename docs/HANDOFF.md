# CM 01/02 Regen Notes Tool — Project Handoff

## Vision (user's own words)
A Windows tool, distributed as a plain `.exe` (no Python/scripts visible to
end users), open source on GitHub (workings visible, downloadable by
anyone), that:

1. On day one of a new save, takes a "stamp in time" snapshot of every
   player's identity + stable attributes (like the community's `.gpf`/`.gpf2`
   tools do).
2. Later, generates a list of which current players are regens of which
   original players (optionally filtered to only show matches where the
   *original* player's PA was 140+).
3. Has a button to write the matched original identity into each regen's
   in-game **Notes** field, directly into the `.sav` file.
4. Optional: export the match list to CSV.

Distribution plan: Python source (readable/auditable) + a GitHub Actions
workflow that builds a Windows `.exe` automatically on release, so end
users just download and double-click — no Python or command line exposed
to them. License: MIT (purely so there's no ambiguity; the user isn't
fussed about license specifics, just wants the code visible and free to
download on GitHub).

## What's fully solved and verified (against the user's real 517MB save)

### `.sav` container format
```
int32   marker          (3 = uncompressed, 4 = compressed - RLE, see below)
int32   unknown header value
int32   blockCount
blockCount x 268-byte block headers:
    uint32  Position   (absolute file offset where this block's data starts)
    uint32  Size        (size in bytes)
    byte[260] Name      (null-terminated ASCII, e.g. "player.dat", "notes.dat")
```
Block data follows, addressable individually. Compression (when used) is a
simple RLE (byte <=128 = literal, byte >128 = repeat next byte (b-128)
times) - not relevant here since the user never plays with compressed saves,
but trivial if ever needed.

Confirmed against real data: inserting/growing one block (notes.dat) and
patching (a) that block's own Size field and (b) the Position field of
every OTHER block whose original Position was greater than the grown
block's position (shift by the size delta) correctly round-trips a
517MB save with zero corruption - verified by comparing every block's
bytes before/after (including 60MB+ blocks) and confirming byte-for-byte
identity aside from the intended shift.

### `notes.dat` block (the in-game "Notes" tab, per player)
```
offset 0:        int32 LE   entry count N
offset 4:        N x 276-byte records, densely packed:
                    [0:4]     int32 LE   TStaff.ID (same ID space as staff.dat)
                    [4:259]   note text, Latin-1, null-terminated
                              (255-byte buffer -> max 254 usable chars)
                    [259:267] "created" date - TCMDate (Day:int16 [0-indexed
                              day-of-year], Year:int16, LeapYear:int32) = 8 bytes
                    [267:275] reminder date - TCMDate, same layout, 8 bytes
                    [275]     unused (always 0 in every observed sample)
offset 4+N*276:  124 bytes, constant, always zero (trailer/reserve)
total size = 4 + N*276 + 124
```

**Critical: the reminder field is NOT simply "zero = no reminder".** The
game's real "No Reminder" sentinel is the specific bytes
`EA 00 B3 07 00 00 00 00` (Day=234, Year=1971, LeapYear=0) - confirmed
identical across all 12 of the user's real, hand-created notes. Writing
plain zeros there instead displays as a bogus "01.01.0000" reminder date
in-game. Any new note record MUST use this exact sentinel for the reminder
field unless deliberately setting a real reminder.

Key = `TStaff.ID`. Cross-verified independently: resolved "Michal
Jankowski" via `first_names.dat`/`second_names.dat` name-index lookup
against `staff.dat`, got ID 67524 - which exactly matched the ID already
embedded in his notes.dat record. Not a guess.

### `TStaff` struct (110 bytes, Pack=1) - the "person" identity record
Key fields (byte offsets confirmed from agevak/CM0102 (CM0102Core) source,
cross-checked against real data):
- 0x00 int ID
- 0x04 int FirstName   (POSITIONAL INDEX into first_names.dat, not a value/text)
- 0x08 int SecondName  (positional index into second_names.dat)
- 0x0C int CommonName  (positional index into common_names.dat)
- 0x61 int Player      (FK into player.dat / TPlayer, if this person plays)
- 0x69 int NonPlayer    (FK into TNonPlayer, if this person coaches)
(full struct has DOB, nation, wage, personality attributes etc. - see
Structures.cs reference below for everything)

`first_names.dat`/`second_names.dat`/`common_names.dat`: each entry is a
60-byte `TNames` record - 51 bytes of Latin-1 text (null-terminated) +
int32 ID + int32 Nation + byte Count. Match by **array position**, not the
embedded ID field (confirmed via agevak's `FindPlayer` logic).

### `TPlayer` struct (70 bytes, Pack=1) - ability stats, linked via TStaff.Player
CA, PA, all technical/mental/physical attributes, positional suitability.
Full offsets available in Structures.cs reference below - not yet needed
for anything built so far, will matter for the regen-matching step.

## Prior art / references (found via GitHub, cloned and read - NOT
committed/copied into any new repo we build, due to unclear licensing;
informed our understanding, credit in README, write our own clean
implementation)
- `agevak/CM0102` (CM0102Core) and `agevak/CM0102SaveGameTacticsEditor` on
  GitHub - C#, open on GitHub but no LICENSE file present (default
  all-rights-reserved). Source of the `TStaff`/`TPlayer`/block-table
  understanding above (independently cross-verified against real save
  data, not taken on faith).
- Community tools referenced during research: GPF/GPF2/GPF3 (Generated
  Player Finder - regen matching, closed-source), "Regen Cheat" (part of
  JLCollection by Andrei Yakovenko - renames regens back to original name
  directly in the save; the user explicitly does NOT want this
  rename-in-place behavior, only additive Notes annotation), GK Save Game
  Editor, CM Explorer.
- The `.gpf2` sidecar file format: NOT human-readable, no player names -
  it's a flat array of one 16-byte record per `player.dat` entry (3 int32
  values, likely CA/PA/similar + a sequential index). Does not hand us
  ready-made (original, regen) pairs; GPF3's actual matching logic
  produces those on-screen only, as far as established so far.

## What's built and tested (Python, in a throwaway Linux sandbox - needs
porting/re-verifying in the new environment, logic is sound)
- `list_blocks.py` - parses and lists every named block in a `.sav`.
- `extract_block.py` - pulls one named block's raw bytes out of a `.sav`.
- `write_note.py` - full write function: overwrites an existing note's
  text in place (leaves dates untouched) OR appends a brand-new note
  record (grows the block, shifts every downstream block's Position in
  the table, sets a proper "created" date read live from `general.dat`
  offset 3944, sets the reminder to the "No Reminder" sentinel). Verified
  end-to-end against the user's real 517MB save, both code paths, with
  full block-table and byte-content integrity checks afterward.
- User has confirmed in-game: a written note (staff ID 67524 / Michal
  Jankowski, text "Robert Lewandowski") displays correctly, including the
  reminder-field fix.

## Not yet built
1. Day-one snapshot tool (should be straightforward - same block-reading
   approach, store ID + name + stable attributes per player).
2. Regen-matching algorithm (the hard, iterative part - no source
   available for GPF3's actual heuristic; forum reports suggest bravery,
   positional suitability, and footedness are stable across regeneration,
   nationality is not always reliable). Good validation set already
   available: the user's real save's existing notes.dat already contains
   11 known (regen ID -> original name) pairs (Messi, Ronaldo, Benzema,
   etc.) that any matching algorithm we build should be able to
   independently rediscover.
3. CSV export (trivial once matching works).
4. Tkinter GUI wrapping the above.
5. GitHub Actions workflow to auto-build a Windows `.exe` on release
   (written conceptually, not yet created/tested against a real repo).
6. Actual GitHub repo creation + push (blocked in the previous sandbox -
   no git push capability there; this is the main reason for moving to
   Claude Code).

## Files included alongside this handoff doc
- `list_blocks.py`, `extract_block.py`, `write_note.py` (working code,
  described above)

## Note on test data
The original `.sav` files and the `.gpf2` file used for all verification
above are NOT included here (large, and were user uploads specific to the
previous chat) - re-upload them into the new Code session's project
folder if further empirical testing against the real save is needed.
