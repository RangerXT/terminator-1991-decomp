"""select_pages (src/scenepresent.c) against the original page selection 0000:0C6B.

From the in-game snapshot: AX = page to draw << 8 | page to show, for pages 0..3 and
random words, with the 320- and 640-wide strides, one-page mode (DS:1534) and a facility
screen (nothing happens). The BIOS page call goes to a second emulator on the C side, as in
tests/test_scenepresent.py. Compared: the calls, all memory, the displayed start address.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.select_pages.restype = ctypes.c_int
    fails = []
    rng = random.Random(0x0C6B)
    values = [shown | drawn << 8 for shown in range(4) for drawn in range(4)] + [rng.randrange(0x10000) for _ in range(16)]
    for profile in ('narrow', 'wide', 'single', 'facility'):
        for ax in values:
            m = dosemu.Machine()
            m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
            if profile == 'wide':
                m.ds_write(0x9A72, struct.pack('<H', 80))
            m.ds_write(0x1534, b'\xff' if profile == 'single' else b'\0')
            m.ds_write(0xADCF, b'\x01' if profile == 'facility' else b'\0')
            g, mem, planes = make_game(m)
            vm = dosemu.Machine()
            vm.vga.mode = m.vga.mode
            vm.vga.crtc[:] = m.vga.crtc[:]
            calls = []

            @RESOURCE
            def service(gp, op, a, b, user):
                calls.append((op, a))
                if op == 0xFF05:
                    vm.w(dosemu.UC_X86_REG_AX, 0x0500 | a)
                    vm._video()
                    ctypes.c_uint8.from_address(g.mem + 0x462).value = vm.rb(0x40, 0x62, 1)[0]
                return 0

            host = Resources(service, None)
            status = lib.select_pages(ctypes.byref(g), ctypes.byref(host), ax)
            m.call(0, 0x0C6B, ax=ax)
            CASES += 1
            label = f'{profile} AX {ax:04X}'
            if status:
                return [f'{label}: status {status}']
            if profile == 'facility' and calls:
                return [f'{label}: a page call on the facility screen']
            if vm.vga.crtc != m.vga.crtc and profile != 'facility':
                return [f'{label}: the displayed start address differs']
            compare(label, mem, planes, m, regions(m), fails)
            if fails:
                return fails
    return fails
