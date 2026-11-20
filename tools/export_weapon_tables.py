"""Export executable-traced weapon parameters as reference data.
Eight entries at DS:78DC/78E4 and DS:8097; each row checked through original 5754.
Unidentified fields retain raw names; live ammo/count is not a fixed table parameter.
"""
import csv
import hashlib
import json
import os
import struct
from pathlib import Path
import dosemu

def main():
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rows = []
    for index in range(8):
        m.ds_write(0, saved)
        item = saved[0x78DC+index]
        kind = saved[0x78E4+index]
        template = saved[0x8097+index*3:0x809A+index*3]
        m.ds_write(0x793F, bytes([item]))
        m.ds_write(0x8200, bytes([0xA5])*6)
        m.call(0, 0x5754, es=m.DATA_SEG, di=0x8200)
        record = m.ds_read(0x8200, 6)
        expected = bytes([kind, template[2], 0xA5, 0xA5, template[0], template[1]])
        if record != expected:
            raise RuntimeError('Original initializer differs at row %d'%index)
        damage = struct.unpack('b', record[5:6])[0]
        sound = struct.unpack('b', saved[0x80DA+kind:0x80DB+kind])[0]
        name_ptr = struct.unpack_from('<H', saved, 0x78EC+index*2)[0]
        name = saved[name_ptr:].split(bytes([0]))[0].decode('ascii')
        ammo_category = saved[0x80AF+kind]
        ammo_item = saved[0x80E2+ammo_category]
        # Validate the reload table meaning through the actual 1D59 entry.
        slot = 0x570+kind*6
        m.ds_write(slot, record)
        m.ds_write(0x0200, bytes(2))
        m.ds_write(0x8096, bytes([1]))
        m.ds_write(0x1138+ammo_category, bytes([2]))
        m.ds_write(0x5B0, struct.pack('<H4B', 0x8700, ammo_item, 0, 2, 2))
        m.ds_write(0x5B6, bytes(6))
        m.ds_write(0x03A2, struct.pack('<H', 0x5B6))
        m.call(0x11BC, 0x1D59, cx=kind+1)
        if m.ds_read(slot+3, 1)[0] != record[4] or m.ds_read(0x1138+ammo_category, 1)[0] != 1 or m.ds_read(0x5B5, 1)[0] != 1 or m.ds_read(0x8096, 1)[0] != 21:
            raise RuntimeError('Original reload table check differs at row %d'%index)
        rows.append(dict(table_index=index, item_id=item, weapon_kind=kind, name=name, name_pointer='%04X'%name_ptr, damage_signed_byte=damage,
                         magazine_capacity=record[4], reload_ammo_category=ammo_category, reload_item_id=ammo_item,
                         ammo_counter_address='%04X'%(0x1138+ammo_category), scope_on_select=bool(record[1]&1),
                         selection_flag_0366=record[1]&2,
                         record_byte_1=record[1], record_byte_4=record[4], sound_signed_byte=sound,
                         charge_on_fire=kind == 3, continuous_sound_path=sound == 4,
                         item_id_address='78DC+%d'%index, kind_address='78E4+%d'%index,
                         template_address='%04X'%(0x8097+index*3)))
    opponent = []
    for index in range(4):
        m.ds_write(0, saved)
        m.ds_write(0x1208, struct.pack('<HH', 0x100, 0x8000))
        m.ds_write(0x0359, bytes([0]))
        pairs = struct.unpack_from('<4H', saved, 0xDE3E)
        ids = [item for pair in pairs for item in [pair&255, pair>>8]]
        for j, item in enumerate(ids):
            m.wb(0x8000, 0x100+j*6, struct.pack('<H4B', 0, item, 0, 2, 2))
        m.wb(0x8000, 0x100+len(ids)*6, bytes(6))
        m.ds_write(0x9948, struct.pack('<HH', 0x97B8, 0x9948))
        m.ds_write(0x97B8, struct.pack('<H', index))
        m.call(0, 0xC068, ax=0)
        capacity = saved[0xDE38+index]
        ammo = pairs[index]&255
        item = pairs[index]>>8
        if m.rw(m.DATA_SEG, 0xDE46) != index or m.ds_read(0x0355, 1)[0] != capacity or m.ds_read(0x035A, 1)[0] != 4:
            raise RuntimeError('Original opponent choice check differs at row %d'%index)
        opponent.append(dict(choice_index=index, weapon_item_id=item, weapon_name=next(row['name'] for row in rows if row['item_id'] == item),
                             paired_ammo_item_id=ammo, choice_capacity_byte=capacity,
                             capacity_address='%04X'%(0xDE38+index), pair_address='%04X'%(0xDE3E+index*2)))
    folder = Path(dosemu.ROOT)/'out'/'tables'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'weapon_parameters.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (folder/'opponent_choices.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(opponent[0]))
        writer.writeheader()
        writer.writerows(opponent)
    exe = Path(dosemu.ROOT)/'exe'/'TERM_unpacked.exe' 
    (folder/'weapon_parameters.json').write_text(json.dumps(dict(
        executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        evidence=['0000:5754 initializes record bytes 0,1,4,5; 2 and 3 are retained',
                  '0000:A0D4 sign-extends record byte 5 as damage',
                  '0000:6D49 decrements record byte 3 as live ammo',
                  '11BC:1D59 reloads record byte 3 from byte 4; decrements DS:1138[DS:80AF[kind]]',
                  '11BC:1D7E removes DS:80E2[ammo_category] from inventory',
                  '11BC:1E6B copies record byte 1 bits 0/1 into scope mode and DS:0366',
                  '0000:C0A7 uses paired inventory IDs at DE3E; C068 selects the DE38 capacity byte',
                  '0000:5622..5659 indexes DS:78EC names into the item record',
                  '0000:6DBA sign-extends DS:80DA[kind] for the sound selector',
                  '0000:6DB2 kind 3 enters charging; 0000:6DC1 sound 4 enters continuous path'],
        limitations=['Display names come from DS:78EC pointers used by 5622, not inferred labels.',
                     'damage_signed_byte is the A07B hitscan input; projectile blast strength is separate.',
                     'Guidance depends on selected source comparison at 6AFC, not on this table alone.',
                     'For kind 3 the sound selector is used by impact resolution, not initial charging.',
                     'Snapshot supplies initialized tables; every entry is checked by original 5754 and 1D59.'],
        weapons=rows, opponent_choices=opponent), indent=2)+chr(10), encoding='utf-8')
    print('8 initializer, 8 reload and 4 opponent-choice checks passed; weapon parameters exported to', folder)
    for row in rows:
        print('%s: item=%d kind=%d damage=%d sound=%d'%(row['name'], row['item_id'], row['weapon_kind'], row['damage_signed_byte'], row['sound_signed_byte']))

if __name__ == '__main__':
    main()
