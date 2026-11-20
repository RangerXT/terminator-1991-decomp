"""Source movie call parameters; names resolved from the input snapshot.
BX is EGA retraces per frame; VGA 14B5:0054 halves it with SHR BX,1.
No display refresh rate or wall-clock audio timing is inferred.
"""
import csv, hashlib, json, re
from pathlib import Path
import dosemu

def main():
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    rows = []
    recent = []
    for line in (root/'disasm/seg_0000.asm').read_text().splitlines():
        match = re.match(r'^([0-9A-F]{4}:[0-9A-F]{4})\s+[0-9a-f]+\s+(.+)$', line)
        if not match:
            continue
        addr, op = match.groups()
        if op in ['call sub_0000_B210', 'call cutscene_play_dispatch']:
            regs = {}
            for a, instr in recent[-5:]:
                if instr.startswith(('call ', 'lcall ', 'ret', 'jmp ')):
                    regs.clear()
                    continue
                mov = re.fullmatch(r'mov (si|ax|bx|cx), (0x[0-9a-f]+|[0-9]+)', instr)
                if mov:
                    regs[mov[1]] = int(mov[2], 0)
                if instr == 'xor cx, cx':
                    regs['cx'] = 0
            if 'si' in regs and 'bx' in regs:
                raw = m.ds_read(regs['si'], 64).split(bytes([0]))[0]
                name = raw.decode('cp437')
                ega = root/'data/ega'/(name.upper()+'.DCF')
                vga = root/'data/vga'/(name.upper()+'.DFF')
                rows.append(dict(call=addr, filename_offset='%04X'%regs['si'], snapshot_name=name, input_width=regs.get('ax'), input_delay=regs['bx'], alternate_atf_prefix_flag=regs.get('cx'), ega_retrace_pairs=regs['bx'] or 65536, vga_retrace_pairs=(regs['bx']>>1) or 65536, ega_frames=int.from_bytes(ega.read_bytes()[:2], 'little') if ega.exists() else None, vga_frames=int.from_bytes(vga.read_bytes()[:2], 'little') if vga.exists() else None))
        recent.append((addr, op))
        recent = recent[-5:]
    out = root/'out/tables'
    doc = dict(executable_sha256=hashlib.sha256(Path(dosemu.EXE).read_bytes()).hexdigest(), scope='source input literals; names resolved from snapshot, potentially mutable; no refresh-rate or audible timing claim', ega_loop='0000:B31C-B365', vga_halving='14B5:0054', calls=rows)
    (out/'cinematic_calls.json').write_text(json.dumps(doc, indent=2), encoding='utf-8')
    with (out/'cinematic_calls.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print('Recovered cinematic call sites:', len(rows))
if __name__ == '__main__':
    main()
