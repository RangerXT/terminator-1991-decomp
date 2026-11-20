"""17E6 live page flips with BIOS/video state checked on both sides."""
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
from test_drawlist import make_game
from test_imageload import compare, regions
from test_mapsetupreal import RESOURCE, Resources

CASES = 0


def run(ctx):
    global CASES
    fails = []
    with gzip.open(os.path.join(capture.CAPDIR, 'scene_present_live.pkl.gz'), 'rb') as f:
        states = pickle.load(f)
    for i, st in enumerate(states):
        for profile in ('live', 'wide', 'single'):
            m = capture.restore(st)
            if profile == 'wide':
                m.ds_write(0x9A72, struct.pack('<H', 80))
                m.vga.set_mode(0x0E, clear=False)
            elif profile == 'single':
                m.ds_write(0x1534, bytes([255]))
                m.vga.set_mode(0x13, clear=False)
            g, mem, planes = make_game(m)
            vm = dosemu.Machine()
            vm.vga.mode = m.vga.mode
            vm.vga.crtc[:] = m.vga.crtc[:]
            original, native = [], []
            start = dosemu.LOAD_SEG << 4

            def snap(ds):
                return tuple(ds(x) for x in (0x122A, 0x122C, 0x1234, 0x1236))

            def trace(uc, address, size, ud):
                rel = address - start
                value = m.ax() & 255 if rel in (0x0C89, 0x0CB9) else 0
                op = 0xFF05 if rel in (0x0C89, 0x0CB9) else rel
                original.append((op, value, snap(lambda x: m.rw(m.DATA_SEG, x))))

            for off in (0x0D8D, 0x0C89, 0x0CB9, 0x0DAA):
                m.uc.hook_add(UC_HOOK_CODE, trace, None, start + off, start + off)
            # Isolated calls stop the real-time driver. Model successive retrace
            # phases at the VGA port, so the original wait loops still execute.
            phases = iter((dosemu.FRAME_INSTR // 2, 0, 0, dosemu.FRAME_INSTR // 2))
            m.vga.clock = phases.__next__

            @RESOURCE
            def service(gp, op, a, b, user):
                native.append((op, a, snap(lambda x: ctypes.c_uint16.from_address(g.ds + x).value)))
                if op == 0xFF05:
                    vm.w(dosemu.UC_X86_REG_AX, 0x0500 | a)
                    vm._video()
                    ctypes.c_uint8.from_address(g.mem + 0x462).value = vm.rb(0x40, 0x62, 1)[0]
                return 0

            host = Resources(service, None)
            status = ctx.lib.scene_present(ctypes.byref(g), ctypes.byref(host))
            capture.run_to_return(m)
            CASES += 1
            label = f'page flip {i}/{profile}'
            if status or original != native or [o[0] for o in native] != [0x0D8D, 0xFF05, 0x0DAA]:
                return [f'{label}: display call order or page state differs: {native} vs {original}']
            if vm.vga.crtc != m.vga.crtc:
                return [f'{label}: displayed start address differs']
            compare(label, mem, planes, m, regions(m), fails)
            if fails:
                return fails
    return fails
