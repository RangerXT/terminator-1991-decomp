"""The unreachable routines (src/unreachable.c) against the original, called directly from
the in-game snapshot with random registers and random memory where they read it: 1814,
26DF / 2707, 296A, 43B9, 47A8, 47CE, 47FD and the handler in its bytes (481A), 5622 and its
thunk EF77, 5A6F, 6479, 79F1, 87E2, 950D, B9C6, CA39, EE0C (it hangs when a word matches:
the original's call is stopped there), F5CD, FA10, FA88, 11BC:110E, 1B27 (on the mode-13h
screen), 1E95. Divisions by values that overflow are included: the game's divide handler
resumes after them. Compared: the registers each routine defines (all, except those its C
comment names as not modelled), the arithmetic flags where it leaves them, the memory, the
planes and card, the mode-13h screen, the machine events.
"""
import ctypes
import os
import random
import struct
import sys

from unicorn.x86_const import UC_X86_REG_EFLAGS, UC_X86_REG_SP, UC_X86_REG_SS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import difference  # noqa: E402
from machine import REGS, CpuRegs, MachineReplay, traced  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402

CASES = 0
ARITH = 0x08D5
ALL = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'ds', 'es')


def fresh():
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.uc.mem_write(0, struct.pack('<HH', 0x0407, dosemu.LOAD_SEG))     # the game's divide handler
    return m


def words(rng, n, choices=(0, 1, 0x7FFF, 0x8000, 0xFFFF, 0x64, 0x1E)):
    return [rng.choice(choices) if rng.random() < 0.4 else rng.randrange(0x10000) for _ in range(n)]


def run_case(lib, label, seg, address, c_side, fails, rng, setup=None, regs=None, checked=ALL, flags=0,
             stack=(), far=False, chunky=False, hang=False):
    global CASES
    m = fresh()
    if chunky:
        m.vga.set_mode(0x13, clear=False)
    if setup:
        setup(m, rng)
    g, mem, planes = make_game(m)
    screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
    spans = regions(m)
    ds_base = m.DATA_SEG << 4
    trace = traced(m)
    given = dict(zip(('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp'), words(rng, 7)))
    given.update(ds=m.DATA_SEG, es=m.DATA_SEG)
    given.update(regs or {})
    entry_flags = m.r(UC_X86_REG_EFLAGS) & ~0x0300 & 0xFFFF | 2
    hung = False
    try:
        out = m.call(seg, address, far=far, stack=stack, max_instr=3_000_000 if hang else 200_000_000, **given)
    except RuntimeError:
        if not hang:
            raise
        hung = True
        out = {name: m.r(reg) for name, reg in m.REG_BY_NAME.items()}
    out_flags = m.r(UC_X86_REG_EFLAGS) & 0xFFFF
    CASES += 1
    events = [e for e in trace if not (e[0] in ('in', 'out') and e[1] in (0x3C4, 0x3C5, 0x3CE, 0x3CF))]  # C's EGA model
    machine = MachineReplay(g, mem, planes, events, video=lambda n: n == 0x10)
    r = CpuRegs(**{k: given[k] for k in REGS if k != 'flags'}, flags=entry_flags)
    status = c_side(lib, g, ctypes.byref(machine.services), r, screen, m)
    where = f'{label} ({seg:04X}:{address:04X})'
    problem = machine.finished()
    if (status != (1 if hung else 0)) or problem:
        fails.append(f'{where}: C status {status}, original {"hung" if hung else "returned"}; {problem}')
        return
    if not hung:
        wrong = [k for k in checked if getattr(r, k) != out[k]]
        if wrong or (r.flags ^ out_flags) & flags:
            fails.append(f'{where}: ' + ', '.join(f'{k} C {getattr(r, k):04X} original {out[k]:04X}' for k in wrong)
                         + (f' flags C {r.flags:04X} original {out_flags:04X}' if (r.flags ^ out_flags) & flags else ''))
            return
    error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
    if error:
        fails.append(f'{where}: memory {error}')
        return
    if chunky and screen.raw != bytes(m.vga.chunky):
        first = next(i for i in range(0x10000) if screen.raw[i] != m.vga.chunky[i])
        fails.append(f'{where}: the mode-13h screen differs at {first:04X}')
        return
    compare(where, mem, planes, m, spans, fails)


def plain(name):
    def c_side(lib, g, mc, r, screen, m):
        getattr(lib, name)(ctypes.byref(g), ctypes.byref(r))
        return 0
    return c_side


def with_machine(name):
    def c_side(lib, g, mc, r, screen, m):
        return getattr(lib, name)(ctypes.byref(g), mc, ctypes.byref(r))
    return c_side


def ds_random(*spans):
    """Random bytes at the DS spans (offset, length)."""
    def setup(m, rng):
        for at, n in spans:
            m.ds_write(at, bytes(rng.randrange(256) for _ in range(n)))
    return setup


def model_with_faces(m, rng, faces=None):
    """A model at DS:8000: count at + 2, faces at DS:8100 (+4: vertex count, then offsets
    into the vertex buffer DS:[3CDC]), vertices with random z signs."""
    vb = m.rw(m.DATA_SEG, 0x3CDC)
    m.ds_write(vb, bytes(rng.randrange(256) for _ in range(6 * 16)))
    count = faces if faces is not None else rng.randrange(1, 6)
    m.ds_write(0x8000, struct.pack('<HHHH', 0, count, 0, 0x8100))
    at = 0x8100
    for i in range(count if count else 1):
        n = rng.randrange(1, 5)
        m.ds_write(at, struct.pack('<HHH', 0, 0, n) + b''.join(struct.pack('<H', 6 * rng.randrange(16)) for _ in range(n)))
        at += 6 + 2 * n
    m.ds_write(m.rw(m.DATA_SEG, 0x40E0), bytes(rng.randrange(3) for _ in range(8)))


def run(ctx):
    lib = ctx.lib
    for name in ('unused_timer_restore', 'unused_protection_fail'):
        getattr(lib, name).restype = ctypes.c_int
    fails = []
    rng = random.Random(0x26DF)

    def go(*a, **k):
        run_case(lib, *a, fails=fails, rng=rng, **k)
        return bool(fails)

    for i in range(6):
        if go('plane bits', 0, 0x1814, plain('unused_plane_bits'), flags=ARITH,
              checked=('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'ds', 'es')):
            return fails
    for faces in (1, 3, 5, 2):
        if go(f'faces behind, {faces}', 0, 0x26DF, plain('unused_faces_behind'),
              setup=lambda m, rng, f=faces: model_with_faces(m, rng, f), regs={'bx': 0x8000},
              checked=('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp')):
            return fails
    for i in range(6):
        if go('camera offset', 0, 0x296A, plain('unused_camera_offset'), setup=ds_random((0x8200, 8)),
              regs={'di': 0x8200}):
            return fails
    if go('extras cleared', 0, 0x43B9, plain('unused_extras_clear')):
        return fails
    for name, address in (('scale down', 0x47A8), ('project', 0x47CE), ('scale half', 0x47FD)):
        for i in range(24):
            regs = dict(zip(('ax', 'bx', 'cx'), words(rng, 3, (0, 1, 2, 0x1E, 0x1F, 0x64, 0x63, 0x8000, 0xFFFF, 0x7FFF))))
            if go(f'{name} {regs}', 0, address, plain(f'unused_{name.replace(" ", "_")}'), regs=regs):
                return fails

    # the handler at 481A: entered as the CPU enters it after a fault (IP, CS, flags on the stack)
    for i in range(4):
        def c_side(lib, g, mc, r, screen, m):
            frame = ctypes.c_uint16.from_address(g.mem + (c_side.ss << 4) + c_side.sp)
            frame.value = 0xFF00                         # the IP the fault (m.call's far return) left
            lib.unused_divide_handler(ctypes.byref(g), c_side.ss, c_side.sp, ctypes.byref(r))
            # the frame is on the stack, which the memory comparison leaves out: its IP here
            got = ctypes.c_uint16.from_address(g.mem + (c_side.ss << 4) + c_side.sp).value
            want = m.rw(c_side.ss, c_side.sp)
            return 0 if got == want == 0xFF02 else 2

        def setup(m, rng):
            m.wb(dosemu.BIOS_SEG, 0xFF02, b'\xeb\xfc')    # FF02: JMP FF00, where the call ends
            c_side.ss = m.r(UC_X86_REG_SS)
            # the frame: m.call's far return (IP FF00, CS) below the two words given, as a fault's
            c_side.sp = (m.r(UC_X86_REG_SP) - 8) & 0xFFFF
        if go('the other divide handler', 0, 0x481A, c_side, setup=setup, far=True, stack=(dosemu.BIOS_SEG, 0x0002),
              checked=('ax', 'dx', 'bx', 'cx', 'si', 'di')):
            return fails

    def items(m, rng):
        m.ds_write(0xA38E, bytes([3, 10, 1, 9, 20, 2, 0x22, 5, 4, 0xFF]))
        m.ds_write(0x78DC, bytes([3, 9, 0x22, 0x40, 0x11, 3]))
        m.ds_write(0x78EC, struct.pack('<6H', *(0x8448 + 3 * i for i in range(6))))
        m.ds_write(0x03FC, struct.pack('<H', rng.choice([0, 5, 0x13])))
    for kind in range(6):
        if go(f'drop kind {kind}', 0, 0x5622, plain('unused_drop_kind'), setup=items, regs={'ax': kind}):
            return fails
        if go(f'drop kind {kind}, the thunk', 0, 0xEF77, plain('unused_drop_kind'), setup=items, regs={'ax': kind},
              far=True):
            return fails

    # 5A6F on a real packed block
    import test_unpack
    blocks = [b for i, b in enumerate(test_unpack.bytekiller_blocks()) if i in (0, 3)]
    for label, before, packed in blocks:
        def setup(m, rng, p=packed, b=before):
            m.wb(0x7800, 0x10, b + p)
            m.wb(0x8800, 0, bytes([0xA5]) * 0x8000)
        if go(f'unpack {label}', 0, 0x5A6F, plain('unused_unpack_far'), setup=setup, far=True,
              regs={'ds': 0x7800, 'si': 0x12, 'es': 0x8800, 'di': 0, 'cx': len(packed)},
              checked=('ax', 'si', 'di', 'bp', 'ds', 'es')):
            return fails
    for i in range(6):
        def setup(m, rng):
            ds_random((m.rw(m.DATA_SEG, 0x03A0) + 0x11, 4), (m.rw(m.DATA_SEG, 0x03A0) + 0x2B, 2))(m, rng)
            m.ds_write(0x7D08, b''.join(struct.pack('<H', rng.choice([0, 1, 0xFFFF])) for _ in range(4)))
        if go('marks undone', 0, 0x6479, plain('unused_marks_undo'), setup=setup):
            return fails
    for i in range(4):
        def setup(m, rng):
            vb = m.rw(m.DATA_SEG, 0x3CDC)
            m.ds_write(vb, bytes(rng.randrange(256) for _ in range(6 * 8)))
            m.ds_write(0x8000, struct.pack('<HHH', 0, 0, rng.randrange(1, 8)))
            m.ds_write(0x4B6E, b'\0')
        if go('model turned', 0, 0x79F1, plain('unused_model_turn'), setup=setup,
              regs={'bx': 0x8000, 'ax': rng.randrange(0x400), 'cx': rng.randrange(0x400)},
              checked=('ax', 'bx', 'cx', 'si', 'di', 'bp', 'ds', 'es')):
            return fails
    if go('add 50h', 0, 0x87E2, plain('unused_add_50'), flags=1):
        return fails
    for i in range(12):
        def setup(m, rng):
            m.ds_write(0xAACF, bytes([rng.choice([1, 2, 7]), rng.choice([0, 0xFF]), rng.choice([0, 1])]))
            m.ds_write(0x0B10, struct.pack('<HHHH', rng.randrange(0x10000), rng.randrange(0x10000), 0,
                                           rng.choice([0, 1, 50])))
            for record in (m.rw(m.DATA_SEG, 0x03A0), m.rw(m.DATA_SEG, 0x04BA)):
                if rng.random() < 0.5:                 # near the decoy
                    m.ds_write(record, m.ds_read(0x0B10, 2) + m.ds_read(record + 2, 2) + m.ds_read(0x0B12, 2))
                m.ds_write(record + 0x0E, bytes([rng.choice([0, 2, 3])]))
        if go('decoy step', 0, 0x950D, plain('unused_decoy_step'), setup=setup):
            return fails
    if go('timer vector back', 0, 0xB9C6, with_machine('unused_timer_restore'),
          setup=lambda m, rng: m.ds_write(0xDE48, struct.pack('<HH', 0x1234, 0x5678))):
        return fails
    for i in range(3):
        if go('count up', 0, 0xCA39, plain('unused_count_up'),
              setup=lambda m, rng: m.ds_write(0xE190, struct.pack('<H', rng.randrange(8)))):
            return fails
    for match in (False, True):
        def setup(m, rng, match=match):
            m.ds_write(0xEA34, struct.pack('<H', 2))
            m.ds_write(0xE6E0, b''.join(struct.pack('<H', 0x1000 + i) for i in range(10)))
            m.ds_write(0xE6F6 + 4, struct.pack('<H', 0x1003 if match else 0x2222))
        if go(f'protection failure, {"a match" if match else "none"}', 0, 0xEE0C, with_machine('unused_protection_fail'),
              setup=setup, hang=match, checked=('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp')):
            return fails
    for text in (b'123', b'65535', b'65536', b'0', b'x', b'99999999', b'7a', b''):
        if go(f'decimal {text!r}', 0, 0xF5CD, plain('unused_parse_decimal'),
              setup=lambda m, rng, t=text: m.ds_write(0x8300, t + b' \0'), regs={'si': 0x8300}, flags=ARITH):
            return fails
    if go('arguments restart', 0, 0xFA10, plain('unused_args_restart')):
        return fails
    for value in (0, 7, 10, 65535, 12345):
        if go(f'decimal of {value}', 0, 0xFA88, plain('unused_decimal_backwards'), regs={'ax': value, 'bx': 0x8400}):
            return fails
    for i in range(4):
        if go('translate', 0x11BC, 0x110E, plain('unused_translate'), far=True, setup=ds_random((0x5DC0, 256))):
            return fails
    for di in (0, 0x29, 0x7C7, 0x2800, 0x3000):
        def c_side(lib, g, mc, r, screen, m):
            lib.unused_text3_vga(ctypes.byref(g), screen, ctypes.byref(r))
            return 0

        def setup(m, rng):
            m.ds_write(0x8500, bytes([rng.randrange(0, 0x0C) for _ in range(3)]))
            m.ds_write(0x468C, bytes([rng.randrange(256)]))
            m.ds_write(0xADDC, struct.pack('<H', 0xA000))
        if go(f'three characters at {di:04X}', 0x11BC, 0x1B27, c_side, setup=setup, far=True, chunky=True,
              regs={'di': di, 'si': 0x8500}):
            return fails
    for slot in (1, 3):
        for flag in (0, 0xFF):
            if go(f'weapon icon {slot}, flag {flag:02X}', 0x11BC, 0x1E95, plain('unused_weapon_icon_redraw'),
                  setup=lambda m, rng, f=flag: (m.ds_write(0x1150, bytes([f])), m.ds_write(0x0366, b'\0')),
                  regs={'cx': slot}, checked=('ax', 'bx', 'cx', 'bp', 'ds', 'es')):
                return fails
    return fails
