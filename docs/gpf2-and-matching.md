# The `.gpf2` format and how regen matching works

Findings established after `HANDOFF.md`, verified against the reference
517 MB save (`Dec 2025 - Nick v2.31 - Cardiff`).

## `.gpf2` sidecar

`HANDOFF.md` guessed the `.gpf2` was `(CA, PA, something, index)`. It isn't.

GPF2, pointed at a fresh save, writes `<savename>.sav.gpf2` next to it. It is
a flat array of **16-byte records, one per `player.dat` slot, in slot order**:

| offset | type  | meaning |
| ------ | ----- | ------- |
| 0      | int32 | `first_names.dat` index  |
| 4      | int32 | `second_names.dat` index |
| 8      | int32 | `common_names.dat` index (0 = none) |
| 12     | int32 | slot number (0, 1, 2, … — the record's own position) |

That is the whole file: a **day-one name snapshot per player slot**. No ids,
no abilities, no dates.

Confirmed: `1,919,168` bytes / 16 = `119,948` records = `player.dat` block
size / 70. Resolving the three indices against the save's own name tables
reproduces the correct day-one name for every slot, including all 12
hand-made regen notes in the reference save (e.g. slot 24819's day-one name
is "Robert Lewandowski"; the manager's note on the current occupant of that
slot, Michal Jankowski, reads "Robert Lewandowski").

The name indices are positions into the **save's** name tables. Those tables
are effectively static within a save (the reference save's differ from the
pre-game database's by only 16 trailing entries), so day-one indices still
resolve correctly against the current save.

## Matching

`player.dat` slots are fixed for the life of a save. When a player retires,
a newgen is eventually written into a freed slot. Therefore:

> a slot whose **current** occupant's name differs from its **day-one** name
> is holding a regen, and the day-one name identifies who they replaced.

The slot number is the entire linkage — no attribute fingerprinting. To find
the current occupant of slot *N*: scan `staff.dat` for the record whose
`Player` FK (offset 97) equals *N*, then resolve that staff record's name
indices.

Regens can themselves regenerate. We always compare against the **day-one**
name, so the reported original is the day-one identity regardless of how many
regen generations have passed in that slot. Caveat: CM reuses *freed* slots
but not necessarily the *same* freed slot, so a newgen can land in some other
retired player's slot and be reported as a regen of that person. This is
inherent to the slot method (GPF2/GPF3 included); it held up 12/12 on the
reference save.

## The "potential >=" filter

The `.gpf2` has no ability data, so GPF2's "Build changes list, potential >="
button must filter on the **current** (regen) player's PA, read from
`player.dat` in the save it is pointed at — not the vanished day-one
original's. `match --potential-min` does the same. `match
--original-potential-min` filters on the day-one PA and requires a `.rnw`
baseline (our snapshot), which records CA/PA/nation per slot.

`TPlayer` (70 bytes): `CA` = int16 LE at offset 5, `PA` = int16 LE at offset
7. A negative `PA` is a masked/random potential — take the absolute value for
filtering and display.
