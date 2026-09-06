import struct
import sys

HEADER_LEN = 12
BLOCK_TABLE_ENTRY_LEN = 268
NOTE_RECORD_LEN = 276
TEXT_FIELD_LEN = 255                      # bytes 4..258 of the record
NOTE_TEXT_MAX = TEXT_FIELD_LEN - 1        # minus null terminator
NO_REMINDER_SENTINEL = bytes.fromhex('ea00b3070000 0000'.replace(' ', ''))  # Day=234, Year=1971, LeapYear=0

def read_block_table(fbytes):
    marker, unknown_hdr, block_count = struct.unpack_from('<iii', fbytes, 0)
    if marker == 4:
        raise NotImplementedError("File is compressed - not handled by this script.")
    table = []
    for i in range(block_count):
        off = HEADER_LEN + i * BLOCK_TABLE_ENTRY_LEN
        position, size = struct.unpack_from('<II', fbytes, off)
        name = fbytes[off+8: off+BLOCK_TABLE_ENTRY_LEN].split(b'\x00', 1)[0].decode('latin-1')
        table.append({'idx': i, 'name': name, 'position': position, 'size': size, 'table_off': off})
    return block_count, table

def get_current_game_date_bytes(fbytes, table):
    # Mirrors SaveReader.GetCurrentGameDate(): TCMDate lives at offset 3944
    # inside general.dat.
    general = next(b for b in table if b['name'] == 'general.dat')
    return fbytes[general['position']+3944: general['position']+3944+8]

def build_new_notes_block(notes_bytes, staff_id, text, created_date_bytes=None):
    if len(text.encode('latin-1')) > NOTE_TEXT_MAX:
        raise ValueError(f"Note text too long ({len(text)} chars); max {NOTE_TEXT_MAX}.")
    text_bytes = text.encode('latin-1') + b'\x00'

    count = struct.unpack_from('<i', notes_bytes, 0)[0]
    pos = 4
    for i in range(count):
        rec_id = struct.unpack_from('<i', notes_bytes, pos)[0]
        if rec_id == staff_id:
            # Overwrite existing record IN PLACE - only touch the text field
            # (bytes 4..258). Created-date and reminder-date (bytes 259..275)
            # are left completely untouched, preserving whatever the human
            # manager had already set (including a real reminder, if any).
            new_bytes = bytearray(notes_bytes)
            for j in range(pos+4, pos+4+TEXT_FIELD_LEN):
                new_bytes[j] = 0
            new_bytes[pos+4: pos+4+len(text_bytes)] = text_bytes
            return bytes(new_bytes), False  # False = size unchanged
        pos += NOTE_RECORD_LEN

    # Not found - append a new record just before the trailer.
    insert_at = 4 + count * NOTE_RECORD_LEN
    new_record = bytearray(NOTE_RECORD_LEN)
    struct.pack_into('<i', new_record, 0, staff_id)
    new_record[4:4+len(text_bytes)] = text_bytes
    if created_date_bytes:
        new_record[259:267] = created_date_bytes
    # New notes default to "No Reminder", matching normal manager preference.
    new_record[267:275] = NO_REMINDER_SENTINEL

    new_bytes = bytearray(notes_bytes)
    new_bytes[0:4] = struct.pack('<i', count + 1)
    new_bytes[insert_at:insert_at] = new_record  # bytearray slice-insert
    return bytes(new_bytes), True  # True = size changed

def write_note(in_path, out_path, staff_id, text):
    with open(in_path, 'rb') as f:
        fbytes = f.read()

    block_count, table = read_block_table(fbytes)
    notes_entry = next(b for b in table if b['name'] == 'notes.dat')
    p, s = notes_entry['position'], notes_entry['size']

    old_notes_bytes = fbytes[p:p+s]
    current_date = get_current_game_date_bytes(fbytes, table)
    new_notes_bytes, size_changed = build_new_notes_block(old_notes_bytes, staff_id, text, current_date)
    delta = len(new_notes_bytes) - len(old_notes_bytes)

    result = bytearray(fbytes)  # start as a full mutable copy

    if delta != 0:
        # Patch block table: notes.dat's own Size, and Position of every block
        # physically stored after it in the file.
        for b in table:
            off = b['table_off']
            if b['name'] == 'notes.dat':
                struct.pack_into('<I', result, off+4, len(new_notes_bytes))
            elif b['position'] > p:
                struct.pack_into('<I', result, off, b['position'] + delta)

    # Splice the data region: unchanged-before + new notes.dat bytes + unchanged-after
    result = result[:p] + bytearray(new_notes_bytes) + result[p+s:]

    # Re-apply block table patch (the slice above rebuilt the bytearray fresh from
    # `result` before splicing, so table patch already lives in the [:p] prefix -
    # nothing further needed since p is always > HEADER_LEN + block table region.)

    with open(out_path, 'wb') as f:
        f.write(result)

    print(f"staff_id={staff_id}: {'appended new' if size_changed else 'overwrote existing'} record. "
          f"notes.dat size {s} -> {len(new_notes_bytes)} (delta {delta}). Output: {out_path}")

if __name__ == '__main__':
    in_path, out_path, staff_id, text = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    write_note(in_path, out_path, staff_id, text)
