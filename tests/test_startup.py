"""The program's start-up (src/startup.c) against the original.

The argument scanner of the run-time library, called directly from the in-game snapshot with
random registers: FA19, then F8FC (the count) and F97A until its carry, on random command
tails in the PSP (switches, separators, blanks, quotes of other characters, a CR or a NUL at
the end) and on tails in the data segment (DS:EA6A not FFFFh), with the character sets made
random too (counts of 0 keep the flag before the scan); FA2C on strings in either case and
F8E0 on random AX. Every register is compared after each call, and the arithmetic flags
where the routine leaves them (FA2C, F8E0; CF for F97A), the memory at the end.

The options 0413 on command tails: each option in either case, several, separated in each
way, bad ones (printed through DOS, INT 21h replayed by tests/machine.py, and the program
ends: ADD SP,2 / RETF onto a NOP the test places), link without and with a port (the link's
set-up 151B:020F a stubbed boundary).
"""
import ctypes
import os
import random
import sys

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EFLAGS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import BASE, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from machine import REGS, CpuRegs, MachineReplay, traced  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_imageload import Files, regions  # noqa: E402

CASES = 0
ARITH = 0x08D5   # OF SF ZF AF PF CF
PROGRAM_CALL = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_uint16,
                                ctypes.POINTER(CpuRegs), ctypes.c_void_p)


class ProgramServices(ctypes.Structure):
    _fields_ = [('machine', ctypes.c_void_p), ('call', PROGRAM_CALL), ('user', ctypes.c_void_p)]


WORDS = ['vga', 'EGA', 'none', 'IbmSound', 'adlib', 'x', 'ab', 'link', 'com2', '1', 'longer.word']
GLUE = [' ', '  ', '\t', ',', ';', '+', '/', ' /', ', ', ' ,', '', '"', "'", '-']


def tail(rng):
    text = ''.join(rng.choice(GLUE) + rng.choice(WORDS) for _ in range(rng.randrange(0, 6)))
    text += rng.choice(['', ' ', ',', '/', '\t'])
    data = text.encode()[:120]
    end = rng.choice([b'\r', b'\r', b'\0'])
    return data + end + bytes(rng.randrange(256) for _ in range(6))


def scanner_cases(lib, fails):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    rng = random.Random(0xF8FC)
    spans = regions(m)
    ds_base = m.DATA_SEG << 4
    psp = m.rw(m.DATA_SEG, 0xEA6E)
    base_sets = m.ds_read(0xEA52, 0x16)
    for case in range(160):
        m.ds_write(0xEA52, base_sets)
        if case % 4 == 3:                          # other character sets, counts 0 .. 3
            for at, count_at in ((0x8400, 0xEA54), (0x8410, 0xEA5C), (0x8420, 0xEA63)):
                count = rng.choice([0, 1, 2, 3])
                m.ds_write(at, bytes(rng.choice(b' \t,;+/-"x') for _ in range(4)))
                m.ds_write(count_at, count.to_bytes(2, 'little') + at.to_bytes(2, 'little'))
        text = tail(rng)
        in_data = case % 5 == 4
        if in_data:                                # the tail in the data segment
            m.ds_write(0x8500, text)
        else:
            m.wb(psp, 0x80, bytes([len(text)]) + text)
        g, mem, planes = make_game(m)

        def regs():
            return {'ax': rng.randrange(0x10000), 'bx': rng.randrange(0x10000), 'cx': rng.randrange(0x10000),
                    'dx': rng.randrange(0x10000), 'si': 0x8600, 'di': rng.randrange(0x10000),
                    'bp': rng.randrange(0x10000), 'ds': m.DATA_SEG, 'es': rng.choice([m.DATA_SEG, psp])}

        steps = []
        if in_data:
            m.ds_write(0xEA68, (0x8500).to_bytes(2, 'little') + m.DATA_SEG.to_bytes(2, 'little'))
            m.ds_write(0xEA6C, (0x8500).to_bytes(2, 'little'))
            ctypes.memmove(g.ds + 0xEA68, m.ds_read(0xEA68, 6), 6)
        else:
            steps.append(('reset', 0xFA19, 0))
        steps.append(('count', 0xF8FC, 0))
        steps += [('next', 0xF97A, 0x0001)] * 10
        for k, (name, address, checked) in enumerate(steps):
            r = regs()
            r['si'] = 0x8600 + 0x20 * k                # each argument to its own buffer
            out = m.call(0, address, **r)
            flags = m.r(UC_X86_REG_EFLAGS) & 0xFFFF
            c = CpuRegs(**r, flags=0x0002)
            if name == 'reset':
                lib.args_reset(ctypes.byref(g))
            elif name == 'count':
                lib.args_count(ctypes.byref(g), ctypes.byref(c))
            else:
                lib.args_next(ctypes.byref(g), ctypes.byref(c))
            CASES += 1
            where = f'case {case} {text[:40]!r}: {name} {address:04X}'
            if name != 'reset':
                wrong = [k for k in REGS if k != 'flags' and getattr(c, k) != out[k]]
                if wrong:
                    fails.append(where + ': ' + ', '.join(f'{k} C {getattr(c, k):04X} original {out[k]:04X}' for k in wrong))
                    return
                if (c.flags ^ flags) & checked:
                    fails.append(f'{where}: flags C {c.flags:04X}, original {flags:04X}')
                    return
            if name == 'next' and flags & 1:
                break
        error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
        if error:
            fails.append(f'case {case} {text[:40]!r}: memory {error}')
            return
    # FA2C and F8E0
    g, mem, planes = make_game(m)
    for case in range(300):
        a = rng.choice(WORDS + ['', 'VGA', 'vGa', 'ega', 'Adlib', '@[`{', 'none ']).encode()
        b = rng.choice([a, a.upper(), a.lower(), a.swapcase(), a + b'x', a[:-1], b'vga', b'']) if rng.random() < 0.8 \
            else bytes(rng.randrange(1, 256) for _ in range(rng.randrange(4)))
        a = a.replace(b'\0', b'') + b'\0'
        b = b.replace(b'\0', b'') + b'\0'
        m.ds_write(0x8700, a)
        m.ds_write(0x8780, b)
        ctypes.memmove(g.ds + 0x8700, a, len(a))
        ctypes.memmove(g.ds + 0x8780, b, len(b))
        r = {'ax': rng.randrange(0x10000), 'bx': rng.randrange(0x10000), 'cx': rng.randrange(0x10000),
             'dx': rng.randrange(0x10000), 'si': 0x8700, 'di': 0x8780, 'bp': rng.randrange(0x10000),
             'ds': m.DATA_SEG, 'es': m.DATA_SEG}
        for name, address in (('strings', 0xFA2C), ('chars', 0xF8E0)):
            if name == 'chars':
                r['ax'] = rng.choice([rng.randrange(0x10000), (rng.randrange(0x60, 0x7C) << 8) | rng.randrange(0x40, 0x80)])
            out = m.call(0, address, **r)
            flags = m.r(UC_X86_REG_EFLAGS) & 0xFFFF
            c = CpuRegs(**r, flags=0x0002)
            if name == 'strings':
                lib.string_compare_nocase(ctypes.byref(g), ctypes.byref(c))
            else:
                lib.char_compare_nocase(ctypes.byref(c))
            CASES += 1
            wrong = [k for k in REGS if k != 'flags' and getattr(c, k) != out[k]]
            if wrong or (c.flags ^ flags) & ARITH:
                fails.append(f'{name} {a!r} / {b!r} AX {r["ax"]:04X}: ' + ', '.join(
                    f'{k} C {getattr(c, k):04X} original {out[k]:04X}' for k in wrong) + f' flags C {c.flags:04X} original {flags:04X}')
                return


OPTIONS = [
    # command tail, what must happen (sound, VGA, link, ends)
    ('', (1, None, 0, False)),
    ('vga', (1, 0xFF, 0, False)),
    ('EGA', (1, 0, 0, False)),
    ('none', (1, None, 0, False)),
    ('IbmSound', (1, None, 0, False)),
    ('adlib', (2, None, 0, False)),
    ('SBLASTER', (4, None, 0, False)),
    ('ega vga', (1, 0xFF, 0, False)),
    ('vga,none;adlib+sblaster', (4, 0xFF, 0, False)),
    ('  ega\t adlib ', (2, 0, 0, False)),
    ('bad', (1, None, 0, True)),
    ('/vga', (1, None, 0, True)),
    ('vga bad', (1, 0xFF, 0, True)),
    ('vgaa', (1, None, 0, True)),
    ('link', (1, None, 0xFF, True)),
    ('link com2', (1, None, 0xFF, False)),
    ('com4 link ega', (1, 0, 0xFF, False)),
    ('com1', (1, None, 0, False)),
    ('a,,b', (1, None, 0, True)),
]


def options_cases(lib, fails):
    global CASES
    lib.startup_options.restype = ctypes.c_int
    outcomes = []
    for text, (sound, vga, link, ends) in OPTIONS:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        psp = m.rw(m.DATA_SEG, 0xEA6E)
        tail_bytes = b' ' + text.encode() if text else b''
        m.wb(psp, 0x80, bytes([len(tail_bytes)]) + tail_bytes + b'\r')
        m.ds_write(0x01DE, b'\0')
        m.ds_write(0xADD0, b'\x77')                # neither 0 nor FF: what an option sets shows
        specs = [Routine(0x151B, 0x020F, far=True, stub=b'\xcb')]
        stub_all(m, specs)
        m.wb(dosemu.LOAD_SEG, 0xFFFE, b'\x90')
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        trace = traced(m)
        recorder = Recorder(m, specs, lambda entry: None).install()
        ended = [False]
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: ended.__setitem__(0, True), None, BASE + 0xFFFE, BASE + 0xFFFE)
        m.call(0, 0x0413, stack=(0xFFFE, dosemu.LOAD_SEG))
        CASES += 1
        got = (m.rw(m.DATA_SEG, 0xA773), m.ds_read(0xADD0, 1)[0], m.ds_read(0x01DE, 1)[0], ended[0])
        want = (sound, 0x77 if vga is None else vga, link, ends)
        if got != want:
            fails.append(f'options {text!r}: the original did not do what the case tests: {got}')
            return
        outcomes.append(f'{text!r}: {"ends" if ends else f"sound {sound}"}')
        events = [e for e in trace if e[0] == 'int' and e[1] == 0x21]
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)
        machine = MachineReplay(g, mem, planes, events, video=False)

        @PROGRAM_CALL
        def call(gp, seg, off, regs, user):
            return -1 if replay.serve(off) else 0

        services = ProgramServices(ctypes.addressof(machine.services), call, None)
        status = lib.startup_options(ctypes.byref(g), ctypes.byref(services))
        problem = replay.finished() or machine.finished()
        if status != int(ends) or problem:
            fails.append(f'options {text!r}: C status {status}, original {int(ends)}; {problem}')
            return
        error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
        if error:
            fails.append(f'options {text!r}: memory {error}')
            return
    print('    startup options: ' + '; '.join(outcomes))


def run(ctx):
    lib = ctx.lib
    for name in ('args_reset', 'args_count', 'args_next', 'string_compare_nocase', 'char_compare_nocase'):
        getattr(lib, name).restype = None
    fails = []
    scanner_cases(lib, fails)
    if not fails:
        options_cases(lib, fails)
    return fails
