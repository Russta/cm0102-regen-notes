"""Tie it together: find regens, then write each one's original identity into
that regen's in-game Notes -- always to a new save file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .match import RegenMatch, find_regens
from .notes import NOTE_TEXT_MAX, write_notes_bulk


@dataclass
class AnnotatePlan:
    to_write: list[RegenMatch] = field(default_factory=list)
    skipped_empty_origin: list[RegenMatch] = field(default_factory=list)
    skipped_too_long: list[RegenMatch] = field(default_factory=list)


def plan_annotations(
    save_path: str | Path,
    baseline_path: str | Path,
    *,
    potential_min: int | None = None,
    original_potential_min: int | None = None,
    annotate_empty_origin: bool = False,
) -> AnnotatePlan:
    found = find_regens(
        save_path,
        baseline_path,
        potential_min=potential_min,
        original_potential_min=original_potential_min,
        include_empty_origin=True,
    )
    plan = AnnotatePlan()
    for m in found:
        if m.original_was_empty and not annotate_empty_origin:
            plan.skipped_empty_origin.append(m)
        elif len(m.original_name.encode("latin-1", "replace")) > NOTE_TEXT_MAX:
            plan.skipped_too_long.append(m)
        else:
            plan.to_write.append(m)
    return plan


def apply_annotations(save_path: str | Path, out_path: str | Path, plan: AnnotatePlan) -> dict:
    if not plan.to_write:
        return {"notes_written": 0, "appended": 0, "overwrote": 0,
                "delta": 0, "out_path": str(out_path)}
    items = [(m.current_staff_id, m.original_name) for m in plan.to_write]
    return write_notes_bulk(save_path, out_path, items)
