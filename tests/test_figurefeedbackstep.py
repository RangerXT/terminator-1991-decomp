"""5C40: each installed CAF vignette's six deltas, persistence, and expiry."""
import ctypes
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare

CASES = 0


def run(ctx):
    global CASES
    failures = []
    for clip in range(11):
        for first_page in range(3):
            m = dosemu.Machine()
            m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))

            def ww(off, value):
                m.ds_write(off, struct.pack('<H', value))
            def wb(off, value):
                m.ds_write(off, bytes([value]))

            actor = m.rw(m.DATA_SEG, 0x03A0)
            wb(actor + 14, 1)
            wb(0x11CA, 0)
            ww(0x1234, first_page * 0x2000)
            source = m.rw(m.DATA_SEG, 0x7A8C + clip*2)
            seg = m.rw(m.DATA_SEG, 0x91C6)
            initial = m.call(0, 0xC9A5, es=seg, si=source, max_instr=50_000_000)
            ww(0x7A7E, initial['ax'] + 2)
            ww(0x117C, 6)
            wb(0x7AC6, 255)
            for step in range(10):
                ww(0x1234, ((first_page + step) % 3) * 0x2000)
                if step == 0:
                    wb(actor + 14, 2)
                if step == 1:
                    wb(actor + 14, 1)
                    wb(0x7A3F, 1)
                if step == 2:
                    wb(0x7A3F, 0)
                if step == 8:
                    if m.rw(m.DATA_SEG, 0x117C) or m.ds_read(0x7A3E, 1) != bytes([150]):
                        return [f'CAF {clip}: the sixth delta did not set a 150-frame hold']
                    wb(0x7A3E, 2)
                g, mem, planes = make_game(m)
                ctx.lib.figure_feedback_step(ctypes.byref(g))
                m.call(0, 0x5C40, es=m.DATA_SEG, max_instr=50_000_000)
                CASES += 1
                compare(f'CAF {clip}, page {first_page}, step {step}', mem, planes, m, failures)
                if failures:
                    return failures
    return failures
