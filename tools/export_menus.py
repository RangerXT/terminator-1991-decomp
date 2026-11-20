"""Export statically parameterized planar menus with original layouts and handlers.
Each layout is rendered by native C and the original. Dynamic text/parameters are
explicitly excluded; this is not an inventory of every menu at runtime.
"""
import csv, ctypes, gzip, hashlib, json, pickle, re, sys
from pathlib import Path
import capture, difftest, dosemu
sys.path.insert(0, str(Path(dosemu.ROOT)/'tests'))
from test_drawlist import make_game, compare
from test_menu import Call, Platform
from export_ui_panels import parse
from unicorn import UC_HOOK_CODE

def references(root):
    result = []
    excluded = []
    recent = []
    for line in (root/'disasm/seg_0000.asm').read_text().splitlines():
        match = re.match(r'^([0-9A-F]{4}:[0-9A-F]{4})\s+[0-9a-f]+\s+(.+)$', line)
        if not match:
            continue
        addr, op = match.groups()
        if op in ['call menu_display', 'call sub_0000_48E6']:
            regs = {}
            for a, instr in recent[-6:]:
                mov = re.fullmatch(r'mov (si|ax|bx|cx|dx|di), (0x[0-9a-f]+|[0-9]+)', instr)
                if mov:
                    regs[mov[1]] = int(mov[2], 0)
            if len(regs) == 6 and regs['si'] >= 0x200:
                result.append((addr, regs))
            else:
                excluded.append(dict(call=addr, reason='dynamic text or nonliteral parameter'))
        recent.append((addr, op))
        recent = recent[-6:]
    return result, excluded

def main():
    root = Path(dosemu.ROOT)
    ctx = difftest.Ctx()
    caps = pickle.load(gzip.open(root/'tests/captures/menu_live.pkl.gz', 'rb'))
    refs, excluded = references(root)
    menus = []
    for call, r in refs:
        m = capture.restore(caps[0])
        seg = m.rw(m.DATA_SEG, 0xEA36)
        try:
            panel = parse(m.rb(seg, 0, 65536), r['si'])
        except (ValueError, IndexError) as error:
            excluded.append(dict(call=call, reason=str(error)))
            continue
        m.ds_write(0x5BDA, bytes([0]))
        m.ds_write(0x5BF5, bytes([0]))
        m.wb(dosemu.LOAD_SEG, 0x4A96, bytes([0xC3]))
        g, mem, planes = make_game(m)
        @Call
        def poll(gp, op, a, b, user):
            return 0
        host = Platform(poll, None)
        status = ctx.lib.menu_prepare(ctypes.byref(g), r['si'], r['ax'], r['bx'], r['cx'], r['dx'], r['di'], ctypes.byref(host))
        m.call(0, 0x48E6, **r, max_instr=100_000_000)
        fails = []
        compare('menu export '+call, mem, planes, m, fails)
        if status or fails:
            raise RuntimeError((call, status, fails))
        count = m.rw(m.DATA_SEG, 0x784C)
        if count != len(panel['lines'])-1:
            raise RuntimeError('menu option count '+call)
        panel.update(call=call, x=r['ax'], y=r['bx'], width=r['cx'], height=r['dx'], actions_offset='%04X'%r['di'], verified=True)
        panel['options'] = []
        for i, line in enumerate(panel['lines'][1:]):
            panel['options'].append(dict(index=i, text=line['text'], hotkey=line['text'][:1], handler='0000:%04X'%m.rw(m.DATA_SEG, r['di']+i*2)))
        menus.append(panel)
    out = root/'out/tables'
    out.mkdir(parents=True, exist_ok=True)
    doc = dict(executable_sha256=hashlib.sha256(Path(dosemu.EXE).read_bytes()).hexdigest(), scope='literal static layouts verified in captured English resource context; dynamic menus excluded', menus=menus, excluded=excluded)
    (out/'menus.json').write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding='utf-8')
    with (out/'menus.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['call', 'title', 'x', 'y', 'width', 'height', 'index', 'text', 'hotkey', 'handler'])
        for p in menus:
            for o in p['options']:
                w.writerow([p['call'], p['lines'][0]['text'], p['x'], p['y'], p['width'], p['height'], o['index'], o['text'], o['hotkey'], o['handler']])
    print('Verified static menu layouts:', len(menus), 'options:', sum(len(m['options']) for m in menus), 'excluded:', len(excluded))
if __name__ == '__main__':
    main()
