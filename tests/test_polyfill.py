"""fill_polygon against recorded calls of the original at 11BC:0000.

Captures: python tools/capture.py 11BC:0000 polyfill --count 60 --skip 40 --ticks 40 --keys "2:right:12,18:up:15"

Compared after each call: the data segment (scan-conversion tables, span list) and all four
EGA bit planes of the emulated screen, byte for byte.
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import capture  # noqa: E402

CASES = 0
DS_END = 0xEA70


PLANE_BYTES = 4 * 0x10000
SCREEN_BYTES = PLANE_BYTES + 16
REG_NAMES = (['plane mask'] + ['set/reset', 'enable set/reset', 'colour compare', 'function', 'read plane',
                               'mode', 'misc', 'colour don\'t care', 'bit mask'] + ['selected index']
             + [f'latch {p}' for p in range(4)] + ['pad'])


def planes_of(machine):
    """The screen as the C code keeps it: the four bit planes followed by the card's
    registers and latches (16 bytes, see EgaRegs in src/term.h)."""
    return b''.join(bytes(p) for p in machine.vga.planes) + machine.vga.card_state()


def screen_differences(got, want):
    """Describe how two screen buffers differ, or return None if they are the same."""
    if got == want:
        return None
    diff = [i for i in range(len(want)) if got[i] != want[i]]
    pixels = [i for i in diff if i < PLANE_BYTES]
    if pixels:
        return (f'screen, {len(pixels)} plane bytes differ, first in plane {pixels[0] >> 16} '
                f'at offset {pixels[0] & 0xFFFF:04X}')
    regs = ', '.join(f'{REG_NAMES[i - PLANE_BYTES]} {got[i]:02X} (original {want[i]:02X})' for i in diff)
    return f'card registers differ: {regs}'


def check(label, ds, planes, after, fails):
    want = after.ds_read(0, DS_END)
    if ds.raw[:DS_END] != want:
        diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
        fails.append(f'{label}: data segment, {len(diff)} bytes differ, first at DS:{diff[0]:04X}')
        return
    problem = screen_differences(planes.raw, planes_of(after))
    if problem:
        fails.append(f'{label}: {problem}')


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.fill_polygon.restype = ctypes.c_int
    fails = []
    kinds = {'solid': 0, 'dither': 0, 'degenerate': 0}
    for n, (before, after, rin, rout) in enumerate(capture.replay('polyfill', far=True)):
        raw = before.ds_read(0, 0x10000)
        ds = ctypes.create_string_buffer(raw, 0x10000)
        planes = ctypes.create_string_buffer(planes_of(before), SCREEN_BYTES)
        status = lib.fill_polygon(ds, planes, ctypes.c_uint16(rin['si']))
        kinds['degenerate' if status else 'dither' if raw[0x468C] >= 16 else 'solid'] += 1
        CASES += 1
        check(f'capture {n}', ds, planes, after, fails)
        if (status != 0) != (rout['ax'] == 0xFFFF):
            fails.append(f'capture {n}: C says status {status}, original returned AX={rout["ax"]:04X}')
    if not all(kinds.values()):
        fails.append(f'recordings do not cover every kind: {kinds}')
    print(f'    polyfill recordings: {kinds}')
    return fails
