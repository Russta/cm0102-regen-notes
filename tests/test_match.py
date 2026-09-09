"""match / snapshot / annotate against a synthetic 4-slot world."""

from __future__ import annotations

from cm0102_regen_notes.annotate import apply_annotations, plan_annotations
from cm0102_regen_notes.match import find_regens
from cm0102_regen_notes.notes import NO_REMINDER_SENTINEL, parse_notes
from cm0102_regen_notes.savfile import SavFile
from cm0102_regen_notes.snapshot import RnwSnapshot, write_snapshot

from synth import make_world


def _write_world(tmp_path):
    sav, gpf2, meta = make_world()
    sp = tmp_path / "now.sav"
    gp = tmp_path / "now.sav.gpf2"
    sp.write_bytes(sav)
    gp.write_bytes(gpf2)
    return sp, gp, meta


def test_find_regens_gpf2(tmp_path):
    sp, gp, meta = _write_world(tmp_path)
    matches = find_regens(sp, gp)
    assert len(matches) == 1
    m = matches[0]
    assert m.slot == meta["regen_slot"]
    assert m.current_staff_id == meta["regen_staff_id"]
    assert m.original_name == meta["regen_original"]
    assert m.current_name == "Reginald Bloggs"
    assert m.current_pa == 175
    assert m.original_pa is None  # gpf2 has no ability


def test_potential_min_filters_on_current_pa(tmp_path):
    sp, gp, _ = _write_world(tmp_path)
    assert len(find_regens(sp, gp, potential_min=175)) == 1
    assert len(find_regens(sp, gp, potential_min=176)) == 0


def test_snapshot_roundtrip_and_rnw_baseline(tmp_path):
    sp, gp, meta = _write_world(tmp_path)
    out, data = write_snapshot(sp, tmp_path / "now.sav.rnw")
    assert data["player_count"] == 4

    snap = RnwSnapshot.load(out)
    assert snap.name_for_slot(0) == "Lionel Messi"
    assert snap.name_for_slot(2) == "Reginald Bloggs"  # snapshot of the *current* world
    assert snap.pa_for_slot(2) == 175

    # matching the same world against its own snapshot -> no regens
    assert find_regens(sp, out) == []


def test_original_potential_min_needs_rnw(tmp_path):
    sp, gp, _ = _write_world(tmp_path)
    try:
        find_regens(sp, gp, original_potential_min=100)
    except ValueError as e:
        assert "rnw" in str(e).lower()
    else:
        raise AssertionError("expected ValueError for original_potential_min with a .gpf2")


def test_annotate_writes_original_into_regen_notes(tmp_path):
    sp, gp, meta = _write_world(tmp_path)
    out = tmp_path / "annotated.sav"

    plan = plan_annotations(sp, gp)
    assert len(plan.to_write) == 1

    summary = apply_annotations(sp, out, plan)
    assert summary["notes_written"] == 1
    assert summary["appended"] == 1

    after = SavFile.load(out)
    notes = parse_notes(after.read_block("notes.dat"))
    assert len(notes) == 1
    assert notes[0].staff_id == meta["regen_staff_id"]
    assert notes[0].text == meta["regen_original"]
    assert notes[0].reminder_raw == NO_REMINDER_SENTINEL
    # untouched blocks preserved
    src = SavFile.load(sp)
    for b in src.blocks:
        if b.name != "notes.dat":
            assert src.read_block(b.name) == after.read_block(b.name)


def test_annotate_refuses_to_overwrite_input(tmp_path):
    sp, gp, _ = _write_world(tmp_path)
    plan = plan_annotations(sp, gp)
    try:
        apply_annotations(sp, sp, plan)
    except ValueError as e:
        assert "input" in str(e).lower()
    else:
        raise AssertionError("expected refusal to overwrite input save")
