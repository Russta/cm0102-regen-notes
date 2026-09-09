"""Find regens: player slots whose occupant's name today differs from the
day-one name for that slot.

``player.dat`` slots are fixed for the life of a save; when a player leaves,
a newgen is eventually written into a freed slot. So a slot whose current
name != its day-one name is holding a regen, and the day-one name is who they
replaced (possibly several regen-generations back -- we always report the
original day-one identity, which is what fits an in-game note).

The day-one baseline can come from either GPF2's ``.gpf2`` (names only) or our
own ``.rnw`` (names + abilities).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from .gpf2 import Gpf2Snapshot
from .names import NameTables
from .records import PlayerRecord, iter_staff
from .savfile import SavFile
from .snapshot import RnwSnapshot


class Baseline(Protocol):
    def name_for_slot(self, slot: int) -> str | None: ...
    def pa_for_slot(self, slot: int) -> int | None: ...


class GpfBaseline:
    """Adapts a ``.gpf2`` + the current save's name tables to the Baseline API."""

    def __init__(self, gpf2: Gpf2Snapshot, tables: NameTables):
        self._gpf2 = gpf2
        self._tables = tables

    def name_for_slot(self, slot: int) -> str | None:
        if 0 <= slot < len(self._gpf2.entries):
            f, s, c = self._gpf2.entries[slot]
            return self._tables.resolve(f, s, c)
        return None

    def pa_for_slot(self, slot: int) -> int | None:
        return None  # GPF2 doesn't record ability


@dataclass(frozen=True)
class RegenMatch:
    slot: int
    original_name: str
    current_name: str
    current_staff_id: int
    current_ca: int
    current_pa: int
    original_pa: int | None  # only when the baseline is a .rnw

    @property
    def original_was_empty(self) -> bool:
        return self.original_name == ""


def load_baseline(path: str | Path, tables: NameTables) -> Baseline:
    """Load a ``.gpf2`` or ``.rnw`` baseline, dispatching on extension."""
    p = Path(path)
    if p.suffix.lower() == ".gpf2":
        return GpfBaseline(Gpf2Snapshot.load(p), tables)
    if p.suffix.lower() == ".rnw":
        return RnwSnapshot.load(p)
    raise ValueError(f"unrecognised baseline {p.name!r}; expected .gpf2 or .rnw")


def find_regens(
    save_path: str | Path,
    baseline_path: str | Path,
    *,
    potential_min: int | None = None,
    original_potential_min: int | None = None,
    include_empty_origin: bool = True,
) -> list[RegenMatch]:
    """All regen slots in ``save_path``, judged against ``baseline_path``.

    ``potential_min`` filters on the *current* (regen) player's PA -- this is
    what GPF2's "potential >=" button does. ``original_potential_min`` filters
    on the day-one player's PA and needs a ``.rnw`` baseline.
    """
    sav = SavFile.load(save_path)
    tables = NameTables.from_sav(sav)
    baseline = load_baseline(baseline_path, tables)

    staff_buf = sav.read_block("staff.dat")
    player_buf = sav.read_block("player.dat")
    player_count = len(player_buf) // 70

    slot_to_staff: dict[int, object] = {}
    for staff in iter_staff(staff_buf):
        if staff.player_fk >= 0:
            slot_to_staff.setdefault(staff.player_fk, staff)

    matches: list[RegenMatch] = []
    for slot in range(player_count):
        staff = slot_to_staff.get(slot)
        if staff is None:
            continue  # slot currently vacant -- nobody to annotate

        current_name = tables.resolve(staff.first_name, staff.second_name, staff.common_name)
        original_name = baseline.name_for_slot(slot)
        if original_name is None:
            continue
        if current_name == original_name:
            continue
        if original_name == "" and not include_empty_origin:
            continue

        player = PlayerRecord.unpack(player_buf, slot)
        original_pa = baseline.pa_for_slot(slot)

        if potential_min is not None and player.effective_pa < potential_min:
            continue
        if original_potential_min is not None:
            if original_pa is None:
                raise ValueError(
                    "original_potential_min needs a .rnw baseline; the .gpf2 has no ability data"
                )
            if original_pa < original_potential_min:
                continue

        matches.append(RegenMatch(
            slot=slot,
            original_name=original_name,
            current_name=current_name,
            current_staff_id=staff.staff_id,
            current_ca=player.ca,
            current_pa=player.effective_pa,
            original_pa=original_pa,
        ))

    return matches


def write_csv(matches: list[RegenMatch], out_path: str | Path) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "slot", "original_name", "current_name", "current_staff_id",
            "current_ca", "current_pa", "original_pa",
        ])
        for m in matches:
            w.writerow([
                m.slot, m.original_name, m.current_name, m.current_staff_id,
                m.current_ca, m.current_pa,
                "" if m.original_pa is None else m.original_pa,
            ])
