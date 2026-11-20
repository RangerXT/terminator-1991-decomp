"""Export a referenced subset of 5032 UI panels, validating each against DOS and C.
Requires generated disasm listings and the in-game snapshot. Dynamic/transformed
SI arguments are excluded. Validation uses a prepared 40x24-cell nonmodal window;
its dimensions are not inferred to be the original caller's layout.
"""
import csv, ctypes, hashlib, json, re, sys
from pathlib import Path
import difftest, dosemu
sys.path.insert(0, str(Path(dosemu.ROOT)/'tests'))
from test_drawlist import make_game, compare


def references():
    result = {}
    for path in (Path(dosemu.ROOT)/'disasm').glob('seg_*.asm'):
        pending = None
        for line in path.read_text().splitlines():
            if line.startswith('; ========'):
                pending = None
            match = re.match(r'^([0-9A-F]{4}:[0-9A-F]{4})\s+[0-9a-f]+\s+(.+)$', line)
            if not match:
                continue
            address, op = match.groups()
            mov = re.fullmatch(r'mov si, (0x[0-9a-f]+|[0-9]+)', op)
            if mov:
                pending = (int(mov.group(1), 0), address)
            elif op.startswith(('call ', 'lcall ')):
                if pending and op.split()[-1] in ['textbox_draw', 'sub_0000_EF6F']:
                    result.setdefault(pending[0], []).append(dict(call=address, source_load=pending[1]))
                pending = None
            elif re.match(r'(mov|pop|add|sub|inc|dec|xor|xchg|lea|les|lds) si\b', op) or op.startswith('lods'):
                pending = None
    return result


def parse(data, offset):
    start = offset
    if data[offset] > 15:
        raise ValueError('colour is not an EGA index')
    colour = data[offset]
    offset += 1
    lines = []
    for _ in range(32):
        x, y = data[offset:offset+2]
        offset += 2
        end = data.find(bytes([0]), offset, min(len(data), offset+1024))
        if end < 0:
            raise ValueError('no bounded text terminator')
        raw = data[offset:end]
        if any(c < 32 or c == 255 for c in raw):
            raise ValueError('non-text bytes')
        lines.append(dict(relative_x=x, relative_y=y, text=raw.decode('cp437')))
        offset = end+1
        if data[offset] == 255:
            if not any(line['text'].strip() for line in lines):
                raise ValueError('empty synthetic/dynamic argument')
            return dict(offset='%04X'%start, colour=colour, byte_length=offset+1-start, lines=lines)
    raise ValueError('too many lines')


def main():
    ctx = difftest.Ctx()
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    saved = m.ds_read(0, 65536)
    seg = m.rw(m.DATA_SEG, 0xEA36)
    data = m.rb(seg, 0, 65536)
    panels = []
    excluded = []
    for offset, refs in sorted(references().items()):
        try:
            panel = parse(data, offset)
        except (ValueError, IndexError) as error:
            excluded.append(dict(offset='%04X'%offset, reason=str(error)))
            continue
        panel['references'] = refs
        m.ds_write(0, saved)
        def word(o, v):
            m.ds_write(o, int(v).to_bytes(2, 'little'))
        word(0x0200, 0)
        m.ds_write(0x8096, bytes([0]))
        m.ds_write(0x5A4E, bytes([255]))
        m.ds_write(0xADCF, bytes([0]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, bytes([0]))
        word(0x1234, 0)
        word(0x122A, 0)
        g, mem, planes = make_game(m)
        status = ctx.lib.textbox_draw_nonmodal(ctypes.byref(g), offset, 0, 0, 40, 24)
        m.call(0, 0x5032, si=offset, ax=0, bx=0, cx=40, dx=24, es=m.DATA_SEG)
        fails = []
        compare('UI panel %04X'%offset, mem, planes, m, fails)
        if status or fails:
            raise RuntimeError(str(fails))
        panels.append(panel)
    exe = root/'exe/TERM_unpacked.exe'
    folder = root/'out/tables'
    folder.mkdir(exist_ok=True, parents=True)
    result = dict(executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), runtime_text_segment='%04X'%seg,
                file_text_segment='%04X'%((seg-dosemu.LOAD_SEG)&65535), panels=panels, excluded=excluded,
                validation='Every exported panel matches original 5032 in memory and EGA in a prepared 40x24-cell window.',
                limitations=['Subset found by direct immediate SI references; dynamic/branch-dependent layouts are not complete.',
                             'Relative coordinate bytes are added modulo 256 by the source; caller box positions/dimensions are not inferred.',
                             'Text includes unreachable or conditional dialogs; extraction is not proof a dialog is reachable.'])
    (folder/'ui_panels.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+chr(10), encoding='utf-8')
    with (folder/'ui_panels.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['offset', 'colour', 'line_index', 'relative_x', 'relative_y', 'text', 'call_sites'])
        writer.writeheader()
        for panel in panels:
            for index, line in enumerate(panel['lines']):
                writer.writerow(dict(offset=panel['offset'], colour=panel['colour'], line_index=index, **line, call_sites=';'.join(ref['call'] for ref in panel['references'])))
    print('%d referenced UI panels exported; all original/native comparisons passed; %d arguments excluded.'%(len(panels), len(excluded)))
    print(folder/'ui_panels.json')

if __name__ == '__main__':
    main()
