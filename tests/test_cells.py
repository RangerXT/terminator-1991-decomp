"""collect_visible_objects against the original at 0000:3C18-3D61, the part of
update_visible_cells (0000:3B88) that reads the map cells in view into the visible-object
list. The original is run from 3C18 to 3D62, the C function on a copy of the same memory.

Captures: python tools/capture.py 0000:3C18 cells --count 30 --skip 0 --ticks 260 --keys "2:right:40,50:up:30,90:left:60,160:up:40,210:right:30"
          python tools/capture.py 0000:3C18 cells2 --count 14 --skip 0 --ticks 160 --from ingame_walked --keys "2:left:50,60:up:50,120:right:30"

Variants: reduced detail; each of the eight heading sectors forced; some of the visible
objects put on the removed list; extra (non-map) objects placed in cells around the player.
Compared: all conventional memory except the stack.
"""
import ctypes
import gzip
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from test_drawlist import compare, make_game  # noqa: E402

CASES = 0
END = 0x3D62
SCRATCH_SEG = 0x9000          # free memory for forged extra entries


def run_original(m):
    until = (dosemu.LOAD_SEG << 4) + END
    uc = m.uc
    uc.reg_write(dosemu.UC_X86_REG_EFLAGS, uc.reg_read(dosemu.UC_X86_REG_EFLAGS) & ~dosemu.IF_ & 0xFFFF)
    m.pending = None
    for _ in range(40):
        m.step(until, 1_000_000)
        if m.pending is not None:
            m._apply_pending()
            if m.blocked:
                raise RuntimeError(m.blocked)
            continue
        if (m.cs << 4) + m.ip == until:
            return
    raise RuntimeError('did not reach the end of the cell walk')


def variants(st, lib):
    yield 'as recorded', lambda m: None
    yield 'reduced detail', lambda m: m.ds_write(0xABCA, struct.pack('<H', 1))
    for octant in range(8):
        yield f'heading sector {octant}', lambda m, o = octant: m.ds_write(0x04C4, struct.pack('<H', 2 * o))

    def removed(m):
        # find out where the visible records come from, then list every third as removed
        probe = capture.restore(st)
        g, mem, planes = make_game(probe)
        regs = {r: probe.r(probe.REG_BY_NAME[r]) for r in ('ax', 'cx', 'dx')}
        lib.collect_visible_objects(ctypes.byref(g), regs['ax'], regs['cx'], regs['dx'])
        ds = probe.DATA_SEG << 4
        count = struct.unpack_from('<H', mem.raw, ds + 0x7240)[0]
        seg = struct.unpack_from('<H', mem.raw, ds + 0x91D4)[0]
        table = bytearray(m.ds_read(0x0F70, 32 * 12))
        for j, k in enumerate(range(0, min(count, 96), 3)):
            src = struct.unpack_from('<H', mem.raw, ds + 0x72DC + 2 * k)[0]
            table[12 * j:12 * j + 8] = probe.rb(seg, src, 8)
        m.ds_write(0x0F70, bytes(table))
    yield 'removed objects', removed

    def extras(m):
        player = m.rw(m.DATA_SEG, 0x03A0)
        col, row = m.rw(m.DATA_SEG, player + 0x1E), m.rw(m.DATA_SEG, player + 0x20)
        entries = b''
        n = 0
        for dc in (-3, -1, 0, 0, 2, 4):
            for dr in (-4, -2, 0, 1, 3):
                key = ((col + dc) & 0xFF) | (((row + dr) & 0xFF) << 8)
                entries += struct.pack('<HHHHHHH', key, 100 + 37 * n % 900, (900 - 53 * n) % 1024, 2 * (n % 3),
                                       0x1234 + n, 0x20 * (n % 2), n)
                n += 1
        m.wb(SCRATCH_SEG, 0, entries)
        m.ds_write(0x1200, struct.pack('<HH', 0, SCRATCH_SEG))
        m.ds_write(0x04C6, struct.pack('<H', n))
    yield 'extra objects', extras


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.collect_visible_objects.restype = None
    fails = []
    states = []
    for name in ('cells', 'cells2'):
        states += pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '.pkl.gz'), 'rb'))
    total = far = 0
    counts = set()
    by_variant = {}
    for n, st in enumerate(states):
        for label, change in variants(st, lib):
            m = capture.restore(st)
            change(m)
            regs = {r: m.r(m.REG_BY_NAME[r]) for r in ('ax', 'cx', 'dx')}
            g, mem, planes = make_game(m)
            lib.collect_visible_objects(ctypes.byref(g), ctypes.c_uint16(regs['ax']), ctypes.c_uint16(regs['cx']),
                                        ctypes.c_uint16(regs['dx']))
            CASES += 1
            where = f'capture {n}, {label}'
            try:
                run_original(m)
            except Exception as e:
                fails.append(f'{where}: original: {e}')
                continue
            if compare(where, mem, planes, m, fails):
                count = m.rw(m.DATA_SEG, 0x7240)
                counts.add(count)
                kind = label.split(' sector')[0]
                by_variant[kind] = by_variant.get(kind, 0) + count
                total += count
                far += sum(1 for i in range(count) if m.rw(m.DATA_SEG, 0x5F80 + 12 * i + 6) & 0x80)
    print(f'    cells: {total} records produced ({far} flagged far), list sizes {min(counts)}..{max(counts)}')
    print('    cells: records per variant: ' + ', '.join(f'{k}: {v}' for k, v in by_variant.items()))
    return fails
