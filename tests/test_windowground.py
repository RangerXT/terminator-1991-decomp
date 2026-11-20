"""Every coarse window origin, using DOS 0A16 as the packing oracle."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_imageload import Files

CASES = 0


def run(ctx):
    global CASES
    CASES = 0
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    errors = []
    shapes = {}
    for row in range(16):
        for col in range(24):
            m.ww(m.DATA_SEG, 0x7280, col)
            m.ww(m.DATA_SEG, 0x7282, row)
            game, ram, planes = make_game(m)
            files = Files(m, record=False)
            start = files.next_handle
            status = ctx.lib.load_window_ground_and_cells(ctypes.byref(game), ctypes.byref(files.host))
            m.call(0x11BC, 0x0A16, max_instr=10_000_000)
            label = f'window ({col},{row})'
            CASES += 1
            if status or files.handles or files.next_handle != m.next_handle:
                return [f'{label}: status {status}, handles {files.next_handle}/{m.next_handle}']
            if not compare(label, ram, planes, m, errors):
                return errors
            sectors = (files.next_handle-start)//2
            shapes[sectors] = shapes.get(sectors, 0)+1
    print('    all ground/street origins by number of source sectors:', shapes)
    return [] if set(shapes) == {1, 2, 4} else ['missing sector overlap']
