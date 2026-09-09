"""The name tables: ``first_names.dat`` / ``second_names.dat`` / ``common_names.dat``.

Each is a flat array of 60-byte ``TNames`` records::

    [0:51]   name text, Latin-1, null-terminated (50 usable chars)
    [51:55]  int32  ID      (an internal id -- NOT how records are addressed)
    [55:59]  int32  Nation
    [59]     byte   Count

Records are addressed by **array position**, and that position is what
``TStaff`` (and the ``.gpf2`` snapshot) store as ``FirstName`` / ``SecondName``
/ ``CommonName``. Do not match on the embedded ID field.
"""

from __future__ import annotations

from dataclasses import dataclass

from .savfile import SavFile

TNAMES_RECORD_LEN = 60
TNAMES_TEXT_LEN = 51


def _parse_name_table(block: bytes) -> list[str]:
    count = len(block) // TNAMES_RECORD_LEN
    out = []
    for i in range(count):
        base = i * TNAMES_RECORD_LEN
        text = block[base : base + TNAMES_TEXT_LEN].split(b"\x00", 1)[0].decode("latin-1")
        out.append(text)
    return out


@dataclass
class NameTables:
    first: list[str]
    second: list[str]
    common: list[str]

    @classmethod
    def from_sav(cls, sav: SavFile) -> "NameTables":
        return cls(
            first=_parse_name_table(sav.read_block("first_names.dat")),
            second=_parse_name_table(sav.read_block("second_names.dat")),
            common=_parse_name_table(sav.read_block("common_names.dat")),
        )

    def _lookup(self, table: list[str], idx: int) -> str:
        return table[idx] if 0 <= idx < len(table) else ""

    def resolve(self, first_idx: int, second_idx: int, common_idx: int) -> str:
        """Best display name for a (first, second, common) index triple.

        CM shows the common name on its own when a player has one (e.g.
        "Ronaldinho"), otherwise "First Second". ``common_idx`` 0 means none.
        """
        common = self._lookup(self.common, common_idx) if common_idx else ""
        if common:
            return common
        first = self._lookup(self.first, first_idx)
        second = self._lookup(self.second, second_idx)
        return f"{first} {second}".strip()

    def resolve_full(self, first_idx: int, second_idx: int, common_idx: int) -> str:
        """"First Second" plus "(Common)" when present -- for logs / CSV."""
        first = self._lookup(self.first, first_idx)
        second = self._lookup(self.second, second_idx)
        base = f"{first} {second}".strip()
        common = self._lookup(self.common, common_idx) if common_idx else ""
        return f"{base} ({common})" if common else base
