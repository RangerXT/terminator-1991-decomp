"""Find where the C rewrite first departs from the original inside one frame's scene.

  python tools/frame_diag.py <frame> [--from ingame] [--keys "t:key[:hold],..."]

Runs the game (with interrupts) to the start of the scene (0000:06FF) of the given frame,
saves that moment as out/emu/states/_diag.pkl, then lets the original draw the scene with
interrupts off, stopping after every draw-list record, while the C code draws the same
records one at a time from the same starting memory. Reports the first record after which
the screens or the card registers differ, with the data-segment differences at that point
(between the two lists the original runs two routines that the C path skips; they change
a few variables but draw nothing).
"""
import ctypes
import os
import struct
import sys

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EFLAGS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import difftest  # noqa: E402
import dosemu  # noqa: E402
import frame_demo as fd  # noqa: E402

BASE = dosemu.LOAD_SEG << 4
DS_END = 0xEA70
RECORD_END = 0x2844


def snapshot_at_scene(start, keys, frame):
    m = dosemu.Machine()
    m.load(os.path.join(ROOT, 'out', 'emu', 'states', start + '.pkl'))
    for t, k, hold in keys:
        m.press(m.ticks + t, k, hold=hold)
    st = {'frame': -1, 'stop': False}

    def on_frame(uc, a, s, u):
        st['frame'] += 1

    def on_scene(uc, a, s, u):
        if st['frame'] == frame:
            st['stop'] = True
            uc.emu_stop()

    m.uc.hook_add(UC_HOOK_CODE, on_frame, None, BASE + fd.FRAME_START, BASE + fd.FRAME_START)
    m.uc.hook_add(UC_HOOK_CODE, on_scene, None, BASE + fd.SCENE, BASE + fd.SCENE)
    m.run(ticks=200000, until=lambda mm: st['stop'])
    path = os.path.join(ROOT, 'out', 'emu', 'states', '_diag.pkl')
    m.save(path)
    return path


def diagnose(path):
    lib = difftest.Ctx().lib
    lib.draw_object_list.restype = ctypes.c_int
    m = dosemu.Machine()
    m.load(path)
    ds = m.DATA_SEG << 4
    start = fd.planes_of(m)
    mem = ctypes.create_string_buffer(bytes(m.uc.mem_read(0, 0xA0000)), 0x100000 + 16)
    scr = ctypes.create_string_buffer(start, len(start))
    g = fd.Game(ctypes.addressof(mem), ctypes.addressof(mem) + ds, ctypes.addressof(scr), m.DATA_SEG)

    def word(off):
        return int.from_bytes(mem.raw[ds + off:ds + off + 2], 'little')

    mine = []
    ground = word(0x91D8)
    mem[ds + 0x00BB] = 1
    for i in range(ground):
        rec = 0x2836 + 12 * i
        fields = struct.unpack_from('<hhhHHh', mem.raw, ds + rec)
        lib.draw_object_list(ctypes.byref(g), ctypes.c_uint16(rec), ctypes.c_uint16(1))
        mine.append((f'ground record {i}', fields, scr.raw, mem.raw[ds:ds + DS_END]))
    mem[ds + 0x00BB] = 0
    objects, first = word(0x50AC), word(0x01FE)
    for i in range(objects):
        rec = (first + 12 * i) & 0xFFFF
        fields = struct.unpack_from('<hhhHHh', mem.raw, ds + rec)
        lib.draw_object_list(ctypes.byref(g), ctypes.c_uint16(rec), ctypes.c_uint16(1))
        mine.append((f'object record {i}', fields, scr.raw, mem.raw[ds:ds + DS_END]))

    theirs = []

    def record_end(uc, a, s, u):
        theirs.append((fd.planes_of(m), bytes(uc.mem_read(ds, DS_END))))

    m.uc.hook_add(UC_HOOK_CODE, record_end, None, BASE + RECORD_END, BASE + RECORD_END)
    uc = m.uc
    uc.reg_write(UC_X86_REG_EFLAGS, uc.reg_read(UC_X86_REG_EFLAGS) & ~dosemu.IF_ & 0xFFFF)
    m.pending = None
    until = BASE + fd.SCENE_DONE
    while True:
        m.step(until, 1_000_000)
        if m.pending is not None:
            m._apply_pending()
            continue
        if (m.cs << 4) + m.ip == until:
            break

    print(f'{ground} ground records, {objects} object records; the original finished {len(theirs)} records')
    planes = fd.PLANE_BYTES
    ignore = {0x59E2, 0x59E3, 0x7756, 0x7757}      # written after the point where the original is sampled
    for (label, fields, c_screen, c_ds), (o_screen, o_ds) in zip(mine, theirs):
        pixels = [k for k in range(planes) if c_screen[k] != o_screen[k]]
        regs = c_screen[planes:] != o_screen[planes:]
        data = [k for k in range(DS_END) if c_ds[k] != o_ds[k] and k not in ignore]
        if pixels or regs:
            print(f'first difference after {label} {fields} (x, y, z, flags, id, extra):')
            if pixels:
                page = int.from_bytes(o_ds[0x1234:0x1236], 'little')
                where = sorted({((k & 0xFFFF) - page) // 40 for k in pixels})
                print(f'  {len(pixels)} plane bytes differ, rows {where[0]}..{where[-1]}; first: plane {pixels[0] >> 16} '
                      f'offset {pixels[0] & 0xFFFF:04X} C {c_screen[pixels[0]]:02X} original {o_screen[pixels[0]]:02X}')
            if regs:
                print(f'  card registers: C {c_screen[planes:].hex(" ")}  original {o_screen[planes:].hex(" ")}')
            if data:
                print(f'  {len(data)} data-segment bytes differ: ' + ', '.join(
                    f'DS:{k:04X} C {c_ds[k]:02X} original {o_ds[k]:02X}' for k in data[:16]))
            return 1
    print('no difference on screen or in the card registers after any record')
    return 0


def main():
    argv = sys.argv[1:]
    opts = {'--from': 'ingame', '--keys': ''}
    args = []
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if not args:
        print(__doc__)
        return 2
    keys = []
    for item in filter(None, opts['--keys'].split(',')):
        parts = item.split(':')
        keys.append((int(parts[0]), parts[1], int(parts[2]) if len(parts) > 2 else 6))
    return diagnose(snapshot_at_scene(opts['--from'], keys, int(args[0])))


if __name__ == '__main__':
    sys.exit(main())
