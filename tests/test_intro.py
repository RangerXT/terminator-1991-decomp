"""The start-up screen (intro_screen, src/intro.c) against the original 57C5:000E.

From the in-game snapshot: the credits typed over the wireframe logo, which slides in and
then zooms. Variants: as recorded (the logo half slid in), from the start-up values
(DS:BE8E = 0, BE90 = EED0h, BE92 = 1), during the zoom (BE92 = 100h, and 1, where the
projection's divisions overflow and the divide-error handler skips them), a key at various
frames, and the credits shortened to a few pages run to the end (pauses, the cursor blink,
the second half of each pause, the last 100 frames of the logo alone). Boundaries
(tests/boundaries.py): page selection 0C6B, the retrace waits 0D8D / 0DAA (stubbed), the
page flip's INT 10h at 0C89 / 0CB9. Keys go into the buffer at a chosen wait. Compared at
every boundary and at the end: memory, the EGA planes and card. Also 57C5:053C, which sets
the text buffer's segment at start-up.
"""
import ctypes
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import Inline, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import type_key  # noqa: E402

CASES = 0
BOUNDARIES = [
    Routine(0, 0x0C6B, registers=('ax',)),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Inline(0x0C89, 0x0C8B, 0xFF05), Inline(0x0CB9, 0x0CBB, 0xFF05),
]
SHORT = b'\0\0AB CD\nEF\0GH IJ\nK\nLMN\0\xff\xff'

SCENARIOS = [
    # name, retrace wait at which a key is typed (two waits a frame; None: no key), settings
    ('as recorded, a key after 8 frames', 16, {}),
    ('from the start, a key after 30 frames', 60, {'reset': True}),
    ('zoom, a key after 40 frames', 80, {'zoom': 0x100}),
    ('zoom from divisor 1, a key after 25 frames', 50, {'zoom': 1}),
    ('short credits, zoom, to the end', None, {'zoom': 0x100, 'text': SHORT}),
    ('short credits, from the start, to the end', None, {'reset': True, 'text': SHORT}),
    ('short credits, a key in the first pause', 30, {'zoom': 0x40, 'text': SHORT}),
]


def run_original(m, key_at):
    waits = [0]

    def on_boundary(entry):
        if entry['service'] in (0x0D8D, 0x0DAA):
            waits[0] += 1
            if waits[0] == key_at:
                type_key(m, ord('x'))

    recorder = Recorder(m, BOUNDARIES, on_boundary).install()
    m.call(0x57C5, 0x000E, far=True, max_instr=3_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, waits[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.intro_screen.restype = ctypes.c_int
    fails = []
    outcomes = []
    for label, key_at, settings in SCENARIOS:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))

        def word(off, value):
            m.ds_write(off, struct.pack('<H', value & 0xFFFF))

        if settings.get('reset'):
            word(0xBE8E, 0)
            word(0xBE90, 0xEED0)
            word(0xBE92, 1)
            m.ds_write(0xDE10, b'\0\0\0')
            word(0xDE2C, 0)
        if 'zoom' in settings:
            word(0xBE8E, 0xF500)
            word(0xBE90, 0xF501)
            word(0xBE92, settings['zoom'])
            word(0xDE2C, 3)
        if 'text' in settings:
            m.ds_write(0xDBB4, settings['text'])
        stub_all(m, BOUNDARIES)
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        entry_sp = (m.r(dosemu.UC_X86_REG_SP) - 4) & 0xFFFF      # after the far call's return address
        recorder, waits = run_original(m, key_at)
        CASES += 1
        outcomes.append(f'{label}: {waits // 2} frames')
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, 0x0500 | a if service == 0xFF05 else a, b)

        resources = Resources(resource, None)
        status = lib.intro_screen(ctypes.byref(g), entry_sp, ctypes.byref(resources), ctypes.byref(files.host))
        problem = replay.finished()
        if status or problem:
            fails.append(f'{label}: status {status}; {problem}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{label}: at the end, memory {error}')
            else:
                compare(label, mem, planes, m, spans, fails)
        if fails:
            return fails
    # 57C5:053C, at start-up: the text buffer's segment
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.ds_write(0xDE20, struct.pack('<H', 0x1234))
    g, mem, planes = make_game(m)
    lib.intro_set_buffer(ctypes.c_void_p(g.ds))
    m.call(0x57C5, 0x053C, far=True)
    CASES += 1
    compare('57C5:053C', mem, planes, m, regions(m), fails)
    print('    intro: ' + '; '.join(outcomes))
    return fails
