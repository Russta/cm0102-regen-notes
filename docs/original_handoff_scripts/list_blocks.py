import struct
import sys

def list_blocks(path):
    with open(path, 'rb') as f:
        header = f.read(12)
        marker, unknown_hdr, block_count = struct.unpack_from('<iii', header, 0)
        was_compressed = (marker == 4)
        print(f"marker={marker} (compressed={was_compressed}), unknown_hdr=0x{unknown_hdr:X}, blocks={block_count}\n")

        blocks = []
        for _ in range(block_count):
            bheader = f.read(268)
            position, size = struct.unpack_from('<II', bheader, 0)
            name = bheader[8:].split(b'\x00', 1)[0].decode('latin-1')
            blocks.append((name, position, size))

    for name, position, size in sorted(blocks):
        print(f"{name:<28} pos=0x{position:010X}  size={size:>12,}")

    return was_compressed, blocks

if __name__ == '__main__':
    list_blocks(sys.argv[1])
