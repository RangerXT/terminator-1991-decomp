"""The FM music driver (src/fmdrv.c) against the original segment 10BB: its functions
(10BB:0000 by BX), its timer interrupt handler (0C83) and its keyboard one (0CF3).

One machine from the in-game snapshot with an OPL2 at 388h (the FM chip of SoundBlaster in
test_soundlayer: timer 1's status C0h once started). The original runs a script of calls on
it: the port base, the set-up (its loop count between timer interrupts measured with three
interrupts raised in its loops), the status byte at DS:EA3C, then three songs, each with
its instruments, the driver clock, transposition, play, and timer interrupts until it ends,
with pauses, a busy driver, a second play, stops and resets in between; the keyboard
handler; the shut-down. The songs: the game's SONG1.CMF, and two made here that reach what
it does not: drums (controller 67h), pitch bends past the octave both ways, more notes than
voices, program changes past the instrument count, running status, the Ax / Dx / Ex events,
SysEx, F2 / F3, meta events, the end by FFh 2Fh and by FCh.

The C side keeps its own copy of the memory from the start and makes each call on it;
MachineReplay checks every port access against the original's (the OPL's registers and
values, the timer, the PIC) and hands over the interrupts. Where the timer handler passes
the interrupt on to the old INT 8 (the BIOS's here: INT 1Ch is left to the BIOS too), the C
side runs it through the replay as often as fmdrv_timer says. Compared after each call: the
registers the call returns (AX, DX, the carry), and the memory (all of it but the stacks).
"""
import ctypes
import os
import random
import struct
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from machine import CpuRegs, MachineReplay, traced  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import regions  # noqa: E402
from test_soundlayer import SoundBlaster, fresh  # noqa: E402

CASES = 0
DRV = 0x10BB
SONG_SEG = 0x9000
BIOS = dosemu.BIOS_SEG


def vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.insert(0, 0x80 | (n & 0x7F))
        n >>= 7
    return bytes(out)


def made_song(rng, end_with_fc=False):
    """A CMF file: 20 instruments, events that reach every path of the driver."""
    instruments = bytes(rng.randrange(256) for _ in range(20 * 16))
    ev = bytearray()

    def at(delay, *data):
        ev.extend(vlq(delay) + bytes(data))
    for ch in range(11):
        at(0, 0xC0 | ch, rng.randrange(60))                   # programs, some past the count
    for i in range(12):                                         # more notes than voices
        at(rng.choice((0, 1, 3)), 0x90 | (i % 9), 30 + 4 * i, 40 + 5 * i)
    at(5, 0x40, 0)                                              # running status: channel 0 again
    at(2, 0x80, 30, 0)
    at(0, 0x90, 34, 0)                                          # note on, velocity 0: off
    at(200, 0xB2, 0x68, 60)                                     # bend up (a two-byte delay)
    at(1, 0x92, 127, 90)                                        # past the top of the scale
    at(3, 0x92, 120, 90)
    at(1, 0xB3, 0x69, 70)                                       # bend down
    at(1, 0x93, 0, 70)                                          # below the bottom
    at(1, 0x93, 2, 70)
    at(1, 0xB1, 0x66, 5)                                        # a marker for the status byte
    at(4, 0xA1, 10, 20, 0, 0xD1, 30, 0, 0xE1, 1, 2)            # aftertouch, channel pressure, pitch wheel
    at(1, 0xB0, 0x67, 1)                                        # drums
    for ch in range(11, 16):
        at(0, 0xC0 | ch, rng.randrange(20))
        at(1, 0x90 | ch, 40 + ch, 100)
    at(6, 0x8B, 51, 0)
    at(0, 0x9C, 52, 0)
    at(2, 0x95, 60, 80)                                         # a melodic voice with drums on
    at(2, 0x97, 61, 80)
    at(3, 0xB0, 0x67, 0)                                        # drums off
    at(1, 0xB0, 0x70, 1)                                        # another controller: ignored
    at(1, 0xF0, *vlq(3), 1, 2, 3)                               # SysEx
    at(1, 0xF7, *vlq(2), 4, 5)
    at(1, 0xF2, 1, 2)
    at(1, 0xF3, 7)
    at(1, 0xF6)
    at(1, 0xFF, 0x01, *vlq(4), 65, 66, 67, 68)                  # text
    for i in range(30):
        at(rng.randrange(4), 0x90 | rng.randrange(9), rng.randrange(128), rng.randrange(1, 128))
        at(rng.randrange(3), 0x80 | rng.randrange(9), rng.randrange(128), 0)
    if end_with_fc:
        at(2, 0xFC)
    else:
        at(2, 0xFF, 0x2F, 0)
    at(5, 0x90, 60, 60)                                         # never reached
    header = bytearray(0x28)
    header[0:4] = b'CTMF'
    struct.pack_into('<HHHHH', header, 4, 0x0101, 0x28, 0x28 + len(instruments), 48, 120)
    struct.pack_into('<H', header, 0x24, 20)
    struct.pack_into('<H', header, 0x26, 120)
    return bytes(header) + instruments + bytes(ev)


class Run:
    def __init__(self, lib, fails):
        self.lib, self.fails = lib, fails
        m = self.m = fresh()
        SoundBlaster(m, base=0x380, dsp=False)
        # a quiet machine: INT 8 and INT 1Ch the BIOS's (the snapshot was taken while the
        # sample player had them), no sample playing
        m.uc.mem_write(0x08 * 4, struct.pack('<HH', 0x08 * 4, BIOS))
        m.uc.mem_write(0x1C * 4, struct.pack('<HH', 0x1C * 4, BIOS))
        m.ds_write(0xAA83, bytes(1))
        self.g, self.mem, self.planes = make_game(m)
        self.seen = {'opl writes': 0, 'key on': 0, 'drums': 0, 'chained': 0}
        self.base = (dosemu.LOAD_SEG + DRV) << 4
        # the timer handler's own stack in the driver's segment (E12h..E76h, the old SS:SP at
        # 44h), which the C code does not need
        cut = sorted([(self.base + 0x44, self.base + 0x48), (self.base + 0xE12, self.base + 0xE76)])
        self.spans = []
        for lo, hi in regions(m):
            for a, b in cut:
                if lo <= a and b <= hi:
                    self.spans.append((lo, a))
                    lo = b
            self.spans.append((lo, hi))

    def poke(self, linear, data):
        self.m.uc.mem_write(linear, data)
        ctypes.memmove(self.g.mem + linear, data, len(data))

    def compare(self, label):
        want = bytes(self.m.uc.mem_read(0, 0xA0000))
        got = self.mem.raw[:0xA0000]
        for lo, hi in self.spans:
            if got[lo:hi] != want[lo:hi]:
                first = next(i for i in range(lo, hi) if got[i] != want[i])
                where = (f'driver {first - self.base:04X}' if self.base <= first < self.base + 0x1010
                         else f'linear {first:05X}')
                self.fails.append(f'{label}: memory differs first at {where}: C {got[first]:02X}, '
                                  f'original {want[first]:02X}')
                return False
        return True

    def call(self, label, bx, ax=0, cx=0, dx=0, raise_irqs=False):
        """function BX on both sides"""
        global CASES
        m = self.m
        hooks = []
        if raise_irqs:        # the set-up's measuring loops: a timer interrupt in each
            counts = {}

            def hit(uc, address, size, need):
                counts[address] = counts.get(address, 0) + 1
                if counts[address] == need:
                    m.raise_irq(0)
            for off, need in ((0x0F2B, 3), (0x0F2F, 3), (0x0F33, 50)):
                at = self.base + off
                hooks.append(m.uc.hook_add(UC_HOOK_CODE, hit, need, at, at))
        trace = traced(m)
        out = m.call(DRV, 0, far=True, bx=bx, ax=ax, cx=cx, dx=dx, irqs=raise_irqs, max_instr=50_000_000)
        for h in hooks:
            m.uc.hook_del(h)
        m.trace = None
        CASES += 1
        self.count(trace)
        replay = MachineReplay(self.g, self.mem, self.planes, trace, video=False)
        r = CpuRegs(ax=ax, bx=bx, cx=cx, dx=dx, ds=m.DATA_SEG, es=m.DATA_SEG, flags=2)
        status = self.lib.fmdrv_call(ctypes.byref(self.g), ctypes.byref(replay.services), ctypes.byref(r))
        problem = replay.finished()
        where = f'{label} (BX {bx:04X})'
        if status or problem:
            self.fails.append(f'{where}: status {status}; {problem}')
            return False
        cf = out['flags'] & 1
        if (r.ax, r.dx, r.flags & 1) != (out['ax'], out['dx'], cf):
            self.fails.append(f'{where}: AX DX CF C {r.ax:04X} {r.dx:04X} {r.flags & 1}, original '
                              f'{out["ax"]:04X} {out["dx"]:04X} {cf}')
            return False
        return self.compare(where)

    def interrupt(self, label, off, vector, c_fn):
        """an interrupt handler on both sides; the C side runs the old handler after as often
        as it says"""
        global CASES
        m = self.m
        trace = traced(m)
        m.call(DRV, off, far=True, stack=(0x0202,), max_instr=20_000_000)
        m.trace = None
        CASES += 1
        self.count(trace)
        replay = MachineReplay(self.g, self.mem, self.planes, trace, video=False)
        passes = c_fn(ctypes.byref(self.g), ctypes.byref(replay.services))
        if vector == 9 and passes == 0:
            passes = 1                     # the keyboard handler always goes on to the old one
        if passes < 0:
            self.fails.append(f'{label}: status {passes}')
            return False
        r = CpuRegs()
        for _ in range(passes):
            if replay.services.interrupt(None, vector, ctypes.byref(r), None):
                break
        problem = replay.finished()
        if problem:
            self.fails.append(f'{label}: {problem}')
            return False
        return self.compare(label)

    def count(self, trace):
        """what the original did, so that the test can say it reached it"""
        reg = None
        for event in trace:
            if event[0] == 'out' and event[1] == 0x388:
                reg = event[3]
            elif event[0] == 'out' and event[1] == 0x389:
                self.seen['opl writes'] += 1
                if reg is not None and 0xB0 <= reg <= 0xB8 and event[3] & 0x20:
                    self.seen['key on'] += 1
                if reg == 0xBD and event[3] & 0x20:
                    self.seen['drums'] += 1
            elif event[0] == 'int' and event[1] == 8:
                self.seen['chained'] += 1

    def timer(self, label):
        return self.interrupt(label, 0x0C83, 8, self.lib.fmdrv_timer)

    def keyboard(self, label):
        return self.interrupt(label, 0x0CF3, 9, self.lib.fmdrv_keyboard)

    def status(self):
        return self.m.ds_read(0xEA3C, 1)[0]

    def playing(self):
        return self.m.rb(dosemu.LOAD_SEG + DRV, 0x1C4, 1)[0]


def play(run, label, song, ticks, rng, events=()):
    """instruments, clock, play, then timer interrupts (events: {tick: action})"""
    run.poke(SONG_SEG << 4, song)
    off6, off8, tempo = struct.unpack_from('<HH', song, 6) + struct.unpack_from('<H', song, 0x0C)
    count = struct.unpack_from('<H', song, 0x24)[0]
    if not (run.call(f'{label}: instruments', 2, ax=off6, cx=count, dx=SONG_SEG)
            and run.call(f'{label}: driver clock', 4, ax=0x1234DC // tempo)
            and run.call(f'{label}: play', 6, ax=off8, dx=SONG_SEG)):
        return False
    for t in range(ticks):
        action = dict(events).get(t)
        if action and not action():
            return False
        if not run.timer(f'{label}: timer interrupt {t}'):
            return False
        if not run.playing() and t > 10 and rng.random() < 0.02:
            break
    return True


def run(ctx):
    lib = ctx.lib
    for name in ('fmdrv_call', 'fmdrv_timer', 'fmdrv_keyboard'):
        getattr(lib, name).restype = ctypes.c_int
    fails = []
    rng = random.Random(0x10BB)
    r = Run(lib, fails)
    ds = r.m.DATA_SEG
    steps = [
        lambda: r.call('version, before set-up', 0),
        lambda: r.call('port base', 0xFFFD, ax=0x0380),
        lambda: r.call('set-up', 0xFFFF, raise_irqs=True),
        lambda: r.call('status byte', 1, ax=0xEA3C, dx=ds),
        lambda: r.call('version', 0),
        lambda: r.call('system clock', 3, ax=0xFFFF),
        lambda: r.call('no such function', 12),
        lambda: r.call('no such function (negative)', 0xFFFC),
        lambda: r.call('pause, stopped', 9),
        lambda: r.call('go on, stopped', 10),
        lambda: r.call('stop, stopped', 7),
    ]
    for step in steps:
        if not step():
            return fails
    song = open(os.path.join(dosemu.GAME_DIR, 'SONG1.CMF'), 'rb').read()

    def busy():
        r.poke(((dosemu.LOAD_SEG + DRV) << 4) + 0x1C7, b'\x01')
        ok = r.call('busy', 0)
        r.poke(((dosemu.LOAD_SEG + DRV) << 4) + 0x1C7, b'\x00')
        return ok
    events = {
        300: lambda: r.call('pause', 9),
        301: lambda: r.call('pause again', 9),
        360: lambda: r.call('go on', 10),
        500: lambda: r.call('transpose', 5, ax=3),
        700: lambda: r.call('play while playing', 6, ax=0x118, dx=SONG_SEG),
        800: busy,
        900: lambda: r.call('user trap (none)', 11, ax=0, dx=0),
    }
    if not play(r, 'SONG1.CMF', song, 2500, rng, events.items()):
        return fails
    if not r.call('stop', 7) or not r.call('transpose back', 5, ax=0xFFFE):
        return fails
    for n, fc in ((1, False), (2, True)):
        made = made_song(random.Random(n), end_with_fc=fc)
        if not play(r, f'made song {n}', made, 1500, rng):
            return fails
        if r.playing():
            fails.append(f'made song {n}: still playing')
            return fails
    if not r.call('reset', 8) or not play(r, 'SONG1.CMF after a reset', song, 200, rng):
        return fails
    r.poke(((dosemu.LOAD_SEG + DRV) << 4) + 0x12, struct.pack('<HH', 9 * 4, BIOS))   # INT 9 on: the BIOS
    for code in (0x1E, 0x9E, 0x03, 0x83, 0x48):
        r.m.kbd_port = code
        if not r.keyboard(f'keyboard {code:02X}'):
            return fails
    r.call('shut down', 0xFFFE)
    least = {'opl writes': 1000, 'key on': 100, 'drums': 5, 'chained': 100}
    if not fails and any(r.seen[k] < n for k, n in least.items()):
        fails.append(f'the songs did not reach enough: {r.seen}')
    return fails
