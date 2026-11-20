"""The sound layer (src/soundlayer.c) against the original 0000:EFA0 .. F4DB, 89F0, 8A41,
8BA2, 8C13, 8C33, 8C96, and the C library's 32-bit division FAF3 / FAF7 / FAFC / FB01.

Direct calls from the in-game snapshot with random registers (and stack arguments for the
library's wrappers). The card is a model on the emulator's ports (SoundBlaster below): the
DSP's reset, read, write, identification (E0h) and its interrupt (F2h raises the IRQ, which
the emulator delivers to the program's handler with interrupts enabled), the FM chip's timer
status; or nothing there (every port FFh), an AdLib alone at 388h, a card that echoes + 6 at
+ A. The drivers' entries (101F:0000, 10BB:0000, 0FBA:058F, the 5B67 routines and the far
pointer DS:AA78) are stubs whose hook records every register at the call and returns
scripted AX, DX and carry; C's calls are checked against those (all registers but BP,
which is the stack frame there) and get the same results. Ports, the PIC, the IRQ and DOS
are replayed through tests/machine.py. Compared: the registers after each call (CF where the
routine sets it), the memory, the machine events, the driver calls.
"""
import ctypes
import os
import random
import struct
import sys

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EFLAGS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import difference  # noqa: E402
from machine import REGS, CpuRegs, MachineReplay, traced  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import regions  # noqa: E402
from test_startup import PROGRAM_CALL, ProgramServices  # noqa: E402

CASES = 0
CHECKED = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'ds', 'es')
DRIVERS = [(0x101F, 0), (0x10BB, 0), (0x0FBA, 0x058F), (0x5B67, 0x0786), (0x5B67, 0x08C5), (0x5B67, 0x0895),
           (0x5B67, 0x0915), (0x5B67, 0x070D)]
SONG_SEG = 0x9000


class SoundBlaster:
    """A card at base: the DSP at + 6 (reset), + A (read), + C (write; status bit 7 busy),
    + E (data waiting, bit 7), the FM chip at + 8 / 9 (timer 1's status C0h once started)."""

    def __init__(self, m, base=0x220, irq=5, dsp=True, fm=True, echo=False):
        self.m, self.base, self.irq, self.echo = m, base, irq, echo
        self.queue, self.reset, self.identify, self.last6 = [], False, False, 0
        self.select, self.status = 0, 0
        ports = ([base + 6, base + 0xA, base + 0xC, base + 0xE] if dsp else []) + ([base + 8, base + 9] if fm else [])
        for port in ports:
            m.devices[port] = self

    def read(self, port):
        at = port - self.base
        if at == 0xA:
            return self.last6 if self.echo else (self.queue.pop(0) if self.queue else 0xFF)
        if at == 0xC:
            return 0x7F
        if at == 0xE:
            return 0xFF if self.queue else 0x7F
        if at == 8:
            return self.status | 0x06
        return 0xFF

    def write(self, port, value):
        at = port - self.base
        if at == 6:
            self.last6 = value
            if value & 1:
                self.reset = True
            elif self.reset:
                self.reset, self.queue = False, [0xAA]
        elif at == 0xC:
            if self.identify:
                self.queue.append(~value & 0xFF)
                self.identify = False
            elif value == 0xE0:
                self.identify = True
            elif value == 0xF2 and self.irq is not None:
                self.m.raise_irq(self.irq)
        elif at == 8:
            self.select = value
        elif at == 9 and self.select == 4:
            if value & 0x80:
                self.status = 0
            elif value & 1:
                self.status = 0xC0


class Drivers:
    """The drivers' entries as stubs (RETF): each call's registers kept, AX / DX / CF from
    script(entry, registers)."""

    def __init__(self, m, script):
        self.m, self.script, self.calls = m, script, []
        for seg, off in DRIVERS:
            m.wb(dosemu.LOAD_SEG + seg, off, b'\xcb')
            at = ((dosemu.LOAD_SEG + seg) << 4) + off
            m.uc.hook_add(UC_HOOK_CODE, self.hit, (seg, off), at, at)

    def hit(self, uc, address, size, entry):
        m = self.m
        regs = {name: m.r(m.REG_BY_NAME[name]) for name in CHECKED}
        ax, dx, cf = self.script(entry, regs)
        m.w(m.REG_BY_NAME['ax'], ax)
        m.w(m.REG_BY_NAME['dx'], dx)
        flags = m.r(UC_X86_REG_EFLAGS)
        uc.reg_write(UC_X86_REG_EFLAGS, flags | 1 if cf else flags & ~1)
        self.calls.append((entry, regs, (ax, dx, cf)))


def scripted(rng):
    def script(entry, regs):
        return rng.randrange(0x10000), rng.randrange(0x10000), rng.random() < 0.3
    return script


def fresh():
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.uc.mem_write(0, struct.pack('<HH', 0x0407, dosemu.LOAD_SEG))    # the game's divide handler
    return m


def case(lib, label, address, c_side, fails, setup=None, regs=None, stack=(), irqs=False, script=None,
         flags=0x0001, rng=None, seg=0):
    """One direct call: setup(m), the original at seg:address with regs (random where not
    given) and stack, then c_side(lib, g, services, CpuRegs) -> status."""
    global CASES
    rng = rng or random.Random(address)
    m = fresh()
    if setup:
        setup(m)
    drivers = Drivers(m, script or scripted(rng))
    g, mem, planes = make_game(m)
    spans = regions(m)
    ds_base = m.DATA_SEG << 4
    trace = traced(m)
    given = {'ax': rng.randrange(0x10000), 'bx': rng.randrange(0x10000), 'cx': rng.randrange(0x10000),
             'dx': rng.randrange(0x10000), 'si': rng.randrange(0x10000), 'di': rng.randrange(0x10000),
             'bp': rng.randrange(0x10000), 'ds': m.DATA_SEG, 'es': m.DATA_SEG}
    given.update(regs or {})
    entry_flags = m.r(UC_X86_REG_EFLAGS) & ~0x0300 & 0xFFFF | 2 | (0x0200 if irqs else 0)   # as m.call sets them
    out = m.call(seg, address, stack=stack, irqs=irqs, max_instr=200_000_000, **given)
    out_flags = m.r(UC_X86_REG_EFLAGS) & 0xFFFF
    CASES += 1
    machine = MachineReplay(g, mem, planes, trace, video=False)
    index = [0]
    errors = []

    @PROGRAM_CALL
    def call(gp, cseg, coff, r, user):
        if index[0] >= len(drivers.calls):
            errors.append(f'C called {cseg:04X}:{coff:04X}, the original no more')
            return -1
        entry, want, (ax, dx, cf) = drivers.calls[index[0]]
        index[0] += 1
        got = r.contents
        wrong = [k for k in CHECKED if getattr(got, k) != want[k]]
        if (cseg, coff) != entry or wrong:
            errors.append(f'driver call {index[0]}: C {cseg:04X}:{coff:04X} ' + ', '.join(
                f'{k} {getattr(got, k):04X}/{want[k]:04X}' for k in wrong) + f', original {entry[0]:04X}:{entry[1]:04X}')
            return -1
        got.ax, got.dx = ax, dx
        got.flags = got.flags | 1 if cf else got.flags & 0xFFFE
        return 0

    services = ProgramServices(ctypes.addressof(machine.services), call, None)
    r = CpuRegs(**{k: given[k] for k in REGS if k != 'flags'}, flags=entry_flags)
    status = c_side(lib, g, services, r)
    problem = (errors[0] if errors else '') or machine.finished()
    if not problem and index[0] != len(drivers.calls):
        problem = f'C made {index[0]} of the original {len(drivers.calls)} driver calls'
    where = f'{label} ({seg:04X}:{address:04X})'
    if status or problem:
        fails.append(f'{where}: status {status}; {problem}')
        return
    wrong = [k for k in REGS if k != 'flags' and getattr(r, k) != out[k]]
    if wrong or (r.flags ^ out_flags) & flags:
        fails.append(f'{where}: ' + ', '.join(f'{k} C {getattr(r, k):04X} original {out[k]:04X}' for k in wrong)
                     + (f' flags C {r.flags:04X} original {out_flags:04X}' if (r.flags ^ out_flags) & flags else ''))
        return
    error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
    if error:
        fails.append(f'{where}: memory {error}')


def regs_fn(name, *extra):
    def c_side(lib, g, s, r):
        getattr(lib, name)(ctypes.byref(g), ctypes.c_void_p(s.machine), *extra, ctypes.byref(r))
        return 0
    return c_side


def host_fn(name):
    def c_side(lib, g, s, r):
        return getattr(lib, name)(ctypes.byref(g), ctypes.byref(s), ctypes.byref(r))
    return c_side


def card(**kw):
    def setup(m):
        m.ds_write(0xEA3E, struct.pack('<H', kw.pop('base', 0x220)))
        if kw.get('present', True):
            SoundBlaster(m, **{k: v for k, v in kw.items() if k != 'present'})
    return setup


def song(tempo, instruments=True):
    """A song header at SONG_SEG:0 (instruments at + 6, notes at + 8, tempo + Ch, + 24h)."""
    def setup(m):
        m.wb(SONG_SEG, 0, struct.pack('<6xHHxxh22xH', 0x40 if instruments else 0, 0x80, tempo, 7))
    return setup


def run(ctx):
    lib = ctx.lib
    for name in ('music_driver_init', 'music_driver_close', 'sound_wrapper', 'music_song_start', 'music_load',
                 'sound_init', 'sample_init', 'sound_memory_free', 'sample_stop'):
        getattr(lib, name).restype = ctypes.c_int
    for name in ('sb_dsp_read', 'sb_dsp_write', 'sb_dsp_read_wait', 'sb_dsp_write_wait', 'sb_irq_unmask', 'sb_irq_mask',
                 'sb_irq_handler', 'sb_irq_detect', 'sb_dsp_reset', 'adlib_delay', 'adlib_write', 'adlib_wait_status',
                 'sb_detect', 'music_flag_take', 'long_division'):
        getattr(lib, name).restype = None
    fails = []
    rng = random.Random(0xEFA0)
    sb, none = card(), card(present=False)

    def queued(m):
        card()(m)
        m.devices[0x22A].queue = [0x55]
    simple = [
        ('DSP read, data', 0xEFA0, 'sb_dsp_read', queued), ('DSP read, none waiting', 0xEFA0, 'sb_dsp_read', sb),
        ('DSP read, no card', 0xEFA0, 'sb_dsp_read', none), ('DSP write', 0xEFBE, 'sb_dsp_write', sb),
        ('DSP write, no card', 0xEFBE, 'sb_dsp_write', none), ('DSP read wait', 0xEFDD, 'sb_dsp_read_wait', queued),
        ('DSP read wait, no card', 0xEFDD, 'sb_dsp_read_wait', none), ('DSP write wait', 0xEFF2, 'sb_dsp_write_wait', sb),
        ('DSP reset', 0xF162, 'sb_dsp_reset', sb), ('DSP reset, no card', 0xF162, 'sb_dsp_reset', none),
        ('FM status', 0xF384, 'adlib_wait_status', sb), ('FM write', 0xF3A5, 'adlib_write', sb),
        ('detect: nothing', 0xF2FA, 'sb_detect', none), ('detect: a Sound Blaster', 0xF2FA, 'sb_detect', sb),
        ('detect: DSP, no FM', 0xF2FA, 'sb_detect', card(fm=False)),
        ('detect: AdLib at 388h', 0xF2FA, 'sb_detect', card(base=0x380, dsp=False)),
        ('detect: an echo at + A', 0xF2FA, 'sb_detect', card(echo=True)),
    ]
    for label, address, name, setup in simple:
        for i in range(3):
            case(lib, label, address, regs_fn(name), fails, setup=setup, rng=rng)
            if fails:
                return fails
    for label, address, name in (('FM delay', 0xF3B8, 'adlib_delay'), ('IRQ unmask', 0xF030, 'sb_irq_unmask'),
                                 ('IRQ mask', 0xF048, 'sb_irq_mask')):
        for irq in (2, 5, 7, 9):
            def setup(m, irq=irq):
                card()(m)
                m.ds_write(0xEA40, struct.pack('<H', irq))

            def c_side(lib, g, s, r, name=name):
                getattr(lib, name)(ctypes.byref(g), ctypes.c_void_p(s.machine))
                return 0
            case(lib, f'{label} {irq}', address, c_side, fails, setup=setup, rng=rng, flags=0)
            if fails:
                return fails
    for irq in (2, 3, 5, 7, None):
        case(lib, f'IRQ detection, IRQ {irq}', 0xF05E, regs_fn('sb_irq_detect'), fails, setup=card(irq=irq),
             irqs=True, rng=rng, flags=0)
        if fails:
            return fails
    for handler, irq in ((0xF11C, 3), (0xF13A, 2), (0xF147, 5), (0xF154, 7)):
        def c_side(lib, g, s, r, irq=irq):
            lib.sb_irq_handler(ctypes.byref(g), ctypes.c_void_p(s.machine), irq)
            return 0
        case(lib, f'IRQ {irq} handler', handler, c_side, fails, setup=sb, stack=(dosemu.LOAD_SEG, 0x0202), rng=rng,
             flags=0)
        if fails:
            return fails
    for cf in (False, True):
        def script(entry, regs, cf=cf):
            return (0x1234, 0x5678, cf and regs['bx'] == 0xFFFF)
        case(lib, f'music driver start{", fails" if cf else ""}', 0xF3CA, host_fn('music_driver_init'), fails,
             script=script, rng=rng, flags=0x0041)
        if fails:
            return fails
    case(lib, 'music driver close', 0xF4C1, host_fn('music_driver_close'), fails, rng=rng)
    for flag in (0, 0x2A):
        case(lib, f'music flag {flag:02X}', 0xF4AE, lambda lib, g, s, r: lib.music_flag_take(ctypes.byref(g),
             ctypes.byref(r)) or 0, fails, setup=lambda m, f=flag: m.ds_write(0xEA3C, bytes([f])), rng=rng)
        if fails:
            return fails
    wrappers = [0xF19E, 0xF1A7, 0xF1D8, 0xF1E8, 0xF1FC, 0xF205, 0xF20E, 0xF22B, 0xF23F, 0xF248, 0xF251, 0xF262,
                0xF409, 0xF41C, 0xF42F, 0xF445, 0xF452, 0xF462, 0xF472, 0xF47B, 0xF484, 0xF494, 0xF4A1, 0xF4DB]
    for entry in wrappers:
        for i in range(2):
            args = [rng.randrange(0x10000) for _ in range(5)]

            def c_side(lib, g, s, r, entry=entry, args=args):
                return lib.sound_wrapper(ctypes.byref(g), ctypes.byref(s), entry, ctypes.byref(r),
                                         (ctypes.c_uint16 * 5)(*args))
            case(lib, f'wrapper {entry:04X}', entry, c_side, fails, stack=tuple(args), rng=rng, flags=0x0001)
            if fails:
                return fails
    # the long division: each entry, signs, the 16-bit DIV and its divide error
    entries = ((0xFAF3, 0), (0xFAF7, 1), (0xFAFC, 2), (0xFB01, 3))
    values = [0, 1, 7, 0x8000, 0xFFFF, 0x1234, 0x7FFF]
    for i in range(160):
        address, mode = entries[i % 4]
        pick = lambda: rng.choice(values) if rng.random() < 0.5 else rng.randrange(0x10000)  # noqa: E731
        a_lo, a_hi, b_lo, b_hi = pick(), pick(), pick(), pick()
        if i % 7 == 0:
            b_hi = 0
        if i % 11 == 0:
            a_hi = b_hi = 0
        if i % 13 == 0:
            b_lo = b_hi = 0

        def c_side(lib, g, s, r, mode=mode, a=(a_lo, a_hi, b_lo, b_hi)):
            lib.long_division(mode, *a, ctypes.byref(r))
            return 0
        case(lib, f'long division {a_hi:04X}{a_lo:04X} / {b_hi:04X}{b_lo:04X}', address, c_side, fails,
             stack=(dosemu.LOAD_SEG, a_lo, a_hi, b_lo, b_hi), rng=rng, flags=0)
        if fails:
            return fails
    # the song: tempo, instruments or not, a tempo of 0 (the divide error resumes)
    for tempo, instruments in ((120, True), (-300, True), (0x7FFF, False), (0, True)):
        case(lib, f'song start, tempo {tempo}', 0x8A41, host_fn('music_song_start'), fails,
             setup=song(tempo, instruments), regs={'es': SONG_SEG}, rng=rng, flags=0)   # CF: ADD SP,4's
        if fails:
            return fails
    # 89F0: the song file loaded and started, or not
    def music(sound, room=0x0D74):
        def setup(m):
            m.ds_write(0xA773, struct.pack('<H', sound))
            m.ds_write(0xA743, struct.pack('<H', SONG_SEG))
            m.ds_write(0xA75F, struct.pack('<H', room))
            m.ds_write(0x8800, b'song1.cmf\0zzmissin.cmf\0')
        return setup
    for label, setup, name in (('AdLib', music(2), 0x8800), ('Sound Blaster', music(4), 0x8800),
                               ('PC speaker', music(1), 0x8800), ('a missing song', music(4), 0x880A),
                               ('no room', music(2, room=3), 0x8800)):
        case(lib, f'music load, {label}', 0x89F0, host_fn('music_load'), fails, setup=setup, regs={'dx': name},
             rng=rng, flags=0)
        if fails:
            return fails
    # 8BA2: the sound at start-up
    def startup(sound, block=0, **kw):
        def setup(m):
            m.ds_write(0xA773, struct.pack('<H', sound))
            m.ds_write(0xA75F, struct.pack('<H', block))
            if kw.get('present', True):
                SoundBlaster(m, **{k: v for k, v in kw.items() if k != 'present'})
        return setup
    for label, setup in (('PC speaker', startup(1, present=False)), ('AdLib', startup(2, base=0x380, dsp=False)),
                         ('Sound Blaster, IRQ 7', startup(4, irq=7)), ('Sound Blaster, no IRQ', startup(4, irq=None)),
                         ('a DSP without FM', startup(4, fm=False)), ('no card', startup(4, present=False)),
                         ('the block there', startup(2, block=0x0D74, base=0x380, dsp=False))):
        case(lib, f'sound start-up, {label}', 0x8BA2, host_fn('sound_init'), fails, setup=setup, irqs=True, rng=rng,
             flags=0)
        if fails:
            return fails
    for cf in (False, True):
        case(lib, f'samples start{", no device" if cf else ""}', 0x8C13, host_fn('sample_init'), fails,
             script=lambda entry, regs, cf=cf: (0, 0, cf and entry == (0x5B67, 0x0786)), rng=rng, flags=0)
        if fails:
            return fails
    case(lib, 'music block freed', 0x8C33, host_fn('sound_memory_free'), fails, rng=rng)
    for flag in (0, 0xFF):
        case(lib, f'samples stop {flag:02X}', 0x8C96, host_fn('sample_stop'), fails,
             setup=lambda m, f=flag: m.ds_write(0xA614, bytes([f])), rng=rng, flags=0)
        if fails:
            return fails
    return fails
