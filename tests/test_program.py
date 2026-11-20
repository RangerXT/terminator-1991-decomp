"""The program's start and set-up routines (src/startup.c) against the original 0000:0000,
04D3, 04E8, 052C, 09FB / 0A2C, 97D8 / 86F4, 59A6 / 5A58 / 5A0D and D5B1 / D5FA.

From the in-game snapshot. Every routine the C leaves to the host (ProgramServices.call:
screens, images, sound, the serial link) is a stubbed boundary on the original's side
(tests/boundaries.py), compared at each call with its argument registers and memory, the
planes and the card; the rest runs for real: the memory routines, and the BIOS, DOS and
port accesses, which tools/dosemu.py traces and tests/machine.py replays to C (registers
checked, the bytes of each file write too; the EGA sequencer and graphics ports are left out,
the C models them). The ratings file goes to a scratch folder.

Cases: the preload with and without the EMS frame and with a missing file; 04D3; the intro
with and without a key that ends its pauses; 052C; the starting kit for each difficulty,
items refused (carry), no room (the original then returns to 0000:BX, where the test puts
a jump to the end) and without the kit; a new game's start and a loaded one's; the ratings
after a game with a place (named, or not asked), without one, for both players. The start:
an adapter that is neither EGA nor VGA, EGA, a bad option, link without a port and with one
(still "bad link"), quitting at the menu (with and without the closing music), a game
quit, a game then the menu's new game, a game lost (the ending and the ratings), the intro
skipped (DS:5BF6) and the ending music flag (DS:7B86).
"""
import ctypes
import os
import random
import struct
import sys
import tempfile

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_CX, UC_X86_REG_DS, UC_X86_REG_DX

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import BASE, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from machine import CpuRegs, MachineReplay, register, traced  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_startup import PROGRAM_CALL, ProgramServices  # noqa: E402

CASES = 0
EGA_PORTS = {0x3C4, 0x3C5, 0x3CE, 0x3CF}
# the host's routines: their argument registers
HOST = {
    (0, 0x1AC9): (), (0, 0x8986): (), (0x57C5, 0x000E): (), (0, 0xB210): ('si', 'bx'), (0, 0x0C6B): ('ax',),
    (0, 0x6149): (), (0, 0x16A9): (), (0, 0x8ABE): (), (0, 0x70DF): (), (0, 0xE475): (), (0, 0x6B23): (),
    (0, 0x4F4B): (), (0, 0xCA1A): (), (0, 0xB187): (), (0, 0xB199): (), (0, 0x5032): ('si', 'ax'),
    (0, 0x855A): ('si', 'di'), (0, 0x3B88): (), (0, 0xD265): (), (0, 0xD628): (), (0, 0xDF3A): (),
    (0, 0x9922): (), (0, 0xEA86): (), (0, 0x8C64): (), (0, 0x8C13): (), (0, 0x8C52): (), (0, 0x02B5): ('bx',),
    (0x151B, 0x000E): ('ax',), (0x151B, 0x0437): (), (0, 0x0155): (), (0x151B, 0x009D): (), (0, 0x8C45): (),
    (0, 0x5B6A): (), (0, 0x8C96): (), (0, 0x8BA2): (), (0, 0x91EA): (), (0x151B, 0x020F): (),
}


def specs(refuse=False):
    out = []
    for (seg, off), registers in HOST.items():
        stub = b'\xcb' if seg else (b'\xf9\xc3' if off == 0x855A and refuse else b'\xc3')
        out.append(Routine(seg, off, far=bool(seg), stub=stub, registers=registers, service=seg << 16 | off))
    return out


def adapter(m, kind):
    """The display adapter the BIOS reports: 'vga' (the emulator's), 'ega' (no 1Ah), 'cga'
    (neither 1Ah nor 12h)."""
    video = m._video

    def patched():
        ah = m.ax() >> 8
        if (ah == 0x1A and kind != 'vga') or (ah == 0x12 and kind == 'cga'):
            return
        video()
    m._video = patched


def scratch(m, folder, names):
    lookup = m._path

    def path(name):
        base = os.path.basename(name.replace('\\', '/')).upper()
        return os.path.join(folder, base) if base in names else lookup(name)
    m._path = path


def fresh():
    """The in-game snapshot with the keyboard vector the BIOS's, as when the program starts
    (the snapshot has the game's own installed)."""
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.uc.mem_write(0x24, struct.pack('<HH', 0x0024, dosemu.BIOS_SEG))
    return m


def run_case(lib, label, setup, original, c_side, fails, refuse=False, on_boundary=None, data_check=True):
    """setup(m) before the copies; original(m) runs it; c_side(lib, g, services) -> status;
    original's status from original(m)."""
    global CASES
    m = fresh()
    folder = tempfile.mkdtemp(prefix='termprog')
    try:
        scratch(m, folder, {'RATINGS.RSE', 'RATINGS.TRM'})
        setup(m)
        boundaries = specs(refuse)
        stub_all(m, boundaries)
        g, mem, planes = make_game(m)
        ctypes.memmove(g.mem + 0xC0000, bytes(m.uc.mem_read(0xC0000, 0x40000)), 0x40000)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        trace = traced(m)
        written = []
        dos = m._dos

        def recording_dos():
            if m.ax() >> 8 == 0x40:
                cx = m.r(UC_X86_REG_CX)
                written.append(bytes(m.rb(m.r(UC_X86_REG_DS), m.r(UC_X86_REG_DX), cx)) if cx else b'')
            return dos()
        m._dos = recording_dos
        recorder = Recorder(m, boundaries, on_boundary or (lambda entry: None)).install()
        want = original(m)
        if recorder.pending:
            fails.append(f'{label}: a boundary did not return')
            return None
        CASES += 1
        events = [e for e in trace if not (e[0] in ('in', 'out') and e[1] in EGA_PORTS)]
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)
        writes = iter(written)

        def check(n, r, index):
            if not data_check or n != 0x21 or r.ax >> 8 != 0x40:
                return None
            expected = next(writes, None)
            got = ctypes.string_at(g.mem + (r.ds << 4) + r.dx, r.cx) if r.cx else b''
            return None if got == expected else f'write to {r.bx}: C wrote other bytes'

        machine = MachineReplay(g, mem, planes, events, video=lambda n: n == 0x10, check=check)

        @PROGRAM_CALL
        def call(gp, seg, off, regs, user):
            names = HOST.get((seg, off))
            if names is None:
                replay.errors.append(f'C called {seg:04X}:{off:04X}, no boundary')
                return -1
            values = [register(regs.contents, n) for n in names] + [0, 0]
            if replay.serve(seg << 16 | off, values[0], values[1]):
                return -1
            if replay.last['carry']:
                regs.contents.flags |= 1
            else:
                regs.contents.flags &= 0xFFFE
            return 0

        services = ProgramServices(ctypes.addressof(machine.services), call, None)
        got = c_side(lib, g, services)
        problem = replay.finished() or machine.finished()
        if got != want or problem:
            fails.append(f'{label}: C status {got}, original {want}; {problem}')
            return None
        error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
        if error:
            fails.append(f'{label}: at the end, memory {error}')
            return None
        compare(label, mem, planes, m, spans, fails)
        return recorder
    finally:
        for base in os.listdir(folder):
            os.remove(os.path.join(folder, base))
        os.rmdir(folder)


def plain(address, result=lambda m, out: 0):
    def original(m):
        out = m.call(0, address, max_instr=2_000_000_000)
        return result(m, out)
    return original


def lib_call(name, *extra):
    def c_side(lib, g, services):
        return getattr(lib, name)(ctypes.byref(g), *extra, ctypes.byref(services))
    return c_side


def routine_cases(lib, fails):
    rng = random.Random(0x052C)
    outcomes = []

    # 09FB: the EMS frame at 9000h (with a missing file), none
    def frame(missing=False):
        def setup(m):
            m.ds_write(0x0208, struct.pack('<H', 0x9000))
            if missing:
                m.ds_write(0x000D, b'zzmissin.msk\0')
        return setup
    for label, setup in (('09FB, frame', frame()), ('09FB, a file missing', frame(True)),
                         ('09FB, no frame', lambda m: m.ds_write(0x0208, b'\0\0'))):
        run_case(lib, label, setup, plain(0x09FB), lib_call('startup_preload'), fails)
        if fails:
            return
    run_case(lib, '04D3', lambda m: None, plain(0x04D3), lib_call('startup_init'), fails)
    if fails:
        return

    def key_waiting(m):
        m.ds_write(0x5BD4, b'\x01\x00')
    for label, setup in (('04E8', lambda m: None), ('04E8, a key waiting', key_waiting)):
        run_case(lib, label, setup, plain(0x04E8), lib_call('startup_intro'), fails)
        if fails:
            return
    run_case(lib, '052C', lambda m: None, plain(0x052C), lib_call('startup_game_setup'), fails)
    if fails:
        return

    # 97D8: the kit by difficulty, refused, no room (return to 0000:BX: a jump to the end there)
    def kit(difficulty, capacity=300, full=False, on=True):
        def setup(m):
            m.ds_write(0x1151, b'\xff' if on else b'\0')
            m.ds_write(0x03F0, struct.pack('<H', difficulty))
            m.ds_write(0x03F2, struct.pack('<H', capacity))
            m.ds_write(0x116C, b'\0\0')
            if full:                                   # the first item's category count at 14h
                item = m.rw(m.DATA_SEG, [0xAB3C, 0xAB48, 0xAB52][difficulty])
                index = (m.ds_read(item + 2, 1)[0] - 1) & 0xFF
                counter = m.rw(m.DATA_SEG, 0x9A4E + 2 * (5 if index > 4 else index))
                m.ds_write(counter, b'\x14')
            m.wb(dosemu.LOAD_SEG, 0x0000, b'\xe9\xfc\xff')     # 0000:0000: JMP FFFF, the end of the call
        return setup

    for label, setup, refuse, expect in (
            ('97D8, easy', kit(0), False, 0), ('97D8, normal', kit(1), False, 0), ('97D8, hard', kit(2), False, 0),
            ('97D8, items refused', kit(1), True, 0), ('97D8, no kit', kit(1, on=False), False, 0),
            ('97D8, no room', kit(0, capacity=0), False, 2), ('97D8, category full', kit(2, full=True), False, 2)):
        bx = ctypes.c_uint16(0xFFFF)

        def original(m, expect=expect):
            # no room: 86F4 drops two words and returns to 0000:BX (0), where our jump ends the call
            astray = []
            m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: astray.append(a), None, BASE, BASE)
            m.call(0, 0x97D8, max_instr=2_000_000_000)
            return 2 if astray else 0

        def c_side(lib, g, services, bx=bx):
            return lib.startup_inventory(ctypes.byref(g), ctypes.byref(services), ctypes.byref(bx))
        if run_case(lib, label, setup, original, c_side, fails, refuse=refuse) is None or fails:
            return
        if expect == 2 and bx.value != 0:
            fails.append(f'{label}: C reported a return to 0000:{bx.value:04X}, the original went to 0000:0000')
            return
        outcomes.append(f'{label}: {expect}')

    # 59A6: a new game, a loaded one
    for label, loaded in (('59A6, new', 0), ('59A6, loaded', 0xFF)):
        run_case(lib, label, lambda m, v=loaded: m.ds_write(0x1143, bytes([v])), plain(0x59A6),
                 lib_call('startup_position'), fails)
        if fails:
            return

    # D5B1: the score's place from the table; named or not asked; no place; each player
    def ratings(place, asked=True, reese=False):
        def setup(m):
            m.ds_write(0x038A, b'\0' if asked else b'\x01')
            if reese:
                m.ds_write(0x03A0, struct.pack('<H', 0x04D4))
            table = bytearray(0xCF)
            struct.pack_into('<H', table, 0, 5)       # five records
            for i in range(5):
                score = 0x7FFF if place is None or i < place else 0
                struct.pack_into('<H', table, 2 + i * 0x29, score)
                table[2 + i * 0x29 + 0x14:2 + i * 0x29 + 0x14 + 6] = f'NAME{i}'.encode() + b'\0'
            m.ds_write(0x50B2, bytes(table))
            m.ds_write(0xE3FA, b'NEWNAME\0' + bytes(rng.randrange(256) for _ in range(14)))
        return setup
    for label, setup in (('D5B1, first place', ratings(0)), ('D5B1, third, not asked', ratings(2, asked=False)),
                         ('D5B1, no place', ratings(None)), ('D5B1, Reese, last place', ratings(4, reese=True))):
        run_case(lib, label, setup, plain(0xD5B1), lib_call('ratings_commit'), fails)
        if fails:
            return
    print('    program, routines: ' + '; '.join(outcomes))


def start_cases(lib, fails):
    """0000:0000 from the snapshot, ES = the PSP, DS such that the RETF at the end (to the
    words DS:0 pushed first) lands on a jump the test puts before the end of the call."""
    outcomes = []
    end_ds = dosemu.LOAD_SEG + 0x0FFF                    # DS:0000 = CS:FFF0: JMP SHORT FFFF

    def scenario(kind='vga', tail=b'', menu=(0x55,), after_game=(), skip_intro=False, closing_music=True,
                 ending_flag=False):
        held = {}

        def setup(m):
            held['m'] = m
            adapter(m, kind)
            psp = m.rw(m.DATA_SEG, 0xEA6E)
            text = b' ' + tail if tail else b''
            m.wb(psp, 0x80, bytes([len(text)]) + text + b'\r')
            m.ds_write(0x01DE, b'\0')
            m.ds_write(0x5BF6, b'\xff' if skip_intro else b'\0')
            m.ds_write(0xEA3C, b'\0' if closing_music else b'\xff')
            m.ds_write(0x7B86, b'\x01\x00' if ending_flag else b'\0\0')
            m.ds_write(0x1151, b'\0')
            m.ds_write(0x1143, b'\0')
            m.wb(dosemu.LOAD_SEG, 0xFFF0, b'\xeb\x0d')
        menus, games = list(menu), list(after_game)

        def on_boundary(entry):
            service = entry['service']
            if service == 0x9922:                      # the main menu: what the player chose
                held['m'].ds_write(0x1159, bytes([menus.pop(0) if menus else 0x55]))
            elif service == 0x0155:                     # the game ended so
                held['m'].ds_write(0x1159, bytes([games.pop(0) if games else 0x55]))
        return setup, on_boundary

    def original(m):
        psp = m.rw(m.DATA_SEG, 0xEA6E)
        m.call(0, 0x0000, ds=end_ds, es=psp, max_instr=4_000_000_000)
        return 0

    def c_side(lib, g, services):
        psp = ctypes.c_uint16.from_address(g.ds + 0xEA6E).value
        return lib.program_start(ctypes.byref(g), psp, ctypes.byref(services))

    cases = [
        ('a CGA', dict(kind='cga')),
        ('EGA, quit at the menu', dict(kind='ega')),
        ('a bad option', dict(tail=b'bad')),
        ('link without a port', dict(tail=b'link')),
        ('link com1', dict(tail=b'link com1')),
        ('quit at the menu', dict()),
        ('quit at the menu, no closing music', dict(closing_music=False)),
        ('a game, quit', dict(menu=(0,), after_game=(0x55,))),
        ('a game, new game, quit', dict(menu=(0, 0x55), after_game=(0xAA,))),
        ('a game lost, then quit', dict(menu=(0, 0x55), after_game=(1,))),
        ('intro skipped, ending music flag', dict(skip_intro=True, ending_flag=True)),
    ]
    for label, settings in cases:
        setup, on_boundary = scenario(**settings)
        recorder = run_case(lib, f'start, {label}', setup, original, c_side, fails, on_boundary=on_boundary)
        if fails:
            return
        outcomes.append(f'{label}: {len(recorder.calls)} calls')
    print('    program, start: ' + '; '.join(outcomes))


def run(ctx):
    lib = ctx.lib
    for name in ('startup_preload', 'startup_init', 'startup_intro', 'startup_game_setup', 'startup_inventory',
                 'startup_position', 'ratings_commit', 'program_start'):
        getattr(lib, name).restype = ctypes.c_int
    fails = []
    routine_cases(lib, fails)
    if not fails:
        start_cases(lib, fails)
    return fails
