"""sort_draw_list against recorded calls of the original at 15AD:0006: the frame's object
records are culled and put in drawing order.

Captures: python tools/capture.py 15AD:0006 sortlist --count 24 --skip 1 --ticks 120 --keys "2:right:12,18:up:15,40:left:10,60:up:20"
          python tools/capture.py 15AD:0006 sortlist2 --count 12 --skip 1 --ticks 60 --from ingame_walked --keys "2:left:14,20:up:20"

Each recording is also run with the game's detail setting at 1 and 2, with the zooms on,
with some records turned into cut-out figures, and with the player turned to eight other
headings (which changes what is visible and what hides what).
Compared: all conventional memory except the stack, and the returned list pointer.
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

CASES = 0


def variants():
    yield 'as recorded', lambda m: None
    yield 'detail 1', lambda m: m.ds_write(0xABCA, struct.pack('<H', 1))
    yield 'detail 2', lambda m: m.ds_write(0xABCA, struct.pack('<H', 2))
    yield 'zoom', lambda m: m.ds_write(0x114D, b'\xff')
    yield 'both zooms', lambda m: (m.ds_write(0x114D, b'\xff'), m.ds_write(0x114F, b'\xff'))

    def figures(m):
        count = m.rw(m.DATA_SEG, 0x50AC)
        for i in range(0, count, 3):
            rec = 0x1576 + 12 * i
            m.ds_write(rec + 6, struct.pack('<HH', 0x4000, 2 * (i % 10)))
    yield 'figures', figures
    for k in range(8):
        def turn(m, k=k):
            player = m.rw(m.DATA_SEG, 0x03A0)
            m.ds_write(player + 6, struct.pack('<H', (m.rw(m.DATA_SEG, player + 6) + 37 + 64 * k) & 0x1FF))
        yield f'turned {k}', turn


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.sort_draw_list.restype = ctypes.c_uint16
    fails = []
    states = []
    for name in ('sortlist', 'sortlist2'):
        states += pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '.pkl.gz'), 'rb'))
    records_in = records_out = reordered = 0
    for n, st in enumerate(states):
        for label, change in variants():
            m = capture.restore(st)
            change(m)
            count_in = m.rw(m.DATA_SEG, 0x50AC)
            before = m.ds_read(0x1576, 12 * count_in)
            g, mem, planes = make_game(m)
            got_si = lib.sort_draw_list(ctypes.byref(g))
            CASES += 1
            where = f'capture {n}, {label}'
            try:
                rout = capture.run_to_return(m, far=True, max_instr=20_000_000)
            except Exception as e:
                fails.append(f'{where}: original: {e}')
                continue
            if got_si != rout['si']:
                fails.append(f'{where}: list pointer {got_si:04X}, original {rout["si"]:04X}')
                continue
            if not compare(where, mem, planes, m, fails):
                continue
            count_out = m.rw(m.DATA_SEG, 0x50AC)
            records_in += count_in
            records_out += count_out
            # was the surviving order anything other than the input order reversed?
            out = m.ds_read(rout['si'], 12 * count_out)
            key = lambda b, i: b[12 * i:12 * i + 6] + b[12 * i + 8:12 * i + 12]
            kept = [key(before, i) for i in range(count_in)]
            order = [key(out, i) for i in range(count_out)]
            plain = [k for k in reversed(kept) if k in order]
            if order != plain:
                reordered += 1
    print(f'    sortlist: {records_in} records in, {records_out} kept; '
          f'{reordered} of {CASES} lists came out in an order other than "input reversed"')
    return fails
