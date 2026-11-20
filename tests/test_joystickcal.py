"""The joystick calibration (joystick_calibrate, src/joystick.c) against the original 0000:38F6.

From the in-game snapshot, EGA (the game menu's option) and VGA (the main menu's, the facility
screen in mode 13h). The port read 3A33 is replaced in the emulator by a stub that loads
scripted counts (DS:8200 / 8202) and sets the button keys from a scripted port byte (8204)
as 3A33 does; the C side's JoystickRead returns the same script. Scripts: idle reads, a
press, held, released, for each of the three corners, both buttons, extreme counts (the
scales' signed comparisons and the IDIV). Boundaries (tests/boundaries.py): 3A33 (the stub),
the pause 5776:02C6. Compared at every boundary and at the end: memory, planes and card, the
mode-13h screen.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_gamemenus import MENU_CALL, MenuPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402

CASES = 0
SCRATCH = 0x8200
STUB = bytes([0xA1, 0x00, 0x82, 0x8B, 0x1E, 0x02, 0x82,
              0xF6, 0x06, 0x04, 0x82, 0x10, 0x75, 0x05, 0xC6, 0x06, 0xF5, 0x5B, 0xFF,
              0xF6, 0x06, 0x04, 0x82, 0x20, 0x75, 0x05, 0xC6, 0x06, 0x12, 0x5C, 0xFF, 0xC3])
BOUNDARIES = [
    Routine(0, 0x3A33, stub=STUB),
    Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
]
JOYSTICK_READ = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16),
                                 ctypes.POINTER(ctypes.c_uint8), ctypes.c_void_p)


class JoystickCalibration(ctypes.Structure):
    _fields_ = [('read', JOYSTICK_READ), ('user', ctypes.c_void_p), ('text', ctypes.c_void_p),
                ('timing', ctypes.c_void_p), ('screen', ctypes.c_void_p)]


def script(rng, extreme):
    reads = []
    for corner in range(3):
        for _ in range(rng.randrange(0, 4)):
            reads.append((rng.randrange(0x10000), rng.randrange(0x10000), rng.choice([0xFF, 0xDF])))
        value = (lambda: rng.choice([0, 0x7FFF, 0x8000, 0xFFFF, rng.randrange(0x10000)])) if extreme else \
            (lambda: rng.randrange(20 + corner * 200, 60 + corner * 200))
        reads.append((value(), value(), rng.choice([0xEF, 0xCF])))
        for _ in range(rng.randrange(0, 3)):
            reads.append((rng.randrange(0x10000), rng.randrange(0x10000), 0xEF))
        reads.append((rng.randrange(0x10000), rng.randrange(0x10000), rng.choice([0xFF, 0xDF])))
    return reads


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.joystick_calibrate.restype = ctypes.c_int
    fails = []
    rng = random.Random(0x38F6)
    for case in range(24):
        vga = case % 2 == 1
        reads = script(rng, case % 4 >= 2)
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        if vga:
            m.ds_write(0xADCF, b'\x01')
            m.vga.set_mode(0x13, clear=False)
            m.uc.mem_write(0x449, b'\x13')
        stub_all(m, BOUNDARIES)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        count = [0]

        def on_boundary(entry):
            if entry['service'] == 0x3A33:
                h, v, port = reads[count[0]] if count[0] < len(reads) else (0, 0, 0xEF)
                count[0] += 1
                m.ds_write(SCRATCH, struct.pack('<HHB', h, v, port))

        recorder = Recorder(m, BOUNDARIES, on_boundary, chunky=True).install()
        m.call(0, 0x38F6, max_instr=200_000_000)
        CASES += 1
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen)
        served = [0]

        @JOYSTICK_READ
        def joystick(h, v, port, user):
            if replay.serve(0x3A33):
                return -1
            values = reads[served[0]] if served[0] < len(reads) else (0, 0, 0xEF)
            served[0] += 1
            h[0], v[0], port[0] = values
            return 0

        @MENU_CALL
        def timing_call(gp, op, a, b, user):
            return -1 if replay.serve(op, a, 0) else 0

        timing = MenuPlatform(timing_call, None)
        host = JoystickCalibration(joystick, None, None, ctypes.addressof(timing), ctypes.addressof(screen))
        status = lib.joystick_calibrate(ctypes.byref(g), ctypes.byref(host))
        problem = replay.finished()
        where = f'case {case} ({"VGA" if vga else "EGA"}, {len(reads)} reads)'
        if status or problem:
            fails.append(f'{where}: status {status}; {problem}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{where}: at the end, memory {error}')
            elif screen.raw != bytes(m.vga.chunky):
                fails.append(f'{where}: at the end, the mode-13h screen differs')
            else:
                compare(where, mem, planes, m, spans, fails)
        if fails:
            return fails
    return fails
