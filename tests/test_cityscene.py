"""One uninterrupted native pass from the live city state to the rendered 3D scene."""
import ctypes
import gzip
import os
import pickle
import sys

from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from test_blast import GameEvent, set_clock
from test_drawlist import make_game
from test_imageload import Files, compare, regions
from test_vehicletransition import VehicleServices

CASES = 0


def run_original(m):
    # These entries are the first call from 01DC. Return normally and then
    # follow the untouched loop to the instruction immediately before the HUD.
    capture.run_to_return(m, max_instr=100_000_000)
    if (m.cs, m.ip) != (dosemu.LOAD_SEG, 0x01DF):
        raise RuntimeError(f'unexpected caller: {m.file_addr()}')
    until = (dosemu.LOAD_SEG<<4)+0x01F1
    for _ in range(120):
        m.step(until, 1_000_000)
        if m.pending is not None:
            m._apply_pending()
            if m.blocked:
                raise RuntimeError(m.blocked)
        elif (m.cs, m.ip) == (dosemu.LOAD_SEG, 0x01F1):
            return
    raise RuntimeError(f'scene did not reach HUD: {m.file_addr()}')


def run(ctx):
    global CASES
    CASES = 0
    errors = []
    with gzip.open(os.path.join(capture.CAPDIR, 'cell_window_live.pkl.gz'), 'rb') as f:
        states = pickle.load(f)
    jobs = [(i, 'live', None) for i in range(len(states))]
    jobs += [(i, 'turn', None) for i in range(0, len(states), 2)]
    tiles = ((20, 20), (84, 20), (148, 20), (20, 84), (84, 84), (148, 84), (64, 64), (128, 64))
    jobs += [(i, 'reload', xy) for i, xy in enumerate(tiles)]
    events = (GameEvent*512)()
    changed = 0
    for i, kind, xy in jobs:
        m = capture.restore(states[i])
        ds = m.DATA_SEG
        actor = m.rw(ds, 0x03A0)
        if kind == 'turn':
            m.ww(ds, actor+6, (m.rw(ds, actor+6)+64)&511)
        if kind == 'reload':
            x, z = xy
            # Keep both the world and local coordinates consistent.
            m.ww(ds, actor+30, x); m.ww(ds, actor+32, z)
            m.wb(ds, actor+34, (x*1024+m.rw(ds, actor)).to_bytes(4, 'little'))
            m.wb(ds, actor+42, ((z+1)*1024-m.rw(ds, actor+4)).to_bytes(4, 'little'))
            m.ww(ds, 0x7242, 65535)
            m.ww(ds, 0x9120, 65535)  # first collision visit remembers the new position
        expected = []
        def sound(uc, address, size, user):
            expected.append((1, m.ax()&255, m.ds_read(0x80E9, 1)[0]))
        m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
        at = (dosemu.LOAD_SEG<<4)+0x89A2
        m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        host = VehicleServices()
        host.images = ctypes.pointer(files.host)
        original_planes = planes.raw
        set_clock(ctx.lib, m)
        ctx.lib.game_events(events, 512)
        status = ctx.lib.scene_render_city(ctypes.byref(g), ctypes.byref(host))
        run_original(m)
        CASES += 1
        got = [(e.kind, e.a, e.b) for e in events[:ctx.lib.game_events(events, 512)]]
        label = f'city scene {i}/{kind} {xy}'
        if status or files.handles or files.next_handle != m.next_handle or got != expected:
            return [f'{label}: status {status}, events {got}/{expected}, handles {files.next_handle}/{m.next_handle}']
        compare(label, mem, planes, m, regions(m), errors)
        if errors:
            return errors
        changed += planes.raw != original_planes
    print(f'    joined city scenes: {len(jobs)} compared, {changed} changed display state')
    return [] if changed else ['no display activity']
