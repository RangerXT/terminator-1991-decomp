"""keyboard_scancode (src/keyboard.c) against the original keyboard interrupt 0000:37E3.

From the in-game snapshot, random byte streams go to port 60h, one interrupt per byte:
presses and releases of the keys the game reads, Shift held or not, F0 prefixes (the next
byte counts as a release), E0 prefixes and other bytes of 80h and above, F12, a buffer
near full or wrapping (random read and write places), presses not buffered (DS:5B6A set),
and the code-segment byte 3B87 that makes the interrupt chain to the BIOS instead of
acknowledging the key itself. Compared after every byte: all memory but the stack, the
planes and card. Del is only ever let go, so Ctrl+Alt+Del (a reboot in the original) never
happens; C must never report it.
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

CASES = 0
KEYS = [0x01, 0x02, 0x03, 0x0E, 0x10, 0x11, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x2A, 0x2C, 0x31, 0x36, 0x38, 0x39,
        0x43, 0x44, 0x48, 0x4B, 0x4D, 0x50, 0x53, 0x58, 0x7F]


def stream(rng, length):
    out = []
    for _ in range(length):
        kind = rng.random()
        if kind < 0.45:
            out.append(rng.choice(KEYS))
        elif kind < 0.8:
            out.append(rng.choice(KEYS) | 0x80)
        elif kind < 0.88:
            out.append(0xF0)
        elif kind < 0.93:
            out.append(0xE0)
        else:
            out.append(rng.randrange(256))
    return out


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.keyboard_scancode.restype = ctypes.c_int
    fails = []
    rng = random.Random(0x37E3)
    base = dosemu.Machine()
    base.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    code_seg = (dosemu.LOAD_SEG) & 0xFFFF
    for case in range(40):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0x5BD9, bytes(128))                      # nothing held
        if case % 5 == 1:                                   # presses not buffered
            m.ds_write(0x5B6A, struct.pack('<H', rng.randrange(1, 0x10000)))
        if case % 4 == 2:                                   # chain to the BIOS
            m.wb(code_seg, 0x3B87, b'\xff')
        if case % 3 == 0:                                   # a buffer near full, or wrapping
            read = rng.randrange(0x5B70, 0x5BD4)
            count = rng.choice([rng.randrange(95, 100), rng.randrange(0, 100)])
            write = 0x5B70 + (read - 0x5B70 + count) % 100
            if rng.random() < 0.3:
                write = 0x5BD4                              # the place it wraps from
            m.ds_write(0x5B6C, struct.pack('<HH', write, read))
            m.ds_write(0x5BD4, struct.pack('<H', count))
        if case % 7 == 3:
            m.ds_write(0x5BD9 + 0x2A, b'\xff')              # Shift already down
        spans = regions(m)
        g, mem, planes = make_game(m)
        for i, code in enumerate(stream(rng, 60)):
            if code == 0x53:
                code = 0xD3                                 # Del is only let go: no reboot
            m.kbd_port = code
            reboot = lib.keyboard_scancode(ctypes.byref(g), code)
            try:
                m.call(0, 0x37E3, far=True, stack=(0x0002,))
            except Exception as error:
                return [f"case {case} byte {i} ({code:02X}): the original stopped: {error} at {m.file_addr()}"]
            CASES += 1
            if reboot:
                fails.append(f'case {case} byte {i} ({code:02X}): C reports Ctrl+Alt+Del')
                return fails
            compare(f'case {case} byte {i} ({code:02X})', mem, planes, m, spans, fails)
            if fails:
                return fails
    return fails
