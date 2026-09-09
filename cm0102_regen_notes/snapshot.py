"""Our own day-one snapshot: the ``.rnw`` sidecar.

Written next to a save as ``<savename>.sav.rnw``. Unlike GPF2's ``.gpf2`` it
also records current ability, potential ability and nation per slot, so a
future "the *original* player's PA was >= N" filter is possible -- GPF2's
sidecar can't do that because it stores names only.

Format: UTF-8 JSON, deliberately plain so it can be diffed and eyeballed::

    {
      "format": "cm0102-regen-notes/rnw",
      "version": 1,
      "source_save": "Dec 2025 - Nick v2.31 - Cardiff.sav",
      "created_utc": "2026-09-09T12:00:00Z",
      "game_date": {"day": 12, "year": 2025},
      "player_count": 119948,
      "fields": ["slot", "staff_id", "first", "second", "common", "name", "ca", "pa", "nation"],
      "rows": [[0, 1, 21744, 22417, 1792, "Lucas Costa", 152, 168, 7], ...]
    }
"""

from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from pathlib import Path

from .names import NameTables
from .notes import TCMDate, get_current_game_date_bytes
from .records import STAFF_RECORD_LEN, S_PLAYER_FK, PlayerRecord, iter_staff
from .savfile import SavFile

RNW_FORMAT = "cm0102-regen-notes/rnw"
RNW_VERSION = 1
RNW_FIELDS = ["slot", "staff_id", "first", "second", "common", "name", "ca", "pa", "nation"]


def sidecar_path(save_path: str | Path) -> Path:
    p = Path(save_path)
    return p.with_name(p.name + ".rnw")


def _slot_to_staff(staff_buf: bytes) -> dict[int, "object"]:
    mapping: dict[int, object] = {}
    for staff in iter_staff(staff_buf):
        if staff.player_fk >= 0:
            mapping.setdefault(staff.player_fk, staff)
    return mapping


def build_snapshot(save_path: str | Path) -> dict:
    sav = SavFile.load(save_path)
    tables = NameTables.from_sav(sav)
    staff_buf = sav.read_block("staff.dat")
    player_buf = sav.read_block("player.dat")

    slot_to_staff = _slot_to_staff(staff_buf)
    player_count = len(player_buf) // 70

    game_date = TCMDate.unpack(get_current_game_date_bytes(sav))

    rows = []
    for slot in range(player_count):
        staff = slot_to_staff.get(slot)
        player = PlayerRecord.unpack(player_buf, slot)
        if staff is None:
            rows.append([slot, -1, 0, 0, 0, "", player.ca, player.effective_pa, -1])
            continue
        name = tables.resolve(staff.first_name, staff.second_name, staff.common_name)
        rows.append([
            slot, staff.staff_id,
            staff.first_name, staff.second_name, staff.common_name,
            name, player.ca, player.effective_pa, staff.nation,
        ])

    return {
        "format": RNW_FORMAT,
        "version": RNW_VERSION,
        "source_save": Path(save_path).name,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "game_date": {"day": game_date.day, "year": game_date.year},
        "player_count": player_count,
        "fields": RNW_FIELDS,
        "rows": rows,
    }


def write_snapshot(save_path: str | Path, out_path: str | Path | None = None) -> tuple[Path, dict]:
    data = build_snapshot(save_path)
    out = Path(out_path) if out_path else sidecar_path(save_path)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out, data


class RnwSnapshot:
    """A loaded ``.rnw`` file, indexed by slot."""

    def __init__(self, data: dict):
        if data.get("format") != RNW_FORMAT:
            raise ValueError(f"not an {RNW_FORMAT} file (got {data.get('format')!r})")
        self.data = data
        self.player_count = data["player_count"]
        idx = {name: i for i, name in enumerate(data["fields"])}
        self._name_i = idx["name"]
        self._pa_i = idx["pa"]
        self._by_slot = {row[idx["slot"]]: row for row in data["rows"]}

    @classmethod
    def load(cls, path: str | Path) -> "RnwSnapshot":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def name_for_slot(self, slot: int) -> str | None:
        row = self._by_slot.get(slot)
        return row[self._name_i] if row else None

    def pa_for_slot(self, slot: int) -> int | None:
        row = self._by_slot.get(slot)
        return row[self._pa_i] if row else None
