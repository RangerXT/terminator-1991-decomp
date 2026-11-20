"""A54E and ABF1 against the original: movement, pursuit and fire."""
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
WALKS = ('none', 'attack', 'cooldown', 'pursue', 'choose_cover', 'choose_failed',
         'blind_foot', 'blind_car', 'car_in', 'car_out', 'reached', 'boundary')
SHOTS = ('fire', 'miss', 'under_armour', 'armour_break', 'skip', 'cooldown',
         'car_hit', 'car_no_hit', 'far')


def run(ctx):
    global CASES
    fails, branches = [], {}
    base = dosemu.LOAD_SEG << 4
    buf = (GameEvent * 32)()
    ctx.lib.armed_figure_fire.restype = ctypes.c_uint8
    path = os.path.join(capture.CAPDIR, 'armed_figure_live.pkl.gz')
    with gzip.open(path, 'rb') as f:
        states = pickle.load(f)
    jobs = [(i, 'live', False) for i in range(len(states))]
    jobs += [(i, prof, one) for i in (0, 3, 6, 9, 12, 15) for one, group in ((False, WALKS), (True, SHOTS)) for prof in group]
    for i, prof, one in jobs:
        m = capture.restore(states[i])
        def ww(o, v):
            m.ds_write(o, struct.pack('<H', v & 65535))
        def wb(o, v):
            m.ds_write(o, bytes([v]))
        def rw(o):
            return struct.unpack('<H', m.ds_read(o, 2))[0]
        si, di = 0x0B30, 0x0DF0
        if prof != 'live':
            entries = 0 if prof == 'none' else (3 if prof == 'boundary' else 1)
            ww(0x119A, entries)
            ww(0x119C, max(0, entries-1))
            ww(0x03A4, di+12*entries)
            wb(0xB66D, (i // 3) % 3)
            wb(0xAA83, 255 if prof == 'skip' else 0)
            wb(0xAA98, 255 if prof in ('under_armour', 'armour_break') else 0)
            wb(0x11CD, i & 1)
            wb(0x8684, 0)
            wb(0xB735, 0)
            ww(0xB64C, 0xB520 if i % 2 else 0xB642)
            ww(0xB65E, i % 3)
            ww(0xB826, 15)
            actor = rw(0x03A0)
            ww(actor+0, 900)
            ww(actor+4, 600)
            ww(actor+6, (i * 30) & 511)
            ww(actor+10, [0, 3, 10][(i // 3) % 3])
            car = prof in ('car_in', 'blind_car', 'car_hit', 'car_no_hit')
            wb(actor+14, 2 if car else 1)
            ww(actor+26, 0)
            ww(actor+28, 900)
            ww(actor+48, 700)
            wb(actor+51, 1 if prof == 'armour_break' else 12)
            m.ds_write(si, bytes(22*(entries+1)))
            m.ds_write(di, bytes(12*(entries+1)))
            wb(si, 16 if prof in ('blind_car', 'car_out') else 0)
            if prof == 'boundary':
                wb(si+22, 2)
                wb(si+44, 4)
                for j in (1, 2):
                    ww(di+12*j, 120*j)
                    ww(di+12*j+4, 130*j)
                    ww(di+12*j+6, 0x4000)
                    ww(di+12*j+8, j*2)
            x = -1100 if prof == 'boundary' else [800, 350, 100][(i//3)%3]
            ww(di, x)
            ww(di+4, 600)
            ww(di+6, 0x4000)
            ww(si+2, x + (5 if prof == 'reached' else 160))
            ww(si+4, 600 + (5 if prof == 'reached' else 140))
            ww(si+6, (i * 18) & 511)
            ww(si+8, 3501 if prof == 'far' else 200)
            ww(si+10, 3 if i % 2 else 10)
            ww(si+12, 3 if prof == 'cooldown' else 0)
            wb(si+1, 20 if prof == 'pursue' else 0)
            seg = rw(0x91B2)
            m.wb(seg, 0, bytes([255 if prof in ('blind_foot', 'blind_car', 'car_in') else 0])*0x9000)
            wanted = 1 if prof == 'choose_cover' else 0
            m.ds_write(0xB740, bytes([wanted])*144)
            ww(0x9948, 0x97B8)
            ww(0x994A, 0x9948)
            initial = 0x9000 if prof == 'car_hit' else 0xFFF0 if prof == 'miss' else 1
            if prof in ('choose_cover', 'choose_failed', 'reached'):
                # Skip body damage and let the next word select the cover branch.
                initial = 0xFFFF
                ww(actor, 2000)
                ww(actor+4, 1800)
            random_words = [initial, 0x1F if prof in ('choose_cover', 'choose_failed', 'reached') else 1, 3, 1] * 30
            m.ds_write(0x97B8, struct.pack('<120H', *random_words))

        m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xC3')
        seen, expected = set(), []
        def track(uc, address, size, ud):
            if ud == 'sound':
                expected.append((1, m.ax() & 255, m.ds_read(0x80E9, 1)[0]))
            elif ud == 'hit':
                seen.add(ud)
                expected.append((5, 4, m.ds_read(0x1514, 1)[0]))
            else:
                seen.add(ud)
        hooks = ((0x89A2, 'sound'), (0x6386, 'hit'), (0xA5E5, 'found_cover'),
                 (0xA630, 'vehicle_search'), (0xA63B, 'foot_search'), (0xA641, 'retirement'),
                 (0xA681, 'move'), (0xA727, 'enter_body'), (0xA758, 'exit_body'),
                 (0xA6E8, 'reached'), (0xAC02, 'cooldown'), (0xAC25, 'vehicle_hit'),
                 (0xAC63, 'armour_break'), (0xACD6, 'shot'))
        for off, tag in hooks:
            m.uc.hook_add(UC_HOOK_CODE, track, tag, base+off, base+off)
        g, mem, planes = make_game(m)
        ctx.lib.game_events(buf, 32)
        set_clock(ctx.lib, m)
        if one:
            cf = ctx.lib.armed_figure_fire(ctypes.byref(g), si, di)
            out = m.call(0, 0xABF1, si=si, di=di)
        else:
            ctx.lib.armed_figures_move(ctypes.byref(g))
            if prof == 'live':
                capture.run_to_return(m)
            else:
                m.call(0, 0xA54E)
        CASES += 1
        label = f'armed figure {i}/{prof}/{"fire" if one else "loop"}'
        if one and cf != out['flags'] & 1:
            return [f'{label}: carry {cf} != {out["flags"] & 1}']
        got = [(e.kind, e.a, e.b) for e in buf[:ctx.lib.game_events(buf, 32)]]
        if got != expected:
            return [f'{label}: events {got} != {expected}']
        compare(label, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        for action in seen:
            branches[action] = branches.get(action, 0) + 1
    required = {tag for _, tag in hooks if tag != 'sound'}
    if missing := required - branches.keys():
        return [f'missing branches: {sorted(missing)}']
    print('    armed branches: ' + ', '.join(f'{k}={v}' for k, v in sorted(branches.items())))
    return fails
