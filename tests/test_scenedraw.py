"""06FF ground/object pass, gameplay hooks and alternative obscured view."""
import ctypes
import gzip
import itertools
import os
import pickle
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from unicorn import UC_HOOK_CODE
from test_blast import GameEvent, set_clock
from test_drawlist import make_game
from test_imageload import compare, regions
from test_mapsetupreal import RESOURCE, Resources

CASES = 0


def run(ctx):
    global CASES
    failures = []
    base = dosemu.LOAD_SEG << 4
    buf = (GameEvent * 512)()
    with gzip.open(os.path.join(capture.CAPDIR, 'draw_scene_live.pkl.gz'), 'rb') as f:
        states = pickle.load(f)
    for i, st in enumerate(states):
        profiles = ('live', 'ground', 'objects', 'noise', 'blank', 'disabled') if i % 3 == 0 else ('live',)
        for profile in profiles:
            m = capture.restore(st)

            def ww(off, value):
                m.ds_write(off, struct.pack('<H', value))
            def wb(off, value):
                m.ds_write(off, bytes([value]))

            normal = profile in ('live', 'ground', 'objects')
            if profile == 'ground':
                ww(0x50AC, 0)
            if profile == 'objects':
                ww(0x91D8, 0)
            if not normal:
                actor = 0x04D4 if profile == 'blank' else 0x0508
                ww(0x03A0, actor)
                ww(0x1172, 0 if profile == 'disabled' else 1 + i % 4)
                wb(actor + 25, 128 if profile == 'disabled' else 0)
                wb(0xAA83, i % 2)
                ww(0x1224, [0x3FFF, 0x4000, 0x0210][i // 3 % 3])
                wb(0x11CA, (i // 3) % 2)
            wb(0x50B0, 255)
            expected, got = [], []
            m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))

            def track(uc, address, size, ud):
                off = address - base
                expected.append((off, m.ax() & 255, m.ds_read(0x80E9, 1)[0]) if off == 0x89A2 else (off, 0, 0))

            for off in (0x89A2, 0x0D8D, 0x0DAA):
                m.uc.hook_add(UC_HOOK_CODE, track, None, base + off, base + off)
            m.vga.clock = itertools.cycle((dosemu.FRAME_INSTR // 2, 0, 0, dosemu.FRAME_INSTR // 2)).__next__
            g, mem, planes = make_game(m)

            def drain():
                for event in buf[:ctx.lib.game_events(buf, 512)]:
                    got.append((0x89A2 if event.kind == 1 else event.kind, event.a, event.b))

            @RESOURCE
            def retrace(gp, op, a, b, user):
                drain()
                got.append((op, a, b))
                return 0

            host = Resources(retrace, None)
            ctx.lib.game_events(buf, 512)
            set_clock(ctx.lib, m)
            status = ctx.lib.draw_scene(ctypes.byref(g), ctypes.byref(host))
            drain()
            capture.run_to_return(m, max_instr=100_000_000)
            CASES += 1
            label = f'draw scene {i}/{profile}'
            if status or got != expected:
                return [f'{label}: status {status}; events {got} != {expected}']
            compare(label, mem, planes, m, regions(m), failures)
            if failures:
                return failures
    # Exercise the sort's equal/negative depths and intermediate swap record,
    # independently of which objects happen to be aimable in the live captures.
    rng = random.Random(0xA3D7)
    m = capture.restore(states[0])
    for i in range(96):
        count = i % 24
        raw = bytearray(rng.randbytes(18 * (count + 1)))
        for j in range(count):
            depth = rng.choice((-32768, -1, 0, 3, 3, 32767))
            struct.pack_into('<h', raw, 18 * (j + 1) + 4, depth)
        m.ds_write(0xB17C, raw)
        m.ds_write(0xB64E, struct.pack('<H', count))
        g, mem, planes = make_game(m)
        ctx.lib.sort_targets_by_depth(ctypes.c_void_p(g.ds))
        m.call(0, 0xA3D7, es=m.DATA_SEG)
        CASES += 1
        compare(f'depth sorting {i}', mem, planes, m, regions(m), failures)
        if failures:
            return failures
    return failures
