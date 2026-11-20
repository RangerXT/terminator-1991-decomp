"""AB77 and AEE9: live civilian frames, steering, and record removal."""
import ctypes
import gzip
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from test_blast import GameEvent
from test_drawlist import make_game
from test_imageload import compare, regions
from unicorn import UC_HOOK_CODE

CASES = 0
PROFILES = ('clear', 'pixels', 'turn', 'blocked', 'no_exit', 'flee',
            'vehicle', 'vehicle_slow', 'coarse_edge', 'fine_edge', 'respawn', 'gap')


def run(ctx):
    global CASES
    fails, branches = [], {}
    base = dosemu.LOAD_SEG << 4
    buf = (GameEvent * 32)()
    ctx.lib.civilian_prepare_move.restype = ctypes.c_uint8
    path = os.path.join(capture.CAPDIR, 'civilian_walk_live.pkl.gz')
    with gzip.open(path, 'rb') as f:
        states = pickle.load(f)
    jobs = [(i, 'live', False) for i in range(len(states))]
    jobs += [(i, profile, one) for i in (0, 5, 10, 15) for profile in PROFILES for one in (False, True)]
    for i, prof, one in jobs:
        m = capture.restore(states[i])
        def ww(o, v):
            m.ds_write(o, struct.pack('<H', v & 65535))
        def wb(o, v):
            m.ds_write(o, bytes([v]))
        def rw(o):
            return struct.unpack('<H', m.ds_read(o, 2))[0]
        if prof != 'live':
            entries = 4
            ww(0x119A, entries)
            ww(0x119C, entries - 1)
            ww(0x03A4, 0x0DF0 + 12*entries)
            ww(0xB82A, 0)
            wb(0xB6A1, i)
            wb(0xB66D, i % 3)
            wb(0x115A, 0)
            wb(0xB69F, 255 if prof in ('flee', 'fine_edge', 'coarse_edge') else 0)
            actor = rw(0x03A0)
            ww(actor, 160)
            ww(actor+4, 672)
            wb(actor+14, 2 if prof.startswith('vehicle') else 1)
            ww(actor+10, 4 if prof == 'vehicle_slow' else 5)
            m.ds_write(0x0B30, bytes(22*(entries+1)))
            m.ds_write(0x0DF0, bytes(12*(entries+1)))
            for j in range(entries):
                si, di = 0x0B30 + 22*j, 0x0DF0 + 12*j
                x = (160 if prof.startswith('vehicle') or prof == 'respawn' else 256) + 24*j
                z = 672 if prof.startswith('vehicle') or prof == 'respawn' else 512
                if not j and prof == 'coarse_edge':
                    x = -1056
                if not j and prof == 'fine_edge':
                    z = 2032
                wb(si, 0 if j == 2 else (2 if (i+j) % 2 else 4))
                ww(si+6, (48*i + 64*j) & 511)
                ww(si+10, 2 + (i+j) % 2)
                ww(di, x)
                ww(di+4, z)
                ww(di+6, 0 if prof == 'gap' and j == 0 else 0x4000)
                ww(di+8, j*2)
                ww(di+10, 2)
            seg = rw(0x91B2)
            m.wb(seg, 0, bytes([1 if prof == 'no_exit' else 0])*0x9000)
            row = lambda x, z: (0x9000 - (((z+8) >> 4)+64)*192 + (((x+8) >> 4)+64) - 0x182) & 65535
            origin = row(256, 512)
            if prof == 'turn':
                direction = ((rw(0x0B36)>>5) & 0xFFFE)
                m.wb(seg, (origin + rw(0xBA7A + direction)) & 65535, b'\x01')
            elif prof == 'blocked':
                m.wb(seg, origin, b'\x01')
            elif prof == 'no_exit':
                m.wb(seg, origin, b'\x00')
            elif prof == 'respawn':
                m.wb(seg, row(160, 672), b'\x01')
            m.vga.gc[5] = 0
            for p in range(4):
                m.vga.planes[p][0x6000:0x8000] = bytes([255 if p == 0 and prof == 'pixels' else 0])*8192
        m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xC3')
        seen, sounds = set(), []
        def track(uc, address, size, ud):
            if ud == 'sound':
                sounds.append((1, m.ax() & 255, m.ds_read(0x80E9, 1)[0]))
            else:
                seen.add(ud)
        hooks = ((0, 0x89A2, 'sound'), (0, 0xAF05, 'remove'), (0, 0xAF71, 'vehicle_hit'),
                 (0, 0xABCD, 'advance'), (0, 0xABD9, 'repeat_slot'), (0, 0xAD37, 'spawn'),
                 (0x14A7, 0x0030, 'pixel_turn'), (0x14A7, 0x0085, 'grid_turn'),
                 (0x14A7, 0x0095, 'grid_exhausted'), (0x14A7, 0x00D9, 'fine_boundary'))
        for seg, off, tag in hooks:
            a = base + 16*seg + off
            m.uc.hook_add(UC_HOOK_CODE, track, tag, a, a)
        g, mem, planes = make_game(m)
        ctx.lib.game_events(buf, 32)
        if one:
            cf = ctx.lib.civilian_prepare_move(ctypes.byref(g), 0x0B30, 0x0DF0)
            out = m.call(0, 0xAEE9, si=0x0B30, di=0x0DF0, max_instr=50_000_000)
        else:
            ctx.lib.civilians_move(ctypes.byref(g))
            if prof == 'live':
                capture.run_to_return(m)
            else:
                m.call(0, 0xAB77, max_instr=50_000_000)
        CASES += 1
        label = f'civilian {i}/{prof}/{"prepare" if one else "loop"}'
        if one and cf != out['flags'] & 1:
            return [f'{label}: carry {cf} != {out["flags"] & 1}']
        got = [(e.kind, e.a, e.b) for e in buf[:ctx.lib.game_events(buf, 32)]]
        if got != sounds:
            return [f'{label}: sound {got} != {sounds}']
        compare(label, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        for action in seen:
            branches[action] = branches.get(action, 0) + 1
    required = {tag for _, _, tag in hooks if tag != 'sound'}
    if missing := required - branches.keys():
        return [f'missing branches: {sorted(missing)}']
    print('    civilian branches: ' + ', '.join(f'{k}={v}' for k, v in sorted(branches.items())))
    return fails
