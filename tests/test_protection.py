"""The copy-protection screen (protection_screen, src/protection.c) against the original
0000:EA86.

From the in-game snapshot with the screen not yet shown (DS:E67E = 0): a VGA installation
(pass256.img in mode 13h) and an EGA one (DS:ADD0 = 0, pass.img from data/ega). The arrow
keys and Enter are set in the key table at the busy loop's reads (EBA4, a point while none
of them is down) and let go at the first retrace wait after; some are held for several
waits (they repeat every ten frames). Variants: moves off the top and bottom (clamped),
answers kept from the ten seeds (DS:E6DF), the screen already shown. Boundaries
(tests/boundaries.py): the mode switches at EA9C / EAA6 (run by the emulator's BIOS), the
retrace waits 0D8D / 0DAA (stubbed). Compared at every boundary and at the end: memory, the
EGA planes and card, the mode-13h screen, and the VGA palette at the end.
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import set_clock  # noqa: E402
from test_damagepanel import ega_installation  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform  # noqa: E402

CASES = 0
KEY = 0x5BD9
ENTER, UP, LEFT, RIGHT, DOWN = 0x1C, 0x48, 0x4B, 0x4D, 0x50
POLL = 0xEBA4


class ProtectionServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in ('resources', 'images', 'keys', 'screen', 'palette')]


def idle(m):
    return not any(m.ds_read(KEY + k, 1)[0] for k in (ENTER, UP, LEFT, RIGHT, DOWN))


BOUNDARIES = [
    Inline(0xEA9C, 0xEA9E, 0xFF10), Inline(0xEAA6, 0xEAA8, 0xFF10),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Point(POLL, POLL, idle),
]

SCENARIOS = [
    # name, [(key, waits it stays down)] one per read of the keys, settings
    ('VGA, Enter', [(ENTER, 0)], {}),
    ('VGA, moves', [(DOWN, 1), (DOWN, 1), (RIGHT, 1), (UP, 1), (LEFT, 1), (DOWN, 1), (ENTER, 0)], {}),
    ('VGA, off the edges', [(UP, 1), (LEFT, 1)] + [(DOWN, 1)] * 13 + [(RIGHT, 1), (ENTER, 0)], {}),
    ('VGA, a held key', [(DOWN, 35), (RIGHT, 12), (ENTER, 0)], {}),
    ('VGA, three kept answers', [(DOWN, 1), (ENTER, 0)], {'kept': 3}),
    ('EGA, Enter', [(ENTER, 0)], {'ega': True}),
    ('EGA, moves', [(RIGHT, 1), (DOWN, 1), (DOWN, 1), (DOWN, 1), (LEFT, 1), (ENTER, 0)], {'ega': True}),
    ('EGA, ten kept answers', [(UP, 1), (ENTER, 0)], {'ega': True, 'kept': 10}),
    ('already shown', [], {'shown': True}),
]


def run_original(m, script):
    reads, held = [0], []

    def on_boundary(entry):
        if entry['service'] == POLL:
            if reads[0] < len(script):
                key, waits = script[reads[0]]
                m.ds_write(KEY + key, b'\xff')
                held.append([key, waits])
            else:
                m.ds_write(KEY + ENTER, b'\xff')
            reads[0] += 1
        elif entry['service'] == 0x0D8D:
            for item in held:
                item[1] -= 1
                if item[1] < 0:
                    m.ds_write(KEY + item[0], b'\0')
            held[:] = [item for item in held if item[1] >= 0]

    recorder = Recorder(m, BOUNDARIES, on_boundary, chunky=True).install()
    m.call(0, 0xEA86, max_instr=1_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, reads[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.protection_screen.restype = ctypes.c_int
    fails = []
    outcomes = []
    for label, script, settings in SCENARIOS:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0xE67E, b'\xff' if settings.get('shown') else b'\0')
        m.ds_write(KEY, bytes(128))
        m.ds_write(0xE6DF, bytes([settings.get('kept', 0)]))
        if settings.get('ega'):
            ega_installation(m)
        stub_all(m, BOUNDARIES)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        palette = ctypes.create_string_buffer(768)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        set_clock(lib, m)
        recorder, reads = run_original(m, script)
        CASES += 1
        outcomes.append(f'{label}: {reads} key reads, right symbol at {m.rw(m.DATA_SEG, 0xEA30)}')
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)

        @KEY_POLL
        def key_poll(gp, user):
            return replay.serve(POLL)

        keys = KeyboardPlatform(key_poll, None)
        services = ProtectionServices(ctypes.addressof(resources), ctypes.addressof(files.host), ctypes.addressof(keys),
                                      ctypes.addressof(screen), ctypes.addressof(palette))
        status = lib.protection_screen(ctypes.byref(g), ctypes.byref(services))
        problem = replay.finished()
        if status or problem:
            fails.append(f'{label}: status {status}; {problem}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{label}: at the end, memory {error}')
            elif screen.raw != bytes(m.vga.chunky):
                fails.append(f'{label}: at the end, the mode-13h screen differs')
            elif not settings.get('ega') and not settings.get('shown') and palette.raw != bytes(m.vga.dac):
                fails.append(f'{label}: the VGA palette differs')
            else:
                compare(label, mem, planes, m, spans, fails)
        if fails:
            return fails
    print('    protection: ' + '; '.join(outcomes))
    return fails
