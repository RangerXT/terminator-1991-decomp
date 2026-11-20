"""06EF pre-render update through CAF, guidance, both actor loops, and debris."""
import ctypes
import gzip
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from test_blast import GameEvent, set_clock
from test_drawlist import make_game
from test_imageload import compare, regions
from unicorn import UC_HOOK_CODE

CASES = 0


def run(ctx):
    global CASES
    base = dosemu.LOAD_SEG << 4
    buf = (GameEvent * 128)()
    fails = []
    path = os.path.join(capture.CAPDIR, 'scene_world_live.pkl.gz')
    with gzip.open(path, 'rb') as f:
        states = pickle.load(f)
    jobs = [(i, 'live') for i in range(len(states))]
    jobs += [(i, p) for i in (0, 3, 6, 9, 12, 15) for p in ('projectile', 'blast', 'camera_idle')]
    changes = dict(caf_delta=0, flying=0, blast=0, shot=0, walk=0, debris=0)
    for i, profile in jobs:
        m = capture.restore(states[i])
        def ww(o, v):
            m.ds_write(o, struct.pack('<H', v & 65535))
        def wb(o, v):
            m.ds_write(o, bytes([v]))
        def rw(o):
            return m.rw(m.DATA_SEG, o)
        if profile != 'live':
            ww(0x11A0, 0)
            wb(0x11CA, 1 if profile == 'camera_idle' else 0)
            wb(0xAA83, 0)
            wb(0xAA98, 0)
            wb(0xB69F, 0)
            wb(0x115A, 0)
            wb(0x8684, 0)
            ww(0xB64C, 0xB520)
            ww(0xB826, 4)
            ww(0x50AC, 0)
            ww(0x020E, 0)
            actor = rw(0x03A0)
            ww(actor, 600)
            ww(actor+4, 700)
            ww(actor+10, 6)
            wb(actor+14, 1)
            ww(0x119A, 2)
            ww(0x119C, 1)
            ww(0x03A4, 0x0DF0+24)
            m.ds_write(0x0B30, bytes(66))
            m.ds_write(0x0DF0, bytes(36))
            m.ds_write(0x0DF0, struct.pack('<12H', 250, 0, 520, 0x4000, 0, 2, 780, 0, 620, 0x4000, 2, 2))
            ww(0x0B32, 320)
            ww(0x0B34, 560)
            ww(0x0B36, 40)
            ww(0x0B3A, 6)
            wb(0x0B46, 2)
            ww(0x0B4C, 128)
            ww(0x0B50, 6)
            m.wb(rw(0x91B2), 0, bytes(0x9000))
            ww(0x9948, 0x97B8)
            ww(0x994A, 0x9948)
            m.ds_write(0x97B8, struct.pack('<200H', *([1]*200)))
            # This real resident CAF frame is decoded before the world update, as in gameplay.
            clip = rw(0x7A8C + (i // 3)*2)
            initial = m.call(0, 0xC9A5, es=rw(0x91C6), si=clip, max_instr=50_000_000)
            ww(0x7A7E, initial['ax'] + 2)
            ww(0x117C, 6)
            wb(0x7AC6, 255)
            wb(0x7A3F, 0)
            m.ds_write(0x10F0, bytes(72))
            if profile != 'camera_idle':
                ww(0x11A0, 1)
                mode = 2 if profile == 'blast' else 0
                m.ds_write(0x10F0, struct.pack('<9H', 400 if mode else 800, 0, 700, 40, mode, 0, 0, 0, 65535))
            seg = rw(0x96DC)
            ww(0x117A, 2)
            m.wb(seg, 0, struct.pack('<18H', 40, 20, 50, 256, 0, 2, 120, 10, 200, 256, 1, 2, 0, 0, 0, 0, 0, 0))
            m.wb(seg, 0x0960, struct.pack('<20H', 1, 50, 0x9564, 2, 3, 4, 10, 0, 0, 0, 6, 60, 0x9565, 2, 3, 4, 10, 0, 0, 0))

        expected = []
        def track(uc, address, size, event):
            if event == 1:
                expected.append((1, m.ax() & 255))
            elif event == 5:
                expected.append((5, 4))
            else:
                expected.append((4, m.r(dosemu.UC_X86_REG_SI)))
        for seg, off, event, stub in ((0, 0x89A2, 1, 0xC3), (0, 0x6386, 5, None), (0x151B, 0x02DE, 4, 0xCB)):
            if stub is not None:
                m.wb(dosemu.LOAD_SEG + seg, off, bytes([stub]))
            at = base + 16*seg + off
            m.uc.hook_add(UC_HOOK_CODE, track, event, at, at)
        g, mem, planes = make_game(m)
        ctx.lib.game_events(buf, 128)
        set_clock(ctx.lib, m)
        status = ctx.lib.scene_update_world(ctypes.byref(g), None)
        if profile == 'live':
            capture.run_to_return(m, max_instr=50_000_000)
        else:
            m.call(0, 0x06EF, max_instr=50_000_000)
        CASES += 1
        label = f'world update {i}/{profile}'
        got = [(e.kind, e.a) for e in buf[:ctx.lib.game_events(buf, 128)]]
        if status or got != expected:
            return [f'{label}: status {status}, events {got} != {expected}']
        compare(label, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if profile != 'live':
            changes['caf_delta'] += rw(0x117C) == 5
            changes['flying'] += profile == 'projectile' and rw(0x10F0) != 800
            changes['blast'] += profile == 'blast' and rw(0x11A0) == 0
            changes['shot'] += rw(0xB64C) != 0xB520
            changes['walk'] += rw(0x0DFC) != 780
            changes['debris'] += rw(0x117A) == 1
    if not all(changes.values()):
        return [f'missing updates: {changes}']
    print('    combined world activity:', ', '.join(f'{k}={v}' for k, v in changes.items()))
    return fails
