"""The CM 01/02 ``.sav`` container format: header + block table + block data.

Layout (little-endian throughout)::

    int32   marker        3 = uncompressed, 4 = compressed (RLE, see below)
    int32   unknown_hdr   purpose unknown; preserved verbatim on write
    int32   block_count
    block_count x 268-byte block-table entries:
        uint32     position   absolute file offset of this block's data
        uint32     size       block data length in bytes
        byte[260]  name       null-terminated ASCII, e.g. "player.dat"
    ... block data, addressable individually via the table ...

Compression, when present, is a byte-level RLE: a control byte <= 128 means
"copy the next (b) bytes literally"; a control byte > 128 means "repeat the
single following byte (b - 128) times". Real saves this tool targets are
always uncompressed (marker 3); :func:`rle_decode` is provided for
completeness but the write path refuses compressed inputs.

Verified against a real 517 MB save: growing one block and patching (a) its
own ``size`` and (b) the ``position`` of every block stored after it in the
file round-trips every other block byte-for-byte.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

HEADER_LEN = 12
BLOCK_TABLE_ENTRY_LEN = 268
BLOCK_NAME_LEN = BLOCK_TABLE_ENTRY_LEN - 8  # 260

MARKER_UNCOMPRESSED = 3
MARKER_COMPRESSED = 4


class CompressedSaveError(NotImplementedError):
    """Raised when an operation needs an uncompressed save but got a compressed one."""


@dataclass(frozen=True)
class Block:
    """One entry in the save's block table."""

    idx: int
    name: str
    position: int
    size: int
    table_off: int  # byte offset of this entry within the file

    @property
    def end(self) -> int:
        return self.position + self.size


class SavFile:
    """A parsed ``.sav`` file held wholly in memory.

    These saves are large (typically 300-700 MB) but comfortably fit in RAM,
    and every operation here needs random access across the whole file, so we
    read it once up front rather than seeking repeatedly.
    """

    def __init__(self, data: bytes):
        self.data = data
        marker, unknown_hdr, block_count = struct.unpack_from("<iii", data, 0)
        self.marker = marker
        self.unknown_hdr = unknown_hdr
        self.block_count = block_count

        self.blocks: list[Block] = []
        self._by_name: dict[str, Block] = {}
        for i in range(block_count):
            off = HEADER_LEN + i * BLOCK_TABLE_ENTRY_LEN
            position, size = struct.unpack_from("<II", data, off)
            raw_name = data[off + 8 : off + BLOCK_TABLE_ENTRY_LEN]
            name = raw_name.split(b"\x00", 1)[0].decode("latin-1")
            block = Block(idx=i, name=name, position=position, size=size, table_off=off)
            self.blocks.append(block)
            # First occurrence wins; real saves don't repeat block names.
            self._by_name.setdefault(name, block)

    # -- construction -----------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "SavFile":
        return cls(Path(path).read_bytes())

    # -- inspection -----------------------------------------------------

    @property
    def compressed(self) -> bool:
        return self.marker == MARKER_COMPRESSED

    def has_block(self, name: str) -> bool:
        return name in self._by_name

    def block(self, name: str) -> Block:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"block {name!r} not found in save") from None

    def read_block(self, name: str) -> bytes:
        """Raw bytes of a named block, decompressed if necessary."""
        block = self.block(name)
        raw = self.data[block.position : block.position + block.size]
        if self.compressed:
            return rle_decode(raw)
        return raw


def rle_decode(data: bytes) -> bytes:
    """Decode the simple CM 01/02 block RLE. See module docstring."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        control = data[i]
        i += 1
        if control <= 128:
            out += data[i : i + control]
            i += control
        else:
            count = control - 128
            out += bytes([data[i]]) * count
            i += 1
    return bytes(out)
