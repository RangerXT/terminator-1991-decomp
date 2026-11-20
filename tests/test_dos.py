"""The DOS file library (src/dos.c) against the original 0000:F63F .. F8D5, through the machine
replay (tests/machine.py), from the in-game snapshot.

Sequences of calls run in the emulator, then in C against the replayed interrupts, the
registers compared after every call (all of them, and CF / ZF): open and read a game file
(F80F, F7AD with its flags, F82B to the end and with CX = 0, F770), create, write and delete
a file (F77C with and without 400h, F84D, F744, F7AD create / truncate / fail-if-exists),
errors (missing files and paths, bad handles), find first / next (F6B3 / F6E8, a trailing
backslash cut and put back), the current directory (F6AC), the drive letter (F738), the
path helpers (F714, F754), printing (F63F), a file loaded whole (FACE), the read and close of
segment 11BC (10CB, 10C6). Files the tests create are named ZZ*.TMP and go
to a scratch folder, never the game folder.
"""
import ctypes
import os
import random
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from machine import REGS, CpuRegs, MachineReplay, traced  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402

CASES = 0
NAME = 0x8200      # file names, patterns, buffers in the data segment
BUFFER = 0x8300
DTA = 0x8280

# (C function, original address, flags to compare)
FUNCTIONS = {
    'print': ('dos_print', 0xF63F, 0x01), 'strip': ('dos_strip_backslash', 0xF714, 0x41),
    'drive': ('dos_drive_letter', 0xF738, 0x41), 'add': ('dos_add_backslash', 0xF754, 0),
    'cwd': ('dos_current_directory', 0xF6AC, 0x01), 'first': ('dos_find_first', 0xF6B3, 0x41),
    'next': ('dos_find_next', 0xF6E8, 0x41), 'delete': ('dos_delete', 0xF744, 0x01),
    'close': ('dos_close', 0xF770, 0x01), 'create': ('dos_create', 0xF77C, 0x01),
    'open': ('dos_open', 0xF7AD, 0x01), 'openmode': ('dos_open_mode', 0xF80F, 0x01),
    'read': ('dos_read', 0xF82B, 0x41), 'write': ('dos_write', 0xF84D, 0x41),
    'load': ('dos_load_file', 0xFACE, 0x01),
    'close11bc': ('dos_close_handle', 0x10C6, 0x01), 'read11bc': ('dos_read_at_si', 0x10CB, 0x01),
}
SEGMENT = {'close11bc': 0x11BC, 'read11bc': 0x11BC}


def scratch_files(m, folder):
    lookup = m._path

    def path(name):
        base = os.path.basename(name.replace('\\', '/')).upper()
        return os.path.join(folder, base) if base.startswith('ZZ') else lookup(name)
    m._path = path


def run(ctx):
    global CASES
    lib = ctx.lib
    for name, _, _ in FUNCTIONS.values():
        getattr(lib, name).restype = ctypes.c_int if name not in ('dos_strip_backslash', 'dos_add_backslash') else None
    rng = random.Random(0xF63F)
    folder = tempfile.mkdtemp(prefix='termdos')
    fails = []

    def text(s):
        return s.encode() + b'\0'

    sequences = [
        ('read a file', [('name', text('font.pck')), ('openmode', {'ax': 0x00}), ('read', {'cx': 0x100}),
                         ('read', {'cx': 0}), ('read', {'cx': 0x8000}), ('read', {'cx': 0x8000}), ('close', {})]),
        ('open by flags', [('name', text('font.pck')), ('open', {'ax': 0x0000}), ('close', {}),
                           ('open', {'ax': 0x0502}), ('name', text('zznone.tmp')), ('open', {'ax': 0x0000}),
                           ('open', {'ax': 0x0102}), ('close', {}), ('open', {'ax': 0x0502}), ('open', {'ax': 0x0202}),
                           ('close', {}), ('delete', {})]),
        ('create, write, delete', [('name', text('zzfile.tmp')), ('create', {'ax': 0x0000}), ('fill', 0x40),
                                   ('write', {'cx': 0x40}), ('write', {'cx': 0}), ('close', {}),
                                   ('create', {'ax': 0x0400}), ('delete', {}), ('create', {'ax': 0x0400}),
                                   ('close', {}), ('delete', {}), ('delete', {})]),
        ('errors', [('name', text('zzmiss.tmp')), ('openmode', {'ax': 0x00}), ('name', text('nodir\\zz.tmp')),
                    ('create', {'ax': 0}), ('close', {'bx': 0x55}), ('read', {'bx': 0x55, 'cx': 4}),
                    ('write', {'bx': 0x55, 'cx': 4})]),
        ('find', [('name', text('*.img')), ('first', {'ax': 0}), ('next', {}), ('next', {}), ('next', {}),
                  ('name', text('*.zzz')), ('first', {'ax': 0}), ('name', text('nodir\\*.*')), ('first', {'ax': 0}),
                  ('name', text('*.pck\\')), ('first', {'ax': 0x10}), ('next', {})]),
        ('directory', [('drive', {'ax': 0x1234}), ('drive', {'ax': 0xAB00}), ('cwd', {'ax': 0x55AA, 'dx': 0x1E42})]),
        ('paths', [('name', text('C:\\')), ('strip', {}), ('name', text('AB\\')), ('strip', {}), ('name', text('A')),
                   ('strip', {}), ('name', text('XYZ')), ('strip', {}), ('name', text('X:\\DIR\\')), ('strip', {}),
                   ('name', text('DIR')), ('add', {}), ('name', text('DIR\\')), ('add', {}), ('name', text('C:')),
                   ('add', {}), ('name', text('')), ('add', {})]),
        ('print', [('name', text('a line$')), ('print', {})]),
        ('11BC read and close', [('name', text('font.pck')), ('openmode', {'ax': 0x00}), ('read11bc', {'cx': 0x80}),
                                 ('read11bc', {'cx': 0}), ('close11bc', {}), ('read11bc', {'bx': 0x55, 'cx': 4}),
                                 ('close11bc', {'bx': 0x55})]),
        ('a file loaded whole', [('name', text('font.pck')), ('load', {'dx': NAME, 'es': 0x9000, 'bx': 0x10}),
                                 ('name', text('zzmiss.tmp')), ('load', {'dx': NAME, 'es': 0x9000, 'bx': 0})]),
    ]
    for label, steps in sequences:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        scratch_files(m, folder)
        g, mem, planes = make_game(m)
        trace = traced(m)
        outs, inputs, handle = [], [], [0]
        for step, arg in steps:
            if step == 'name':
                m.ds_write(NAME, arg + bytes(16))
                inputs.append(('mem', NAME, arg + bytes(16)))
                continue
            if step == 'fill':
                data = bytes(rng.randrange(256) for _ in range(arg))
                m.ds_write(BUFFER, data)
                inputs.append(('mem', BUFFER, data))
                continue
            regs = {'ax': rng.randrange(0x10000), 'bx': handle[0], 'cx': rng.randrange(0x10000),
                    'dx': rng.randrange(0x10000), 'si': NAME, 'di': DTA, 'bp': rng.randrange(0x10000),
                    'ds': m.DATA_SEG, 'es': m.DATA_SEG}
            if step in ('read', 'write'):
                regs['si'] = BUFFER
            regs.update(arg)
            out = m.call(SEGMENT.get(step, 0), FUNCTIONS[step][1], **regs)
            out['flags'] = m.r(dosemu.UC_X86_REG_EFLAGS) & 0xFFFF
            if step in ('openmode', 'open', 'create', 'load') and not out['flags'] & 1:
                handle[0] = out['bx']
            inputs.append((step, regs))
            outs.append(out)
        replay = MachineReplay(g, mem, planes, trace)
        n = 0
        for item in inputs:
            if item[0] == 'mem':
                ctypes.memmove(g.ds + item[1], item[2], len(item[2]))
                continue
            step, regs = item
            function, address, checked = FUNCTIONS[step]
            r = CpuRegs(**{k: regs[k] for k in REGS if k != 'flags'}, flags=0x0002)
            if step in ('strip',):
                getattr(lib, function)(ctypes.byref(g), ctypes.byref(r))
                status = 0
            elif step == 'add':
                lib.dos_add_backslash(ctypes.byref(g), regs['ds'], regs['si'])
                status = 0
            else:
                status = getattr(lib, function)(ctypes.byref(g), ctypes.byref(replay.services), ctypes.byref(r))
            out = outs[n]
            n += 1
            CASES += 1
            where = f'{label}, step {n} ({step} {address:04X})'
            problem = replay.errors[0] if replay.errors else ''
            if status or problem:
                return [f'{where}: status {status}; {problem}']
            if step != 'add':
                wrong = [k for k in REGS if k != 'flags' and getattr(r, k) != out[k]]
                if wrong:
                    return [f'{where}: ' + ', '.join(f'{k} C {getattr(r, k):04X} original {out[k]:04X}' for k in wrong)]
                if (r.flags ^ out['flags']) & checked:
                    return [f'{where}: flags C {r.flags:04X}, original {out["flags"]:04X}']
        problem = replay.finished()
        if problem:
            return [f'{label}: {problem}']
        compare(label, mem, planes, m, regions(m), fails)
        for handle in list(m.files):                  # files a sequence left open, so the folder can go
            m.files.pop(handle)[0].close()
        if fails:
            return fails
    for name in os.listdir(folder):
        os.remove(os.path.join(folder, name))
    os.rmdir(folder)
    return fails
