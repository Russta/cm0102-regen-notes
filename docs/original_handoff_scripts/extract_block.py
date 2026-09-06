import struct
import sys

def find_block(path, target_name):
    with open(path, 'rb') as f:
        header = f.read(12)
        marker, unknown_hdr, block_count = struct.unpack_from('<iii', header, 0)
        was_compressed = (marker == 4)

        target = None
        for _ in range(block_count):
            bheader = f.read(268)
            position, size = struct.unpack_from('<II', bheader, 0)
            name = bheader[8:].split(b'\x00', 1)[0].decode('latin-1')
            if name == target_name:
                target = (position, size)

        if target is None:
            raise ValueError(f"Block {target_name!r} not found")

        position, size = target
        f.seek(position)
        data = f.read(size)
        if was_compressed:
            raise NotImplementedError("Compressed block - need RLE decode")
        return data

if __name__ == '__main__':
    path, name, outpath = sys.argv[1], sys.argv[2], sys.argv[3]
    data = find_block(path, name)
    with open(outpath, 'wb') as f:
        f.write(data)
    print(f"Wrote {len(data)} bytes from block {name!r} to {outpath}")
