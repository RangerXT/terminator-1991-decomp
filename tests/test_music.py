"""Starting and stopping the music (src/music.c) against the original 0000:8986, 899C, 8C52
and 8C64, for every combination of the flags they read (music on DS:0361, song loaded A615,
driver playing EA3C, device A773 = 0..5). The FM driver's calls (89F0, F472, F445, F4C1,
F205) are stubbed and recorded; compared: the calls with their argument, and all memory.
"""
import ctypes
import itertools
import os
import struct
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402

CASES = 0
DRIVER = (0x89F0, 0xF472, 0xF445, 0xF4C1, 0xF205)


def run(ctx):
    global CASES
    lib = ctx.lib
    for name in ('music_stop', 'music_start', 'music_close'):
        getattr(lib, name).restype = ctypes.c_int
    fails = []
    routines = [('music_start', 0x8986), ('music_stop', 0x8C52), ('music_close', 0x8C64), ('music_mark_ending', 0x899C)]
    for (name, address), wanted, loaded, playing, device in itertools.product(
            routines, (0, 1), (0, 0xFF), (0, 0xFF), range(6)):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0x0361, bytes([wanted]))
        m.ds_write(0xA615, bytes([loaded]))
        m.ds_write(0xEA3C, bytes([playing]))
        m.ds_write(0xA773, struct.pack('<H', device))
        original = []
        for off in DRIVER:
            m.wb(dosemu.LOAD_SEG, off, b'\xc3')
            at = (dosemu.LOAD_SEG << 4) + off
            m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, off=off: original.append((off, m.r(dosemu.UC_X86_REG_DX)
                                                                                   if off == 0x89F0 else 0)), None, at, at)
        g, mem, planes = make_game(m)
        native = []

        @RESOURCE
        def driver(gp, op, a, b, user):
            native.append((op, a))
            return 0

        host = Resources(driver, None)
        if name == 'music_mark_ending':
            lib.music_mark_ending(ctypes.c_void_p(g.ds))
            status = 0
        else:
            status = getattr(lib, name)(ctypes.byref(g), ctypes.byref(host))
        m.call(0, address)
        CASES += 1
        where = f'{name}: music {wanted}, loaded {loaded}, playing {playing}, device {device}'
        if status or native != original:
            return [f'{where}: status {status}, calls C {native}, original {original}']
        compare(where, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    return fails
