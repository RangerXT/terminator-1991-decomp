"""Binocular/scope toggle and drawing against original; loader is an explicit stub."""
import ctypes
import os
import struct
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
from test_hudcompose import HudCall, HudServices
import dosemu

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    m.wb(dosemu.LOAD_SEG, 0xFACE, b'\xc3')
    images = {off: open(os.path.join(dosemu.ROOT, 'data/common', name), 'rb').read()
              for off, name in [(0x814B, 'BINOS.IMG'), (0x8155, 'SCOPES.IMG')]}
    original = []
    def loaded(uc, address, size, ud):
        original.append((uc.reg_read(dosemu.UC_X86_REG_DX), m.ds_read(0, 0xEA70)))
    at = (dosemu.LOAD_SEG << 4) + 0xFACE
    m.uc.hook_add(UC_HOOK_CODE, loaded, None, at, at)
    for name, entry, count in [('hud_load_optics', 0x766A, 6),
                                ('hud_init_optics', 0x7683, 12),
                                ('hud_draw_optics', 0x76B4, 256)]:
        for i in range(count):
            m.ds_write(0, saved)
            # Both masks have 38-byte rows and are raw image files.
            scope = (i >> 5) & 1
            m.wb(0x8000, 0, images[0x8155 if scope else 0x814B])
            m.ds_write(0x91C0, struct.pack('<HH', 0, 0x8000))
            flags = [(0x8161, i & 1), (0x5C09, (i >> 1) & 1),
                     (0x812A, (i >> 2) & 1), (0xAAA0, (i >> 3) & 1),
                     (0x114F, 255 if i & 16 else 0), (0x1150, scope)]
            if name != 'hud_draw_optics':
                flags[-1] = (0x1150, 255 if i & 1 else 0)
            for off, value in flags:
                m.ds_write(off, bytes([value]))
            m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
            m.ds_write(0x0408, struct.pack('<HH', [0, 160, 65535][i % 3], 60 + i % 3))
            mine = []
            @HudCall
            def load(gp, service, arg, user):
                mine.append((arg, ctypes.string_at(gp.contents.ds, 0xEA70)))
                if service != 0xFACE:
                    fails.append('optics requested wrong service')
                return 0
            host = HudServices(load, None)
            g, mem, planes = make_game(m)
            original.clear()
            result = getattr(ctx.lib, name)(ctypes.byref(g), ctypes.byref(host))
            m.call(0, entry)
            CASES += 1
            if result or mine != original:
                fails.append(f'{name} {i}: loader boundary differs')
            compare(f'{name} {i}', mem, planes, m, fails)
            if fails:
                return fails
    return fails
