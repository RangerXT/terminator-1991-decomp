"""Saving, loading and deleting games (src/savegame.c) against the original 0000:4B7E (save),
4CDE (delete), 4CE5 (load) and the save block coder 0A76.

4B7E and 4CDE are called as the game menu calls an action (SI = 0, ES = DS; in C through
game_menu_action, src/gamemenus.c, with the machine services) with a word
below the return address: an action that closes the menu drops its return address
(ADD SP,2) and returns onto that word, which the test points at a NOP before the end, so
"closed" and "the menu goes on" are told apart (and the carry). 4CE5 is called as the main
menu calls it. From recorded main-loop frames (the Terminator on foot, frameloop from
tests/test_frame.py), on the in-game EGA screen and on the VGA facility screen (DS:ADCF set,
mode 13h). Save files go to a scratch folder (the emulator's game folder for the run),
filled per case with saves of the right size and files of another size; the DOS calls the
original made (INT 21h, tools/dosemu.py's trace) are replayed to C through tests/machine.py,
which checks every register DOS reads and, for writes, the bytes written.

Scenarios: not on foot; a new name; a name that exists (overwrite: yes, no and another name,
no and Esc, Esc; the No answer pointed at the unreferenced entry 4B76); Esc in the name editor; an 8-letter name; 20 saves (the picker deletes one first, also
after an Esc); a file of another size; delete (nothing saved, the second, Esc); load (nothing
saved, the first, Esc, past a file of another size, 21 saves: the 20th); on the VGA screen a
short name (the scan for the end looks for AL = 2 there, so the name gets no ".CSM"), an
8-letter name and overwriting it, loading, nothing saved, delete with Esc. Boundaries
(tests/boundaries.py): the menu waits 5776:02C6 (keys scripted there), the key releases
4A6F / 4B3A (VGA 9E36 / 9F07), page selection 0C6B, the name editor's key reads 37AC (keys
typed there) and Esc release E038, the VGA message box's waits 11BC:2C27 / 2C35 / 2C45.
Compared at every boundary and at the end: memory, the EGA planes and card, the mode-13h
screen. 0A76 is also called directly: random blocks, sizes, players and AX.
"""
import ctypes
import gzip
import os
import pickle
import random
import struct
import sys
import tempfile

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_CX, UC_X86_REG_DS, UC_X86_REG_DX, UC_X86_REG_EFLAGS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from boundaries import BASE, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from machine import MachineReplay, traced  # noqa: E402
from test_blast import set_clock  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_frame import TEXT_POLL, TextPlatform  # noqa: E402
from test_gamemenus import MENU_CALL, GameMenuServices, MenuPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform, buffer_empty, type_key  # noqa: E402
from test_ratingsscreen import RatingsServices  # noqa: E402

CASES = 0
KEY = 0x5BD9
SC = {'esc': 0x01, 'enter': 0x1C, 'up': 0x48, 'down': 0x50}
FACILITY_SCREEN = 0xADCF


class SaveGameServices(ctypes.Structure):
    _fields_ = [('menus', ctypes.c_void_p), ('machine', ctypes.c_void_p)]


def held(m, *names):
    return any(m.ds_read(KEY + SC[n], 1)[0] for n in names)


COMMON = [
    Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
    Routine(0, 0x0C6B, registers=('ax',)),
    Point(0x37AC, 0x37AC, buffer_empty),
    Point(0xE038, 0xE038, lambda m: held(m, 'esc')),
]
EGA = [
    Point(0x4A6F, 0x1000, lambda m: held(m, 'esc', 'enter')),
    Point(0x4B3A, 0x1001, lambda m: held(m, 'esc')),
]
VGA = [
    Point(0x9E36, 0x1000, lambda m: held(m, 'esc', 'enter')), Point(0x9F07, 0x1001, lambda m: held(m, 'esc')),
    Point(0x2C27, 0x2C27, lambda m: held(m, 'esc', 'enter'), seg=0x11BC),
    Point(0x2C35, 0x2C35, lambda m: not held(m, 'esc', 'enter'), seg=0x11BC),
    Point(0x2C45, 0x2C45, lambda m: held(m, 'esc', 'enter'), seg=0x11BC),
]

ENTRY = {'save': 0x4B7E, 'delete': 0x4CDE, 'load': 0x4CE5}
TWENTY = [f'S{i:02d}' for i in range(20)]


def name(text):
    return list(text) + [0x0D]


SCENARIOS = [
    # name, entry, settings: saves / other files there, keys typed in the editor, {menu wait:
    # keys}, foot, vga; expect: the status C must return and the files after
    ('in a car', 'save', {'foot': False}, (0, set())),
    ('a new name', 'save', {'typed': name('ABC')}, (1, {'ABC.CSM'})),
    ('over an old one: yes', 'save', {'saves': ['ABC', 'OLD'], 'typed': name('ABC'), 'menu': {1: ['enter']}},
     (1, {'ABC.CSM', 'OLD.CSM'})),
    ('over an old one: no, another name', 'save',
     {'saves': ['ABC'], 'typed': name('ABC') + name('XY'), 'menu': {1: ['down'], 2: ['enter']}},
     (1, {'ABC.CSM', 'XY.CSM'})),
    ('over an old one: no, Esc', 'save',
     {'saves': ['ABC'], 'typed': name('ABC') + ['esc'], 'menu': {1: ['down'], 2: ['enter'], 3: ['esc']}},
     (1, {'ABC.CSM'})),
    ('over an old one: no through 4B76 (unreferenced), another name', 'save',
     {'saves': ['ABC'], 'typed': name('ABC') + name('XY'), 'menu': {1: ['down'], 2: ['enter']}, 'no': 0x4B76},
     (1, {'ABC.CSM', 'XY.CSM'})),
    ('over an old one: Esc', 'save', {'saves': ['ABC'], 'typed': name('ABC'), 'menu': {1: ['esc']}},
     (1, {'ABC.CSM'})),
    ('Esc in the editor', 'save', {'saves': ['ABC'], 'typed': ['esc']}, (0, {'ABC.CSM'})),
    ('an 8-letter name', 'save', {'typed': name('ABCDEFGHIJ')}, (1, {'ABCDEFGH.CSM'})),
    ('20 saved: delete one first', 'save', {'saves': TWENTY, 'typed': name('NEW'), 'menu': {1: ['enter']}},
     (1, set(f'{n}.CSM' for n in TWENTY[1:] + ['NEW']))),
    ('20 saved: Esc, then delete the 2nd', 'save',
     {'saves': TWENTY, 'typed': name('NEW'), 'menu': {1: ['esc'], 2: ['down'], 3: ['enter']}},
     (1, set(f'{n}.CSM' for n in TWENTY[:1] + TWENTY[2:] + ['NEW']))),
    ('a file of another size', 'save',
     {'saves': ['ABC'], 'other': ['ODD'], 'typed': name('ODD'), 'menu': {1: ['enter']}},
     (1, {'ABC.CSM', 'ODD.CSM'})),
    ('delete, nothing saved', 'delete', {'other': ['ODD']}, (0, {'ODD.CSM'})),
    ('delete the 2nd', 'delete', {'saves': ['AAA', 'BBB', 'CCC'], 'menu': {1: ['down'], 2: ['enter']}},
     (1, {'AAA.CSM', 'CCC.CSM'})),
    ('delete, Esc', 'delete', {'saves': ['AAA'], 'menu': {1: ['esc']}}, (1, {'AAA.CSM'})),
    ('load, nothing saved', 'load', {}, (1, set())),
    ('load the first', 'load', {'saves': ['AAA', 'BBB'], 'menu': {1: ['enter']}}, (1, {'AAA.CSM', 'BBB.CSM'})),
    ('load, Esc', 'load', {'saves': ['AAA'], 'menu': {1: ['esc']}}, (0, {'AAA.CSM'})),
    ('load the 3rd past another size', 'load',
     {'saves': ['AAA', 'BBB', 'CCC'], 'other': ['ABB'], 'menu': {1: ['down'], 2: ['down'], 3: ['enter']}},
     (1, {'AAA.CSM', 'ABB.CSM', 'BBB.CSM', 'CCC.CSM'})),
    ('load, 21 saved: the 20th', 'load', {'saves': TWENTY + ['T20'], 'menu': {1: ['up'], 2: ['enter']}},
     (1, set(f'{n}.CSM' for n in TWENTY + ['T20']))),
    ('VGA, a short name', 'save', {'vga': True, 'typed': name('ABC')}, (1, {'ABC'})),
    ('VGA, an 8-letter name', 'save', {'vga': True, 'typed': name('ABCDEFGH')}, (1, {'ABCDEFGH.CSM'})),
    ('VGA, over an 8-letter one: yes', 'save',
     {'vga': True, 'saves': ['ABCDEFGH'], 'typed': name('ABCDEFGH'), 'menu': {1: ['enter']}}, (1, {'ABCDEFGH.CSM'})),
    ('VGA, load the 2nd', 'load', {'vga': True, 'saves': ['AAA', 'BBB'], 'menu': {1: ['down'], 2: ['enter']}},
     (1, {'AAA.CSM', 'BBB.CSM'})),
    ('VGA, load, nothing saved', 'load', {'vga': True}, (1, set())),
    ('VGA, delete, Esc', 'delete', {'vga': True, 'saves': ['AAA'], 'menu': {1: ['esc']}}, (1, {'AAA.CSM'})),
]


def save_file(m, rng):
    """A save as 4B7E writes it from this game, the cash changed: the block coded as 0A76 does
    (AX = 0), then the two far blocks (the second through the pointer at 1200h in the first
    one's segment, as the original reads it)."""
    size = m.rw(m.DATA_SEG, 0x11FA)
    block = bytearray(m.ds_read(0x0252, size))

    def word(off):
        return struct.unpack_from('<H', block, off - 0x0252)[0]

    def put(off, value):
        struct.pack_into('<H', block, off - 0x0252, value & 0xFFFF)
    put(0x117E, rng.randrange(0x10000))
    put(0x03A0, 0 if word(0x03A0) == 0x04D4 else 1)
    for off, base in ((0x03A2, 0x05B0), (0x03A4, 0x0DF0), (0x03A6, 0x0F70)):
        put(off, word(off) - base)
    for i in range(size):
        block[i] ^= 0xAA ^ ((size - i) & 0xFF)
    seg = m.rw(m.DATA_SEG, 0x120A)
    first = m.rb(seg, m.rw(m.DATA_SEG, 0x1208), 0x3C)
    second = m.rb(m.rw(seg, 0x1202), m.rw(seg, 0x1200), 0xC4)   # the pointer read through that segment
    return bytes(block) + bytes(first) + bytes(second)


def fill(m, folder, settings, rng):
    for base in settings.get('saves', []):
        with open(os.path.join(folder, base + '.CSM'), 'wb') as f:
            f.write(save_file(m, rng))
    for base in settings.get('other', []):
        with open(os.path.join(folder, base + '.CSM'), 'wb') as f:
            f.write(save_file(m, rng)[:-0x10])


def clear(folder):
    for base in os.listdir(folder):
        os.remove(os.path.join(folder, base))
    os.rmdir(folder)


def run_original(m, specs, entry, settings, vga):
    waits, reads = [0], [0]
    typed, script = settings.get('typed', []), settings.get('menu', {})

    def keys(names, value):
        for n in names:
            m.ds_write(KEY + SC[n], bytes([value]))

    def on_boundary(e):
        service = e['service']
        if service == 0x02C6 and e['caller'] == (0, 0x5185):
            keys(['enter'], 0xFF)                   # a message box waits: Enter
        elif service == 0x02C6:
            waits[0] += 1
            keys(['up', 'down', 'enter', 'esc'], 0)
            keys(script.get(waits[0], ['esc'] if waits[0] > 60 else []), 0xFF)
        elif service in (0x1000, 0x1001, 0x2C27, 0x2C45):
            keys(['esc', 'enter'], 0)
        elif service == 0x2C35:                     # the VGA message box's key: Enter
            keys(['enter'], 0xFF)
        elif service == 0x37AC:
            key = typed[reads[0]] if reads[0] < len(typed) else 0x0D
            reads[0] += 1
            if key == 'esc':
                keys(['esc'], 0xFF)
                type_key(m, 0x1B)
            else:
                type_key(m, ord(key) if isinstance(key, str) else key)
        elif service == 0xE038:
            keys(['esc'], 0)

    recorder = Recorder(m, specs, on_boundary, chunky=vga).install()

    def release_before(uc, addr, size, user):       # a message box first waits for Enter/Esc up
        if not recorder.pending and held(m, 'esc', 'enter'):
            keys(['esc', 'enter'], 0)

    def release_after(uc, addr, size, user):
        if not recorder.pending:
            keys(['enter'], 0)

    closed = [False]

    def landed(uc, addr, size, user):
        closed[0] = True

    m.uc.hook_add(UC_HOOK_CODE, release_before, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, release_after, None, BASE + 0x5195, BASE + 0x5195)
    m.uc.hook_add(UC_HOOK_CODE, landed, None, BASE + 0xFFFE, BASE + 0xFFFE)
    out = m.call(0, ENTRY[entry], stack=(0xFFFE,), si=0, max_instr=2_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    carry = m.r(UC_X86_REG_EFLAGS) & 1
    if entry == 'load':
        status = 2 if closed[0] else carry
    else:
        status = 1 + carry if closed[0] else 0
    return recorder, status, reads[0], waits[0], out


def code_block_cases(lib, fails):
    """0A76 called directly."""
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    rng = random.Random(0x0A76)
    spans = regions(m)
    ds_base = m.DATA_SEG << 4
    for i in range(48):
        size = [0xFA8, 0xFA8, 1, 0x40, 0x150, 0x300][i % 6]
        m.ds_write(0x11FA, struct.pack('<H', size))
        m.ds_write(0x0252, bytes(rng.randrange(256) for _ in range(min(size + 8, 0xFA8))))
        player = [0x04D4, 0x0508, 0, 1, rng.randrange(0x10000)][i % 5]
        m.ds_write(0x03A0, struct.pack('<HHHH', player, *(rng.randrange(0x10000) for _ in range(3))))
        m.ds_write(0x04C6, struct.pack('<H', rng.randrange(0x10000)))
        ax = [0, 0xFFFF, 1, 0x8000][(i // 6) % 4]
        g, mem, planes = make_game(m)
        m.call(0, 0x0A76, ax=ax)
        lib.savegame_code_block(ctypes.byref(g), ax)
        CASES += 1
        error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
        if error:
            fails.append(f'0A76 case {i} (size {size:X}, AX {ax:04X}, player {player:04X}): memory {error}')
            return


def run(ctx):
    global CASES
    lib = ctx.lib
    for f in ('game_menu_action', 'savegame_load'):
        getattr(lib, f).restype = ctypes.c_int
    lib.savegame_code_block.restype = None
    fails = []
    code_block_cases(lib, fails)
    if fails:
        return fails
    with gzip.open(os.path.join(capture.CAPDIR, 'frameloop.pkl.gz'), 'rb') as f:
        recording = pickle.load(f)
    rng = random.Random(0x4B7E)
    outcomes = []
    for label, entry, settings, (expected, expected_files) in SCENARIOS:
        vga = settings.get('vga', False)
        folder = tempfile.mkdtemp(prefix='termsave')
        try:
            m = capture.restore(recording[0])
            fill(m, folder, settings, rng)
            m.ds_write(KEY, bytes(128))
            player = m.rw(m.DATA_SEG, 0x03A0)
            flags = m.ds_read(player + 0x0E, 1)[0]
            m.ds_write(player + 0x0E, bytes([flags & 0xFE if settings.get('foot') is False else flags | 1]))
            if vga:
                m.ds_write(FACILITY_SCREEN, b'\x01')
                m.vga.set_mode(0x13, clear=False)
            m.wb(dosemu.LOAD_SEG, 0xFFFE, b'\x90')     # where a closing action returns: NOP, then the end
            if 'no' in settings:                    # the "overwrite?" menu's No pointed elsewhere
                m.ds_write(0x778E, struct.pack('<H', settings['no']))
            specs = COMMON + (VGA if vga else EGA)
            stub_all(m, specs)
            g, mem, planes = make_game(m)
            screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
            palette = ctypes.create_string_buffer(768)
            files = Files(m, record=False)
            m.game_dir = folder
            spans = regions(m)
            ds_base = m.DATA_SEG << 4
            trace = traced(m)
            written = []
            dos = m._dos

            def recording_dos(m=m, dos=dos, written=written):
                if m.ax() >> 8 == 0x40:
                    cx = m.r(UC_X86_REG_CX)
                    written.append(bytes(m.rb(m.r(UC_X86_REG_DS), m.r(UC_X86_REG_DX), cx)) if cx else b'')
                return dos()
            m._dos = recording_dos
            set_clock(lib, m)
            recorder, status, reads, waits, _ = run_original(m, specs, entry, settings, vga)
            after = set(os.listdir(folder))
            CASES += 1
            if status != expected or after != expected_files:
                fails.append(f'{label}: the script did not reach what it tests (status {status}, files {sorted(after)})')
                continue
            outcomes.append(f'{label}: {status}, {len(after)} files')
            events = [e for e in trace if e[0] == 'int' and e[1] == 0x21]
            replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen if vga else None)
            writes = iter(written)

            def check(n, r, index, writes=writes, g=g):
                if r.ax >> 8 != 0x40:
                    return None
                want = next(writes, None)
                got = ctypes.string_at(g.mem + (r.ds << 4) + r.dx, r.cx) if r.cx else b''
                if got != want:
                    at = next((i for i in range(min(len(got), len(want or b''))) if got[i] != want[i]), None)
                    return f'write to {r.bx}: C wrote other bytes (first difference at {at})'
                return None

            machine = MachineReplay(g, mem, planes, events, video=False, check=check)

            @MENU_CALL
            def menu_call(gp, op, a, b, user):
                return -1 if replay.serve(op, a if op == 0x02C6 else 0, 0) else 0

            menu = MenuPlatform(menu_call, None)

            def keyb(offset, g=g):
                return ctypes.c_uint8.from_address(g.ds + offset)

            @TEXT_POLL
            def text_poll(gp, phase, ticks, user):
                if vga:
                    return replay.serve((0x2C27, 0x2C35, 0x2C45)[phase])
                if phase == 0:
                    keyb(KEY + SC['esc']).value = keyb(KEY + SC['enter']).value = 0
                    return 0
                if phase == 2:
                    keyb(KEY + SC['enter']).value = 0
                    return 0
                return replay.serve(0x02C6, ticks)

            text = TextPlatform(text_poll, None)

            @RESOURCE
            def resource(gp, service, a, b, user):
                return replay.serve(service, a, b)

            resources = Resources(resource, None)

            @KEY_POLL
            def key_poll(gp, user):
                return replay.serve(0x37AC if not keyb(KEY + SC['esc']).value else 0xE038)

            keyboard = KeyboardPlatform(key_poll, None)
            ratings = RatingsServices(ctypes.addressof(resources), ctypes.addressof(files.host),
                                      ctypes.addressof(keyboard), ctypes.addressof(screen), ctypes.addressof(palette))
            menus = GameMenuServices(ctypes.addressof(menu), ctypes.addressof(text), ctypes.addressof(files.host), None,
                                     ctypes.addressof(ratings), ctypes.addressof(machine.services))
            services = SaveGameServices(ctypes.addressof(menus), ctypes.addressof(machine.services))
            if entry == 'load':
                got = lib.savegame_load(ctypes.byref(g), ctypes.byref(services))
            else:                                   # as the game menu runs the option
                got = lib.game_menu_action(ctypes.byref(g), ENTRY[entry], ctypes.byref(menus))
            problem = replay.finished() or machine.finished()
            if got != status or problem:
                fails.append(f'{label}: C status {got}, original {status}; {problem}')
            else:
                error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
                if error:
                    fails.append(f'{label}: at the end, memory {error}')
                elif vga and screen.raw != bytes(m.vga.chunky):
                    fails.append(f'{label}: at the end, the mode-13h screen differs')
                else:
                    compare(label, mem, planes, m, spans, fails)
        finally:
            clear(folder)
        if fails:
            return fails
    print('    savegame: ' + '; '.join(outcomes))
    return fails
