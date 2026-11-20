"""Complete 0758 replays including guided projectiles with inherited DX."""
import ctypes
import gzip
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from unicorn import UC_HOOK_CODE
from test_blast import GameEvent, set_clock
from test_drawlist import make_game
from test_hudcompose import HudCall, HudServices
from test_imageload import Files, compare, regions

CASES = 0


def run(ctx):
    global CASES
    ctx.lib.image_hud_service.restype = ctypes.c_uint32
    ctx.lib.image_hud_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    ctx.lib.scene_post_render.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint16]
    with gzip.open(os.path.join(capture.CAPDIR, 'scene_post_render_live.pkl.gz'), 'rb') as f:
        states = pickle.load(f)
    fails, inherited = [], set()
    fired = 0
    buf = (GameEvent * 512)()
    for i, st in enumerate(states):
        profiles = ('live', 'bearing', 'held', 'far', 'flash', 'warning', 'system') if i % 3 == 0 else ('live',)
        for profile in profiles:
            m = capture.restore(st)
            def wb(off, value):
                m.ds_write(off, bytes([value]))
            def ww(off, value):
                m.ds_write(off, struct.pack('<H', value & 65535))
            def rw(off):
                return m.rw(m.DATA_SEG, off)
            if profile != 'live':
                # Keep real art and HUD state. Arm the original weapon record and
                # choose overlay branches that produce different DX values.
                actor = 0x0508 if profile == 'system' else rw(0x03A0)
                ww(0x03A0, actor)
                wb(actor + 14, 1)
                wb(actor + 25, 0)
                for off in (0x8096, 0x1160, 0xAA83, 0x0366, 0x8161, 0x114F, 0x5C09, 0x00B9, 0x00BA, 0x1153, 0x1154, 0x5BE6):
                    wb(off, 0)
                wb(0x11CA, 0 if profile == 'system' else 2)
                wb(0x114E, 0)
                wb(0x0345, profile not in ('bearing', 'system'))
                wb(0x115D, 255)
                wb(0x0364, 15)
                wb(0x5BE8, 1)
                wb(0x0361, 1)
                m.ds_write(0x570, bytes([0, 0, 0, 3, 0, 10]))
                ww(0x04D0, 0)
                ww(0x0418, 0)
                ww(0x118E, 1)
                ww(0x119A, 2)
                ww(0x119C, 0)
                ww(0x11A0, 0)
                ww(0x0B2E, int(profile in ('far', 'flash')))
                if profile in ('far', 'flash'):
                    ww(0x0404, rw(actor) + (300 if profile == 'far' else 0))
                    ww(0x0406, rw(actor + 4))
                if profile == 'warning':
                    wb(0x00B9, 255)
            incoming = m.r(dosemu.UC_X86_REG_DX) if profile == 'live' else 0x4012 + i
            m.w(dosemu.UC_X86_REG_DX, incoming)
            original_events, actual_dx = [], []
            base = dosemu.LOAD_SEG << 4
            m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
            def trace(uc, address, size, ud):
                if address == base + 0x89A2:
                    original_events.append((1, m.ax() & 255, m.ds_read(0x80E9, 1)[0]))
                else:
                    actual_dx.append(m.r(dosemu.UC_X86_REG_DX))
            for off in (0x89A2, 0x07B0):
                m.uc.hook_add(UC_HOOK_CODE, trace, None, base + off, base + off)
            g, mem, planes = make_game(m)
            prior = rw(0x0378)
            files = Files(m, record=False)
            @HudCall
            def hud_service(gp, op, arg, user):
                return ctx.lib.image_hud_service(gp, op, arg, ctypes.byref(files.host))
            host = HudServices(hud_service, None)
            ctx.lib.game_events(buf, 512)
            set_clock(ctx.lib, m)
            status = ctx.lib.scene_post_render(ctypes.byref(g), ctypes.byref(host), incoming)
            capture.run_to_return(m, max_instr=100_000_000)
            CASES += 1
            label = f'post-render {i}/{profile}'
            n = ctx.lib.game_events(buf, 512)
            events = [(e.kind, e.a, e.b) for e in buf[:n]]
            if status or files.handles or original_events != events:
                return [f'{label}: status {status}, event or handle mismatch: {events} vs {original_events}']
            compare(label, mem, planes, m, regions(m), fails)
            if fails:
                return [f'{fails[0]} (weapon DX={actual_dx}; incoming={incoming:04x})']
            if profile != 'live':
                if rw(0x11A0) != 1 or rw(0x0378) != (prior + 1) & 65535:
                    return [f'{label}: guided shot was not launched']
                inherited.update(actual_dx)
                fired += 1
    if fired != 48 or len(inherited) < 3:
        return [f'missing guided coverage: {fired} launches, DX values {inherited}']
    print(f'    post-render: {len(states)} live entries, {fired} guided shots, {len(inherited)} distinct DX values')
    return fails
