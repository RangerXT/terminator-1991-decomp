"""Actual weapons.cif load and eight-record indexing against DOS."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, trace_dos, regions, compare, check_memory
CASES = 0

def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    spans = regions(m)
    trace_dos(m)
    for offset in [0, 2, 256, 4096]:
        m.ds_write(0, saved)
        m.ds_write(0x80F0, struct.pack('<HH', offset, 0x7800))
        g, mem, planes = make_game(m)
        files = Files(m)
        m.image_calls.clear()
        status = ctx.lib.weapon_images_load(ctypes.byref(g), ctypes.byref(files.host))
        m.call(0, 0x6B23)
        CASES += 1
        if status or len(files.calls) != len(m.image_calls):
            return ['weapon load status/IO count']
        for c, o in zip(files.calls, m.image_calls):
            if c[0] != o[0]:
                return ['weapon load DOS inputs']
            error = check_memory(c[1], o[1], spans)
            if error:
                return ['weapon load DOS boundary: '+error]
        compare('weapon assets offset %d'%offset, mem, planes, m, spans, fails)
        if fails:
            return fails
    return fails
