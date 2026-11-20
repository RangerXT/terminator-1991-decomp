"""Export original sound request IDs/groups and verify their real file loads.
Runs 8A9E/8ABE/8ADE/8AFE on the original executable, with sound idle and a prepared
sample arena. No stat/file-load bodies are replaced. Installed assets are read only.
"""
import csv, hashlib, json, os, struct
from pathlib import Path
import dosemu, termsnd
ROOT = Path(dosemu.ROOT)


def main():
    groups = []
    rows = []
    for mode, entry, table, count, ids in [(1, 0x8A9E, 0xA6EC, 13, 0xA706), (3, 0x8ABE, 0xA713, 12, 0xA72B), (4, 0x8ADE, 0xA737, 3, 0xA73D), (6, 0x8AFE, 0xA740, 1, 0xA742)]:
        m = dosemu.Machine()
        m.load(str(ROOT/'out/emu/states/ingame.pkl'))
        m.ds_write(0xA743, struct.pack('<H', 0x8000))
        m.ds_write(0xA75F, struct.pack('<H', 0xD74))
        m.ds_write(0xA6E9, bytes([0]))
        m.ds_write(0xAA83, bytes([0]))
        source = []
        for slot in range(count):
            off = m.rw(m.DATA_SEG, table+slot*2)
            name = m.ds_read(off, 64).split(bytes([0]))[0].decode('ascii')
            request = m.ds_read(ids+slot, 1)[0]
            source.append((slot, name, request))
        m.call(0, entry, es=m.DATA_SEG, max_instr=10_000_000)
        if m.ds_read(0xA6E9, 1)[0] != mode:
            raise ValueError('Original group did not complete')
        entries = []
        for slot, name, request in source:
            path = Path(m._path(name))
            data = path.read_bytes()
            seg = m.rw(m.DATA_SEG, 0xA743+slot*2)
            if m.ds_read(0xA763+slot, 1)[0] != request or not seg or m.rb(seg, 0, len(data)) != data:
                raise ValueError('Original sound slot mismatch '+name)
            tag, code, rate, samples = termsnd.read_rs(path)
            record = dict(group=mode, slot=slot, request_id=request, file=name, file_bytes=len(data), declared_samples=struct.unpack_from('<H', data, 7)[0], exported_samples=len(samples), rate_code=code, rate_hz=rate, tag=tag, raw_header_byte6=data[6], wav='out/snd/'+path.stem.upper()+'.wav', sha256=hashlib.sha256(data).hexdigest())
            rows.append(record)
            entries.append(record)
        groups.append(dict(mode=mode, source_entry='0000:%04X'%entry, slots=entries))
        print('Original sound group %d: %d slots verified'%(mode, count))
    out = ROOT/'out/tables'
    out.mkdir(exist_ok=True)
    (out/'sound_groups.json').write_text(json.dumps(dict(exe_sha256=hashlib.sha256((ROOT/'exe/TERM_unpacked.exe').read_bytes()).hexdigest(), groups=groups), indent=2)+'\n')
    with (out/'sound_groups.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print('Exported', len(rows), 'verified sound-group slots')

if __name__ == '__main__':
    main()
