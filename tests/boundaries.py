"""Record the original's host boundaries, then replay them to the C code.

Used by tests that run a whole screen or game step in both. The original runs first. A
boundary is a call the C code hands to its host (a file load, a mode switch, a retrace
wait, ...). For each one the recorder keeps the service, its arguments, and the complete
memory and screen before and after it. Tests change the machine at a boundary (keys
pressed, for instance) through on_boundary, which runs after "before" is taken, so the
change is part of "after". The replayer then serves the C code's host calls: service and
arguments must match, the C state must equal "before", and "after" is copied in.

Kinds of boundary:
  Routine(seg, off, ...)         a called routine; optionally stubbed (b'\\xc3' = RET)
  Inline(at, next, service, ..)  an instruction (int 10h, say) treated as a call
  Point(at, service, when)       nothing is called there; an instantaneous boundary taken
                                 whenever execution reaches `at` and when(m) holds (input
                                 arriving while the original polls the keyboard table)
"""
import ctypes
from dataclasses import dataclass, field

from unicorn import UC_HOOK_CODE

import dosemu

BASE = dosemu.LOAD_SEG << 4


@dataclass
class Routine:
    seg: int
    off: int
    far: bool = False
    stub: bytes = b''
    registers: tuple = ()              # argument registers, at most two
    service: int = None                # service id seen by the C code (default: off)
    callers: tuple = ()                # only when the return offset lies in one of these ranges
    argument: int = None               # fixed first argument instead of a register


@dataclass
class Inline:
    at: int
    next: int
    service: int
    registers: tuple = ('ax',)


@dataclass
class Point:
    at: int
    service: int
    when: object = None                # m -> bool
    seg: int = 0


PAGE = 4096
MEMORY = 0xA0000                        # conventional memory; the screen (planes + card) follows
SCREEN = 4 * 65536 + 16                 # the planes and the card registers; then, if asked, the
                                        # 64 KB mode-13h screen


def screen_of(m):
    return b''.join(bytes(p) for p in m.vga.planes) + m.vga.card_state()


def pages_of(m, chunky=False):
    """The state (memory, the planes and card registers, maybe the mode-13h screen) cut
    into 4 KB pages."""
    state = bytes(m.uc.mem_read(0, MEMORY)) + screen_of(m) + (bytes(m.vga.chunky) if chunky else b'')
    return [state[i:i + PAGE] for i in range(0, len(state), PAGE)]


def difference(got, want, spans, ds_base):
    """'' or where the first differences are, as DS offsets with C/original bytes."""
    for lo, hi in spans:
        if got[lo:hi] != want[lo:hi]:
            first = next(i for i in range(lo, hi) if got[i] != want[i])
            diffs = [i for i in range(first, min(hi, first + 4096)) if got[i] != want[i]][:8]
            return 'differs at ' + ', '.join(
                (f'DS:{i - ds_base:04X}' if 0 <= i - ds_base < 65536 else f'{i:05X}')
                + f' C {got[i]:02X} orig {want[i]:02X}' for i in diffs)
    return ''


@dataclass
class Recorder:
    """States are kept as the pages that changed since the previous state (before the first
    boundary: since install), so thousands of boundaries cost little memory."""
    m: object
    boundaries: list
    on_boundary: object = None         # (entry) -> None, called after "before" is taken
    chunky: bool = False               # keep the mode-13h screen too
    calls: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    base: list = None                  # the pages at install

    def changed(self):
        pages = pages_of(self.m, self.chunky)
        delta = {i: page for i, page in enumerate(pages) if page != self._pages[i]}
        self._pages = pages
        return delta

    def install(self):
        m = self.m
        hooked = set()
        self.base = self._pages = pages_of(m, self.chunky)

        def finish(uc, addr, size, user):
            if self.pending and addr == self.pending[-1]['return'] and m.r(dosemu.UC_X86_REG_SP) == self.pending[-1]['sp']:
                entry = self.pending.pop()
                entry['after'] = self.changed()
                entry['handles'] = m.next_handle
                entry['carry'] = m.r(dosemu.UC_X86_REG_EFLAGS) & 1

        def begin(service, a, b, ret=None, sp=None, caller=None):
            entry = dict(service=service, a=a, b=b, before=self.changed(), sp=sp, caller=caller, **{'return': ret})
            self.calls.append(entry)
            if self.on_boundary:
                self.on_boundary(entry)
            if ret is None:                       # a point: over at once
                entry['after'] = self.changed()
                entry['handles'] = m.next_handle
                entry['carry'] = 0
                return
            self.pending.append(entry)
            if ret not in hooked:
                m.uc.hook_add(UC_HOOK_CODE, finish, None, ret, ret)
                hooked.add(ret)

        def args(registers):
            return [m.r(m.REG_BY_NAME[r]) for r in registers] + [0, 0]

        def routine(uc, addr, size, spec):
            if self.pending:
                return
            ss, sp = m.r(dosemu.UC_X86_REG_SS), m.r(dosemu.UC_X86_REG_SP)
            ret_off = m.rw(ss, sp)
            ret_seg = m.rw(ss, sp + 2) if spec.far else m.r(dosemu.UC_X86_REG_CS)
            if spec.callers and not any(lo <= ret_off < hi for lo, hi in spec.callers):
                return
            a, b = args(spec.registers)[:2]
            if spec.argument is not None:
                a = spec.argument
            begin(spec.off if spec.service is None else spec.service, a, b, (ret_seg << 4) + ret_off,
                  (sp + (4 if spec.far else 2)) & 0xFFFF, (ret_seg - dosemu.LOAD_SEG & 0xFFFF, ret_off))

        def inline(uc, addr, size, spec):
            if not self.pending:
                a, b = args(spec.registers)[:2]
                begin(spec.service, a, b, BASE + spec.next, m.r(dosemu.UC_X86_REG_SP))

        def point(uc, addr, size, spec):
            if not self.pending and (spec.when is None or spec.when(m)):
                begin(spec.service, 0, 0)

        for spec in self.boundaries:
            if isinstance(spec, Routine):
                if spec.stub:
                    m.wb(dosemu.LOAD_SEG + spec.seg, spec.off, spec.stub)
                at = ((dosemu.LOAD_SEG + spec.seg) << 4) + spec.off
                m.uc.hook_add(UC_HOOK_CODE, routine, spec, at, at)
            elif isinstance(spec, Inline):
                m.uc.hook_add(UC_HOOK_CODE, inline, spec, BASE + spec.at, BASE + spec.at)
            else:
                at = ((dosemu.LOAD_SEG + spec.seg) << 4) + spec.at
                m.uc.hook_add(UC_HOOK_CODE, point, spec, at, at)
        return self


def stub_all(m, boundaries, extra=()):
    """Write the stubs before the C copy of memory is made, so both hold the same code."""
    for spec in boundaries:
        if isinstance(spec, Routine) and spec.stub:
            m.wb(dosemu.LOAD_SEG + spec.seg, spec.off, spec.stub)
    for off in extra:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')


@dataclass
class Replayer:
    g: object
    mem: object
    planes: object
    spans: list
    ds_base: int
    recorder: Recorder
    files: object = None               # test_imageload.Files: takes over the DOS handle counter
    screen: object = None              # the C mode-13h screen buffer, when the recorder kept it
    index: int = 0
    errors: list = field(default_factory=list)
    last: dict = None                  # the entry served last (its 'carry', for instance)

    def __post_init__(self):
        self.calls = self.recorder.calls
        self.state = bytearray(b''.join(self.recorder.base))

    def apply(self, delta):
        for i, page in delta.items():
            self.state[i * PAGE:i * PAGE + len(page)] = page

    def serve(self, service, a=0, b=0):
        if self.errors:
            return -1
        if self.index >= len(self.calls):
            self.errors.append(f'extra service {service:04X} ({a:04X}, {b:04X})')
            return -1
        entry = self.last = self.calls[self.index]
        self.index += 1
        if (service, a, b) != (entry['service'], entry['a'], entry['b']):
            self.errors.append(f'service {self.index}: C {service:04X} ({a:04X}, {b:04X}), original '
                               f'{entry["service"]:04X} ({entry["a"]:04X}, {entry["b"]:04X})')
            return -1
        self.apply(entry['before'])
        error = difference(self.mem.raw, self.state, self.spans, self.ds_base)
        if not error and self.planes.raw != self.state[MEMORY:MEMORY + SCREEN]:
            got, want = self.planes.raw, self.state[MEMORY:MEMORY + SCREEN]
            first = next(i for i in range(SCREEN) if got[i] != want[i])
            where = f'card register byte {first - 4 * 65536}' if first >= 4 * 65536 else                 f'plane {first >> 16} offset {first & 0xFFFF:04X}'
            error = f'screen differs ({where}: C {got[first]:02X}, original {want[first]:02X})'
        if not error and self.screen is not None and self.screen.raw != self.state[MEMORY + SCREEN:]:
            error = 'mode-13h screen differs'
        if error:
            self.errors.append(f'before service {self.index} ({service:04X}): {error}')
            return -1
        self.apply(entry['after'])
        ctypes.memmove(self.g.mem, bytes(self.state[:MEMORY]), MEMORY)
        ctypes.memmove(self.g.planes, bytes(self.state[MEMORY:MEMORY + SCREEN]), SCREEN)
        if self.screen is not None:
            chunky = bytes(self.state[MEMORY + SCREEN:])
            ctypes.memmove(self.screen, chunky, len(chunky))
        if self.files is not None:
            self.files.next_handle = entry['handles']
        return 0

    def finished(self):
        """'' or what went wrong with the sequence of calls."""
        if self.errors:
            return '; '.join(self.errors[:2])
        if self.index != len(self.calls):
            return f'C made {self.index} of the original {len(self.calls)} service calls'
        return ''
