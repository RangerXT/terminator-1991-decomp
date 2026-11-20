"""Complete system HUD and target presentation; bitmap IO/sound are explicit stubs; the target query runs unmodified.

The original and C must reach service calls with the same entire DS, request the same
sounds, and finish with identical conventional memory and EGA planes/registers.
Twelve captured real E170 inputs complement the forced branch configurations.
"""
import ctypes
import gzip
import os
import pickle
import struct
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import Game, make_game, compare
from test_blast import c_events
import capture
import dosemu

CASES = 0
HudCall = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(Game), ctypes.c_uint16,
                          ctypes.c_uint16, ctypes.c_void_p)


class HudServices(ctypes.Structure):
    _fields_ = [('call', HudCall), ('user', ctypes.c_void_p)]


def stub(m):
    m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xc3')
    m.wb(dosemu.LOAD_SEG, 0x6962, b'\xc3')
    m.external, m.sounds = [], []
    def external(uc, address, size, service):
        arg = uc.reg_read(dosemu.UC_X86_REG_DX) if service == 0x6962 else 0
        m.external.append((service, arg, m.ds_read(0, 0xEA70)))
    for service in [0x6962]:
        at = (dosemu.LOAD_SEG << 4) + service
        m.uc.hook_add(UC_HOOK_CODE, external, service, at, at)
    def sound(uc, address, size, ud):
        m.sounds.append((1, uc.reg_read(dosemu.UC_X86_REG_AX) & 255))
    at = (dosemu.LOAD_SEG << 4) + 0x89A2
    m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)


def configure(m, saved, i):
    m.ds_write(0, saved)
    def byte(off, value):
        m.ds_write(off, bytes([value & 255]))
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    word(0x1234, (i % 3) * 0x2000)
    word(0xE170, 0)
    word(0xE172, 3)
    byte(0xE16A, i % 16)
    word(0xE56C, 0x8200)
    word(0x8200, 0x8100)
    word(0x0418, 0 if i % 17 == 0 else 0x8100)
    word(0x8106, [0, 4, 0x20, 0x4000, 0x2000, 0x24, 0x4004, 0x4020][i % 8])
    word(0x8108, 2 * (i % 10))
    count = [0, 1, 2, 4][i % 4]
    word(0xB64E, count)
    for j in range(count):
        m.ds_write(0xB18E + j * 18, struct.pack('<9H', 0x8100, 0, [16, 96, 512][(i + j) % 3],
                                               8 if (i + j) % 3 else 200, 311, 8, 110, 0, 0))
    for off, value in [(0x1140, (i // 2) % 2), (0x115D, (i // 4) % 2),
                       (0x118E, (i // 8) % 3), (0xE4FD, [0, 1, 2, 3][(i // 24) % 4]),
                       (0x113F, [0, 1, 30][(i // 96) % 3]), (0xB512, (i // 288) % 2),
                       (0x0364, 12 if i % 3 else 0), (0x114D, i & 1),
                       (0x1155, (i // 2) & 1), (0x115A, (i // 3) & 1),
                       (0x5BE6, i & 1), (0x5C0F, (i // 2) & 1),
                       (0xE434, (i // 4) & 1), (0x114E, (i // 8) & 1),
                       (0x1142, (i // 16) & 1), (0x1150, (i // 32) & 1),
                       (0x5C05, (i // 4) & 1), (0xE4FC, (i // 8) & 1),
                       (0xE435, i % 8), (0xE436, (i // 8) % 3),
                       (0xE437, [0, 1, 2, 255][i % 4]), (0xE438, i % 6),
                       (0xE482, i % 7), (0xE483, 1 + i % 5)]: byte(off, value)
    word(0xE439, 0xE43B + (i // 8) % 3)
    player = m.rw(m.DATA_SEG, 0x03A0)
    for field in [0, 2, 4, 6, 0x1A, 0x1C, 0x1E, 0x20]:
        word(player + field, (i * (field + 7)) & 511)
    byte(player + 0x19, (i // 3) & 1)
    for record in [0xE59C, 0xE5A8, 0xE5B4, 0xE5C0, 0xE5CC, 0xE5E4, 0xE5F0]:
        byte(record, 1 + i % 2)
        byte(record + 2, (i // 2) & 1)


def pair(ctx, m, name, offset, fails):
    global CASES
    mine = []
    @HudCall
    def call(g, service, arg, user):
        mine.append((service, arg, ctypes.string_at(g.contents.ds, 0xEA70)))
        return 0
    host = HudServices(call, None)
    g, mem, planes = make_game(m)
    c_events(ctx.lib)
    m.external.clear()
    m.sounds.clear()
    fn = getattr(ctx.lib, name)
    if name in ['hud_draw_system', 'hud_draw_warnings', 'hud_draw_target', 'hud_refresh_pages']:
        result = fn(ctypes.byref(g), ctypes.byref(host))
        if result:
            return fails.append(f'{name}: C returned {result}')
    else:
        fn(ctypes.byref(g))
    events = c_events(ctx.lib)
    m.call(0, offset)
    CASES += 1
    if events != m.sounds:
        fails.append(f'{name}: sound requests differ')
    if mine != m.external:
        fails.append(f'{name}: external service entry state differs')
    compare(name, mem, planes, m, fails)


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    stub(m)
    for name, offset, count in [('hud_clear_target_info', 0xE813, 24),
                                ('hud_draw_target_info', 0xE6E0, 136),
                                ('hud_draw_target_frame', 0xE542, 24),
                                ('hud_refresh_pages', 0x4FE5, 9),
                                ('hud_draw_target', 0xE4AE, 1152),
                                ('hud_draw_warnings', 0xE5E9, 192),
                                ('hud_draw_system', 0xE170, 384)]:
        for i in range(count):
            configure(m, saved, i)
            if name == 'hud_draw_system':
                m.ds_write(0x11CA, bytes([1 if i % 19 == 0 else 0]))
                if i % 23 == 0:
                    m.ds_write(0x03A0, struct.pack('<H', 0x04D4))
            pair(ctx, m, name, offset, fails)
            if fails:
                return fails
    path = os.path.join(capture.CAPDIR, 'systemhud.pkl.gz')
    caps = pickle.load(gzip.open(path, 'rb'))
    for st in caps:
        m = capture.restore(st)
        stub(m)
        # Use the real entry's stack/return address rather than a synthetic call.
        mine = []
        @HudCall
        def call(g, service, arg, user):
            mine.append((service, arg, ctypes.string_at(g.contents.ds, 0xEA70)))
            return 0
        host = HudServices(call, None)
        g, mem, planes = make_game(m)
        c_events(ctx.lib)
        result = ctx.lib.hud_draw_system(ctypes.byref(g), ctypes.byref(host))
        events = c_events(ctx.lib)
        capture.run_to_return(m)
        CASES += 1
        if result or events != m.sounds or mine != m.external:
            return ['real-input HUD: service/results differ']
        compare('real-input HUD', mem, planes, m, fails)
        if fails:
            return fails
    print(f'    system HUD: {len(caps)} real entry states; IO/sound bodies stubbed, target query native')
    return fails
