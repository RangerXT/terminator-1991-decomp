"""draw_background against the original at 0000:06DE (ground colour 0000:159D, then the
horizon picture and sun 0000:16BE).

Captures: python tools/capture.py 0000:06DE background --count 8 --skip 5 --ticks 120 --keys "2:right:40,50:left:30"

Each recording is run with 64 headings round the circle (so the picture wraps at every
position and the sun crosses the view), with three ground colours, and in the other camera
mode. Compared: all conventional memory except the stack, and the four bit planes.
"""
import ctypes
import gzip
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from test_drawlist import compare, make_game  # noqa: E402
from test_polyfill import planes_of  # noqa: E402

CASES = 0


def variants():
    yield 'as recorded', lambda m: None
    for k in range(64):
        def turn(m, k=k):
            player = m.rw(m.DATA_SEG, 0x03A0)
            m.ds_write(player + 6, struct.pack('<H', (k * 8 + k % 7) & 0x1FF))
            m.ds_write(0x1533, bytes([(2, 6, 7)[k % 3]]))
        yield f'heading step {k}', turn
    for k in (3, 20, 41):
        def other(m, k=k):
            player = m.rw(m.DATA_SEG, 0x03A0)
            m.ds_write(player + 6, struct.pack('<H', k * 9))
            m.ds_write(0x11CA, b'\x02')
        yield f'other camera mode, heading {k * 9}', other


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.draw_background.restype = None
    fails = []
    states = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'background.pkl.gz'), 'rb'))
    suns = 0
    for n, st in enumerate(states):
        for label, change in variants():
            m = capture.restore(st)
            change(m)
            g, mem, planes = make_game(m)
            lib.draw_background(ctypes.byref(g))
            CASES += 1
            where = f'capture {n}, {label}'
            try:
                capture.run_to_return(m, max_instr=5_000_000)
            except Exception as e:
                fails.append(f'{where}: original: {e}')
                continue
            if compare(where, mem, planes, m, fails):
                column = m.ds_read(0x154D, 1)[0]
                suns += 1 if column and 0 <= 0x21 - column < 0x26 else 0
    print(f'    background: the sun was on screen in {suns} of {CASES} cases')
    for n, st in enumerate(states):
        for mode in range(3):
            for obscured in range(3):
                m = capture.restore(st)
                p = m.rw(m.DATA_SEG, 0x03A0)
                m.ds_write(0x11CA, bytes([mode]))
                m.ds_write(0x154C, bytes([(5*n + mode) % 16]))
                m.ds_write(0x1172, struct.pack('<H', int(obscured == 1)))
                m.ds_write(p+25, bytes([128 if obscured == 2 else 0]))
                g, mem, planes = make_game(m)
                lib.draw_frame_background(ctypes.byref(g))
                m.call(0, 0x06C3, max_instr=5_000_000)
                CASES += 1
                if not compare(f'frame background {n}/{mode}/{obscured}', mem, planes, m, fails):
                    return fails
    return fails
