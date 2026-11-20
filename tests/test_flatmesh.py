"""draw_flat_mesh against recorded calls of the original at 0000:E83E: a one-face mesh
(ground polygon) from the fetched copy to pixels.

Captures: python tools/capture.py 0000:E83E flatmesh --count 40 --skip 9 --ticks 60 --keys "2:right:12,18:up:15"

Each recording is run four ways: as recorded (ground pass); in the ground pass ignoring the
record's "off screen" flag; as if in the object pass, where
the routine also rejects polygons off one corner and handles two-sided faces; and in the
object pass with the face marked two-sided. Compared: data segment and the four bit planes.
"""
import ctypes
import gzip
import os
import pickle
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from test_polyfill import PLANE_BYTES, SCREEN_BYTES, check, planes_of  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.draw_flat_mesh.restype = ctypes.c_int
    fails = []
    drew = {'ground pass': 0, 'ground pass, redone': 0, 'object pass': 0, 'object pass, two-sided': 0}
    reversed_faces = 0
    states = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'flatmesh.pkl.gz'), 'rb'))
    for n, st in enumerate(states):
        for variant in drew:
            m = capture.restore(st)
            mesh = m.r(m.REG_BY_NAME['bx'])
            if variant != 'ground pass':
                m.ds_write(0x50B0, b'\xff')           # do not trust the "off screen" record flag
            if variant.startswith('object'):
                m.ds_write(0x00BB, b'\0')
            if variant.endswith('two-sided'):
                m.ds_write(m.rw(m.DATA_SEG, mesh + 0x0A), b'\xff')
            ds = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
            start = planes_of(m)
            planes = ctypes.create_string_buffer(start, SCREEN_BYTES)
            face = m.rw(m.DATA_SEG, mesh + 6)
            refs_before = m.ds_read(face + 6, 4)
            count_before = m.rw(m.DATA_SEG, face + 4)
            status = lib.draw_flat_mesh(ds, planes, ctypes.c_uint16(mesh))
            CASES += 1
            label = f'capture {n}, {variant}'
            try:
                capture.run_to_return(m, max_instr=5_000_000)
            except Exception as e:
                fails.append(f'{label}: original: {e} (C returned {status})')
                continue
            if status != 0:
                fails.append(f'{label}: C version returned {status}')
                continue
            if planes_of(m)[:PLANE_BYTES] != start[:PLANE_BYTES]:
                drew[variant] += 1
            check(label, ds, planes, m, fails)
            if (variant.endswith('two-sided') and m.rw(m.DATA_SEG, face + 4) == count_before
                    and m.ds_read(face + 6, 4) != refs_before):
                reversed_faces += 1
    print('    flatmesh: polygons that reached the screen: ' + ', '.join(f'{k}: {v}' for k, v in drew.items())
          + f'; two-sided faces turned round: {reversed_faces}')
    return fails
