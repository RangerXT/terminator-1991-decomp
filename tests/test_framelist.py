"""build_frame_draw_list against the original at 0000:036E: everything to be drawn this frame
is gathered into one list, then culled and sorted. Also angle_between (0000:5E62) on random
points.

Captures: python tools/capture.py 0000:036E framelist --count 16 --skip 3 --ticks 160 --keys "2:right:30,40:up:30,80:left:40"

The recordings hold only map objects, so each is also run with every other source of
records forced on: guided projectiles, pickups, things in flight, the special and the timed object
(including its going off, which runs the blast code), figures, the companion in each of its
forms, debris records. Compared: all conventional memory except the stack, and the calls
into untranslated code (see tests/test_blast.py).
"""
import ctypes
import gzip
import os
import pickle
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from test_blast import GameEvent, c_events, set_clock, stub  # noqa: E402
from test_drawlist import compare, make_game  # noqa: E402

CASES = 0


def w16(m, off, *values):
    m.ds_write(off, struct.pack(f'<{len(values)}H', *[v & 0xFFFF for v in values]))


def near(m, k):
    """A position (x, z) a little in front of the player, different for each k."""
    player = m.rw(m.DATA_SEG, 0x03A0)
    px, pz = m.rw(m.DATA_SEG, player), m.rw(m.DATA_SEG, player + 4)
    return (px + 150 * ((k % 5) - 2)) & 0xFFFF, (pz - 300 - 170 * (k % 7)) & 0xFFFF


def guided_projectiles(m):
    w16(m, 0x11A0, 4)
    for i in range(4):
        x, z = near(m, i)
        m.ds_write(0x10F0 + 0x12 * i, struct.pack('<9H', x, 0, z, (i * 91) & 0x1FF, 0, 0, 0, 0, 0 if i == 2 else 1))


def pickups(m):
    player = m.rw(m.DATA_SEG, 0x03A0)
    col, row = m.rw(m.DATA_SEG, player + 0x1E), m.rw(m.DATA_SEG, player + 0x20)
    for i in range(20):
        dc, dr = (i % 5) - 2, (i % 4) - 1
        m.ds_write(0x253 + 13 * i, struct.pack('<4HHBBB', (col + dc) & 0xFFFF, (row + dr) & 0xFFFF,
                                               (100 + 41 * i) % 1024, (900 - 37 * i) % 1024, 0, 1 if i % 3 else 0, 0, 0))


def projectiles(m):
    for i in range(30):
        x, z = near(m, i)
        if i % 6 == 5:
            x = (x + 6000) & 0xFFFF            # too far: gets switched off
        m.ds_write(0xB520 + 10 * i, struct.pack('<5H', x, (0x10000 - 20 - i) & 0xFFFF, z, 0xFFFF if i % 4 == 3 else i, i))
    w16(m, 0xB51E, 5)


def special(m):
    m.ds_write(0x0373, b'\x01')
    x, z = near(m, 3)
    w16(m, 0x0367, x, 0xFFE0, z)


def timed(steps):
    def change(m):
        x, z = near(m, 5)
        w16(m, 0x0B08, x, z)
        w16(m, 0x0B08 + 6, steps)
        w16(m, 0x9A64, 2)       # its mesh: a loaded one (in this snapshot DS:9A64 names none)
    return change


def figures(m):
    w16(m, 0x119A, 6)
    for i in range(6):
        x, z = near(m, i + 2)
        m.ds_write(0x0DF0 + 12 * i, struct.pack('<6H', x, 0, z, 0x4000, 2 * (i % 10), 20))


def companion(flags_1153, flags_1152, flag_01de, flag_1154, mode_11be, vehicle_bit, walking):
    def change(m):
        m.ds_write(0x0345, b'\0')
        m.ds_write(0x1153, bytes([flags_1153]))
        m.ds_write(0x1152, bytes([flags_1152]))
        m.ds_write(0x01DE, bytes([flag_01de]))
        m.ds_write(0x1154, bytes([flag_1154]))
        w16(m, 0x11BE, mode_11be)
        x, z = near(m, 4)
        w16(m, 0xDE52, x)
        w16(m, 0xDE54, z)
        x, z = near(m, 6)
        w16(m, 0xE3EC, x)
        w16(m, 0xE3EE, z)
        vehicle = m.rw(m.DATA_SEG, 0x04BA)
        b = m.ds_read(vehicle + 0x0E, 1)[0]
        m.ds_write(vehicle + 0x0E, bytes([(b & 0xFE) | vehicle_bit]))
        w16(m, vehicle + 0x0A, walking)
        w16(m, 0x53C + 0x0A, walking)
        m.ds_write(0x5A0 + 2, bytes([1 if walking else 3]))
        m.ds_write(0x5A8 + 2, bytes([1 if walking else 3]))
    return change


def debris(m):
    seg = m.rw(m.DATA_SEG, 0x96DC)
    w16(m, 0x117A, 5)
    for i in range(5):
        x, z = near(m, i + 1)
        m.wb(seg, 12 * i, struct.pack('<6H', x, (0x10000 - 30) & 0xFFFF, z, 0x0100, i, 10))


def everything(m):
    for change in (guided_projectiles, pickups, projectiles, special, timed(7), figures,
                   companion(1, 0, 0, 1, 0, 0, 3), debris):
        change(m)


VARIANTS = [
    ('as recorded', lambda m: None),
    ('guided projectiles', guided_projectiles), ('pickups', pickups), ('things in flight', projectiles), ('special object', special),
    ('timed object', timed(9)), ('timed object, held', timed(0x8003)), ('timed object, expiring', timed(1)),
    ('figures', figures),
    ('companion: vehicle', companion(1, 0, 1, 0, 0, 0, 0)),
    ('companion: figure standing', companion(1, 0, 0, 0, 0, 0, 0)),
    ('companion: figure walking', companion(1, 0, 1, 0, 0, 1, 2)),
    ('companion: figure running, second figure', companion(1, 0, 0, 1, 0, 0, 3)),
    ('companion: second figure only', companion(0, 0, 0, 1, 2, 0, 1)),
    ('companion: second figure at its place', companion(1, 1, 0, 0, 0, 0, 0)),
    ('debris records', debris),
    ('everything at once', everything),
]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.build_frame_draw_list.restype = ctypes.c_int
    lib.angle_between.restype = ctypes.c_uint16
    fails = []

    # angle_between on random and edge-case points
    m = ctx.game()
    rng = random.Random(3)
    ds = ctx.ds_copy()
    edge = [-32768, -32767, -1, 0, 1, 2, 63, 64, 65, 1000, 32767]
    points = [(a, b, c, d) for a in edge for b in edge for c in (0, 5, -7) for d in (0, -3, 9)]
    points += [tuple(rng.randrange(-2000, 2000) for _ in range(4)) for _ in range(3000)]
    points += [tuple(rng.randrange(-32768, 32768) for _ in range(4)) for _ in range(1000)]
    for a, b, c, d in points:
        want = m.call(0x0000, 0x5E62, ax=a, bx=b, cx=c, dx=d)['ax']
        got = lib.angle_between(ds, ctypes.c_int16(a), ctypes.c_int16(b), ctypes.c_int16(c), ctypes.c_int16(d))
        CASES += 1
        if got != want:
            fails.append(f'angle_between({a}, {b}, {c}, {d}) = {got}, original {want}')
            if len(fails) > 5:
                return fails

    states = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'framelist.pkl.gz'), 'rb'))
    kept = {}
    untranslated = 0
    for n, st in enumerate(states):
        for label, change in VARIANTS:
            mm = stub(capture.restore(st))
            change(mm)
            g, mem, planes = make_game(mm)
            set_clock(lib, mm)
            lib.game_events((GameEvent * 512)(), 512)
            status = lib.build_frame_draw_list(ctypes.byref(g))
            CASES += 1
            where = f'capture {n}, {label}'
            if status != 0:
                fails.append(f'{where}: C version returned {status}')
                continue
            try:
                capture.run_to_return(mm, max_instr=20_000_000)
            except Exception as e:
                fails.append(f'{where}: original: {e}')
                continue
            mine, theirs = c_events(lib), list(mm.calls)
            if mine != theirs:
                fails.append(f'{where}: calls into untranslated code differ: C {mine[:6]}, original {theirs[:6]}')
                continue
            untranslated += bool(theirs)
            if compare(where, mem, planes, mm, fails):
                before, after = mm.rw(mm.DATA_SEG, 0x020E), mm.rw(mm.DATA_SEG, 0x50AC)
                a, b = kept.get(label, (0, 0))
                kept[label] = (a + before, b + after)
    print('    framelist: records gathered -> kept after culling, per variant: '
          + ', '.join(f'{k}: {a}->{b}' for k, (a, b) in kept.items()))
    print(f'    framelist: in {untranslated} cases the timed object went off while the list was built')
    return fails
