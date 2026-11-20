"""draw_object_list against recorded calls of the original at 0000:271E: a whole draw list
(ground pass or object pass of one frame), from the 12-byte records to pixels.

Captures: python tools/capture.py 0000:271E drawlist --count 24 --skip 3 --ticks 120 --keys "2:right:12,18:up:15,40:left:10,60:up:20"
          python tools/capture.py 0000:271E drawlist2 --count 12 --skip 3 --ticks 60 --from ingame_walked --keys "2:left:14,20:up:20"

Compared after each call: all conventional memory (640 KB) except the stack, and all four
EGA bit planes. The C code is given the whole memory image because meshes are fetched from
other segments.
"""
import ctypes
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from test_polyfill import PLANE_BYTES, SCREEN_BYTES, planes_of, screen_differences  # noqa: E402

CASES = 0
MEM = 0x100000
STACK_BYTES = 0x400


class Game(ctypes.Structure):
    _fields_ = [('mem', ctypes.c_void_p), ('ds', ctypes.c_void_p), ('planes', ctypes.c_void_p),
                ('ds_seg', ctypes.c_uint16)]


def make_game(m):
    """A C-side copy of machine `m`: (Game, memory buffer, planes buffer)."""
    raw = bytes(m.uc.mem_read(0, 0xA0000))
    mem = ctypes.create_string_buffer(raw, MEM + 16)
    planes = ctypes.create_string_buffer(planes_of(m), SCREEN_BYTES)
    g = Game(ctypes.addressof(mem), ctypes.addressof(mem) + (m.DATA_SEG << 4), ctypes.addressof(planes), m.DATA_SEG)
    return g, mem, planes


def compare(label, mem, planes, after, fails):
    """Compare the C side with machine `after`. Returns True if identical."""
    want = bytes(after.uc.mem_read(0, 0xA0000))
    got = mem.raw[:0xA0000]
    stack = after.r(dosemu.UC_X86_REG_SS) << 4
    regions = [(0, stack), (stack + STACK_BYTES, 0xA0000)]
    for lo, hi in regions:
        if got[lo:hi] != want[lo:hi]:
            diff = [i for i in range(lo, hi) if got[i] != want[i]]
            ds = after.DATA_SEG << 4
            where = f'DS:{diff[0] - ds:04X}' if ds <= diff[0] < ds + 0x10000 else f'linear {diff[0]:05X}'
            fails.append(f'{label}: memory, {len(diff)} bytes differ, first at {where}')
            return False
    problem = screen_differences(planes.raw, planes_of(after))
    if problem:
        fails.append(f'{label}: {problem}')
        return False
    return True


KINDS = ['cut-out figure (4000)', 'other vehicle (2000)', 'guided projectile (0800)', 'flag 1000',
         'player vehicle (0020)', 'vehicle part (0024)', 'cut-out vehicle (4020)', 'hidden (0040)',
         'negative extra', 'unchanged']


def force_kinds(m, si, count, shift, leave_out=()):
    """Rewrite the records of an object list so that record i becomes kind (i + shift) % 10
    (kinds in `leave_out` stay as they are). Positions are kept, so the objects stay where
    the buildings were. Returns kinds used."""
    ds = m.DATA_SEG
    used = {}
    for i in range(count):
        rec = (si + 12 * i) & 0xFFFF
        flags, ident, extra = struct.unpack('<HHh', m.ds_read(rec + 6, 6))
        kind = (i + shift) % len(KINDS)
        if kind in leave_out:
            kind = 9
        model_mesh = m.rw(ds, 0x0B30 + 22 * (i % 10) + 0x14)
        if kind == 0:
            flags, ident = 0x4000, 2 * (i % 10)
        elif kind == 1:
            # an id other than DS:9A64 means "the player's vehicle mesh", DS:72CA as a number
            flags, ident = 0x2000, (m.rw(ds, 0x9A64) if i % 2 or 4 in leave_out else 2 * (i % 10))
        elif kind == 2:
            flags, ident = 0x0800 | (flags & 3), (i * 37) & 0x1FF
        elif kind == 3:
            flags = 0x1000
        elif kind == 4:
            flags = 0x0020
        elif kind == 5:
            flags = 0x0024
        elif kind == 6:
            flags, ident = 0x4020, model_mesh
        elif kind == 7:
            flags |= 0x0040
        elif kind == 8:
            extra = -1
        m.ds_write(rec + 6, struct.pack('<HHh', flags, ident, extra))
        used[kind] = used.get(kind, 0) + 1
    return used


def run(ctx):
    global CASES
    import gzip
    import pickle
    lib = ctx.lib
    lib.draw_object_list.restype = ctypes.c_int
    fails = []
    passes = {'ground': 0, 'object': 0}
    records = 0
    flag_bits = {}
    drew = 0
    forced = {}
    forced_drew = 0
    states = []
    for name in ('drawlist', 'drawlist2'):
        states += pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '.pkl.gz'), 'rb'))
    for n, st in enumerate(states):
        before = capture.restore(st)
        after = capture.restore(st)
        rin = {r: before.r(before.REG_BY_NAME[r]) for r in capture.REG_NAMES}
        capture.run_to_return(after)
        ground = before.ds_read(0x00BB, 1)[0]
        passes['ground' if ground else 'object'] += 1
        for i in range(rin['cx']):
            flags = struct.unpack('<H', before.ds_read((rin['si'] + 12 * i + 6) & 0xFFFF, 2))[0]
            records += 1
            for bit in range(16):
                if flags >> bit & 1:
                    flag_bits[1 << bit] = flag_bits.get(1 << bit, 0) + 1
        g, mem, planes = make_game(before)
        start = planes.raw
        status = lib.draw_object_list(ctypes.byref(g), ctypes.c_uint16(rin['si']), ctypes.c_uint16(rin['cx']))
        CASES += 1
        if status != 0:
            fails.append(f'capture {n}: C version returned {status}')
            continue
        if planes_of(after)[:PLANE_BYTES] != start[:PLANE_BYTES]:
            drew += 1
        compare(f'capture {n} ({"ground" if ground else "object"} pass, {rin["cx"]} records)', mem, planes, after, fails)
        if ground:
            continue

        # The recordings only hold buildings. Turn the same lists into every other kind of
        # record the routine knows, and compare again.
        for shift in (0, 3, 7):
            m = capture.restore(st)
            # A vehicle-part record (0024) takes DS:72CA as a mesh offset in the model
            # segment, a player-vehicle record (0020) takes it as a building number, so
            # one list cannot hold valid records of both kinds.
            used = force_kinds(m, rin['si'], rin['cx'], shift, leave_out=(4,) if shift == 7 else (5,) if shift == 0 else ())
            player = m.rw(m.DATA_SEG, 0x03A0)
            if shift == 3:                      # player on foot: vehicle parts are skipped
                m.ds_write(player + 0x0E, bytes([m.ds_read(player + 0x0E, 1)[0] & 0xFE]))
            if shift == 7:                      # the other colour table for cut-out vehicles
                m.ds_write(0x04BA, struct.pack('<H', 0x0508))
                m.ds_write(0x72CA, struct.pack('<H', m.rw(m.DATA_SEG, 0x0B30 + 22 * (n % 10) + 0x14)))
            g, mem, planes = make_game(m)
            start = planes.raw
            status = lib.draw_object_list(ctypes.byref(g), ctypes.c_uint16(rin['si']), ctypes.c_uint16(rin['cx']))
            CASES += 1
            label = f'capture {n} with forced kinds (shift {shift})'
            try:
                capture.run_to_return(m, max_instr=5_000_000)
            except Exception as e:              # the original hung or ran off into data
                fails.append(f'{label}: original: {e} (C returned {status})')
                continue
            if status != 0:
                fails.append(f'{label}: C version returned {status}')
                continue
            for k, c in used.items():
                forced[k] = forced.get(k, 0) + c
            if planes_of(m)[:PLANE_BYTES] != start[:PLANE_BYTES]:
                forced_drew += 1
            compare(label, mem, planes, m, fails)
    bits = ', '.join(f'{b:04X}: {c}' for b, c in sorted(flag_bits.items()))
    print(f'    drawlist recordings: {passes["ground"]} ground passes, {passes["object"]} object passes, '
          f'{records} records, {drew} changed the screen')
    print(f'    record flag bits seen in recordings: {bits}')
    print(f'    forced kinds ({forced_drew} lists changed the screen): '
          + ', '.join(f'{KINDS[k]}: {c}' for k, c in sorted(forced.items())))
    return fails
