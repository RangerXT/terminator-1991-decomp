"""Headless DOS machine for running The Terminator (1991) under Unicorn.

Just enough PC to run this one game deterministically without a display:
real-mode 8086/386 CPU (Unicorn), DOS file/memory/vector services, BIOS video/keyboard/timer
services, EGA/VGA planar and mode 13h video memory, DAC, PIC/PIT timer interrupts and a
scripted keyboard. There is no sound hardware; the game sees neither AdLib nor Sound Blaster.

Use it from Python (see the Machine class) or from the command line:

  python tools/dosemu.py run [--ticks N] [--keys "t:key,t:key,..."] [--shots DIR] [--every N]
                             [--coverage] [--save FILE] [--load FILE] [--args "ADLIB"]

  --ticks N       stop after N timer ticks of virtual time (18.2 per second)
  --keys          scripted key presses: "<tick>:<name>" e.g. "40:enter,90:esc,120:a"
  --shots DIR     write a PNG of the screen every --every ticks (default 18)
  --coverage      record every executed code address into disasm/coverage.txt
  --save / --load machine state snapshots, to resume from a point without replaying

Everything is deterministic: time is counted in executed instructions, not wall-clock.
"""
import os
import pickle
import struct
import sys
import time

from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UC_HOOK_INSN, UC_HOOK_BLOCK,
                     UC_HOOK_MEM_UNMAPPED, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_PROT_ALL)
from unicorn.x86_const import *  # noqa: F401,F403

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
EXE = os.path.join(ROOT, 'exe', 'TERM_unpacked.exe')
GAME_DIR = os.path.join(ROOT, 'run_vga')

PSP_SEG = 0x0200
LOAD_SEG = PSP_SEG + 0x10
ENV_SEG = 0x01F0
MEM_TOP = 0xA000
BIOS_SEG = 0xF000
INSTR_PER_TICK = 1000000          # virtual CPU speed: instructions per 18.2 Hz timer tick (about 18 MIPS)
SLICE = 2000                      # instructions per emulation slice
# File segments that hold code (see RE_NOTES.md); writes into them are watched for
# self-modifying code, see Machine._code_write.
CODE_SEGMENTS = [(0x0000, 0x1720), (0x5776, 0x5C27)]
FRAME_INSTR = INSTR_PER_TICK * 182 // 700   # one 70 Hz video frame

CF, ZF, IF_, TF = 0x0001, 0x0040, 0x0200, 0x0100

SCANCODES = {
    'esc': 0x01, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09,
    '9': 0x0A, '0': 0x0B, 'minus': 0x0C, 'equals': 0x0D, 'backspace': 0x0E, 'tab': 0x0F,
    'q': 0x10, 'w': 0x11, 'e': 0x12, 'r': 0x13, 't': 0x14, 'y': 0x15, 'u': 0x16, 'i': 0x17, 'o': 0x18,
    'p': 0x19, 'lbracket': 0x1A, 'rbracket': 0x1B, 'enter': 0x1C, 'ctrl': 0x1D,
    'a': 0x1E, 's': 0x1F, 'd': 0x20, 'f': 0x21, 'g': 0x22, 'h': 0x23, 'j': 0x24, 'k': 0x25, 'l': 0x26,
    'lshift': 0x2A, 'z': 0x2C, 'x': 0x2D, 'c': 0x2E, 'v': 0x2F, 'b': 0x30, 'n': 0x31, 'm': 0x32,
    'comma': 0x33, 'period': 0x34, 'slash': 0x35, 'rshift': 0x36, 'alt': 0x38, 'space': 0x39,
    'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E, 'f5': 0x3F, 'f6': 0x40, 'f7': 0x41, 'f8': 0x42,
    'f9': 0x43, 'f10': 0x44, 'home': 0x47, 'up': 0x48, 'pgup': 0x49, 'left': 0x4B, 'right': 0x4D,
    'end': 0x4F, 'down': 0x50, 'pgdn': 0x51, 'insert': 0x52, 'delete': 0x53,
}
ASCII = {'esc': 27, 'enter': 13, 'space': 32, 'backspace': 8, 'tab': 9, 'minus': 45, 'equals': 61,
         'comma': 44, 'period': 46, 'slash': 47, 'lbracket': 91, 'rbracket': 93}
for _c in 'abcdefghijklmnopqrstuvwxyz0123456789':
    ASCII[_c] = ord(_c)


def ega_rgb(v):
    """6-bit EGA colour number (rgbRGB) -> (r, g, b) 0..255."""
    r = ((v >> 2) & 1) * 170 + ((v >> 5) & 1) * 85
    g = ((v >> 1) & 1) * 170 + ((v >> 4) & 1) * 85
    b = (v & 1) * 170 + ((v >> 3) & 1) * 85
    return r, g, b


DEFAULT_ATTR = [0, 1, 2, 3, 4, 5, 0x14, 7, 0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F]


class VGA:
    def __init__(self, clock=lambda: 0):
        self.clock = clock
        self.planes = [bytearray(0x10000) for _ in range(4)]
        self.chunky = bytearray(0x10000)
        self.latch = [0, 0, 0, 0]
        self.seq_index = 0
        self.seq = [0] * 8
        self.seq[2] = 0x0F
        self.gc_index = 0
        self.gc = [0] * 16
        self.gc[8] = 0xFF
        self.crtc_index = 0
        self.crtc = [0] * 32
        self.attr = list(DEFAULT_ATTR) + [0] * 16
        self.attr_flip = False
        self.attr_index = 0
        self.dac = bytearray(768)
        self.dac_windex = 0
        self.dac_rindex = 0
        self.dac_wcomp = 0
        self.dac_rcomp = 0
        self.status_toggle = 0
        self.mode = 3
        self.writes = 0
        self.reset_dac()

    def reset_dac(self):
        for i in range(64):
            r, g, b = ega_rgb(i)
            self.dac[i * 3:i * 3 + 3] = bytes((r >> 2, g >> 2, b >> 2))
        for i in range(64, 256):
            self.dac[i * 3:i * 3 + 3] = bytes((i >> 2, i >> 2, i >> 2))

    def set_mode(self, mode, clear=True):
        self.mode = mode
        self.seq[2] = 0x0F
        self.gc = [0] * 16
        self.gc[8] = 0xFF
        self.crtc[0x0C] = self.crtc[0x0D] = 0
        self.attr[:16] = DEFAULT_ATTR
        self.reset_dac()
        if clear:
            for p in self.planes:
                p[:] = bytes(0x10000)
            self.chunky[:] = bytes(0x10000)

    def card_state(self):
        """The registers and latches the C rewrite models, in the layout of EgaRegs in
        src/term.h: plane mask, graphics controller 0-8, selected index, latches, pad."""
        return bytes([self.seq[2] & 0xFF] + [v & 0xFF for v in self.gc[:9]] + [self.gc_index & 0xFF]
                     + [v & 0xFF for v in self.latch] + [0])

    # ---- memory at A000:0000
    def mem_read(self, off):
        if self.mode == 0x13:
            return self.chunky[off]
        pl = self.planes
        self.latch = [pl[0][off], pl[1][off], pl[2][off], pl[3][off]]
        if self.gc[5] & 0x08:      # read mode 1: colour compare
            cc, dc = self.gc[2], self.gc[7]
            r = 0xFF
            for p in range(4):
                if dc >> p & 1:
                    r &= ~(self.latch[p] ^ (0xFF if cc >> p & 1 else 0)) & 0xFF
            return r
        return self.latch[self.gc[4] & 3]

    def mem_write(self, off, val):
        self.writes += 1
        if self.mode == 0x13:
            self.chunky[off] = val
            return
        gc = self.gc
        mode = gc[5] & 3
        mask = self.seq[2]
        latch = self.latch
        pl = self.planes
        if mode == 1:
            for p in range(4):
                if mask >> p & 1:
                    pl[p][off] = latch[p]
            return
        bitmask = gc[8]
        func = (gc[3] >> 3) & 3
        rot = gc[3] & 7
        if mode == 0:
            if rot:
                val = ((val >> rot) | (val << (8 - rot))) & 0xFF
            sr, esr = gc[0], gc[1]
            for p in range(4):
                if not (mask >> p & 1):
                    continue
                src = (0xFF if sr >> p & 1 else 0) if esr >> p & 1 else val
                lt = latch[p]
                if func == 1:
                    src &= lt
                elif func == 2:
                    src |= lt
                elif func == 3:
                    src ^= lt
                pl[p][off] = (src & bitmask) | (lt & ~bitmask & 0xFF)
        elif mode == 2:
            for p in range(4):
                if not (mask >> p & 1):
                    continue
                src = 0xFF if val >> p & 1 else 0
                lt = latch[p]
                if func == 1:
                    src &= lt
                elif func == 2:
                    src |= lt
                elif func == 3:
                    src ^= lt
                pl[p][off] = (src & bitmask) | (lt & ~bitmask & 0xFF)
        else:  # mode 3
            if rot:
                val = ((val >> rot) | (val << (8 - rot))) & 0xFF
            bm = val & bitmask
            sr = gc[0]
            for p in range(4):
                if mask >> p & 1:
                    src = 0xFF if sr >> p & 1 else 0
                    pl[p][off] = (src & bm) | (latch[p] & ~bm & 0xFF)

    # ---- ports
    def port_out(self, port, val):
        if port == 0x3C4:
            self.seq_index = val & 7
        elif port == 0x3C5:
            self.seq[self.seq_index] = val
        elif port == 0x3CE:
            self.gc_index = val & 15
        elif port == 0x3CF:
            self.gc[self.gc_index] = val
        elif port == 0x3D4:
            self.crtc_index = val & 31
        elif port == 0x3D5:
            self.crtc[self.crtc_index] = val
        elif port == 0x3C0:
            if not self.attr_flip:
                self.attr_index = val & 0x1F
            else:
                self.attr[self.attr_index] = val
            self.attr_flip = not self.attr_flip
        elif port == 0x3C8:
            self.dac_windex, self.dac_wcomp = val, 0
        elif port == 0x3C7:
            self.dac_rindex, self.dac_rcomp = val, 0
        elif port == 0x3C9:
            self.dac[(self.dac_windex * 3 + self.dac_wcomp) % 768] = val & 0x3F
            self.dac_wcomp += 1
            if self.dac_wcomp == 3:
                self.dac_wcomp = 0
                self.dac_windex = (self.dac_windex + 1) & 0xFF

    def port_in(self, port):
        if port == 0x3DA:
            self.attr_flip = False
            self.status_toggle ^= 1
            # bit 3 vertical retrace: 70 Hz in virtual time, active for a tenth of the frame.
            # bit 0 display disabled: set during vertical retrace, otherwise toggles per read.
            if self.clock() % FRAME_INSTR < FRAME_INSTR // 10:
                return 0x09
            return self.status_toggle
        if port == 0x3C5:
            return self.seq[self.seq_index]
        if port == 0x3CF:
            return self.gc[self.gc_index]
        if port == 0x3D5:
            return self.crtc[self.crtc_index]
        if port == 0x3C9:
            v = self.dac[(self.dac_rindex * 3 + self.dac_rcomp) % 768]
            self.dac_rcomp += 1
            if self.dac_rcomp == 3:
                self.dac_rcomp = 0
                self.dac_rindex = (self.dac_rindex + 1) & 0xFF
            return v
        if port == 0x3C8:
            return self.dac_windex
        if port in (0x3CC, 0x3C2):
            return 0x63
        return 0xFF

    # ---- picture
    def rgb_of(self, i):
        return tuple(min(255, c * 255 // 63) for c in self.dac[i * 3:i * 3 + 3])

    def screenshot(self):
        """Return (width, height, rgb_bytes) for graphics modes, or None in text mode."""
        m = self.mode
        if m == 0x13:
            pal = [self.rgb_of(i) for i in range(256)]
            out = bytearray()
            for v in self.chunky[:64000]:
                out += bytes(pal[v])
            return 320, 200, bytes(out)
        if m in (0x0D, 0x0E, 0x10, 0x12):
            w, h = {0x0D: (320, 200), 0x0E: (640, 200), 0x10: (640, 350), 0x12: (640, 480)}[m]
            start = (self.crtc[0x0C] << 8) | self.crtc[0x0D]
            pal = [self.rgb_of(self.attr[i] & 0x3F) for i in range(16)]
            rb = w // 8
            out = bytearray(w * h * 3)
            p0, p1, p2, p3 = self.planes
            o = 0
            for y in range(h):
                base = (start + y * rb) & 0xFFFF
                for xb in range(rb):
                    a = (base + xb) & 0xFFFF
                    b0, b1, b2, b3 = p0[a], p1[a], p2[a], p3[a]
                    for bit in (128, 64, 32, 16, 8, 4, 2, 1):
                        c = (1 if b0 & bit else 0) | (2 if b1 & bit else 0) | (4 if b2 & bit else 0) | \
                            (8 if b3 & bit else 0)
                        out[o:o + 3] = bytes(pal[c])
                        o += 3
            return w, h, bytes(out)
        return None


class Exit(Exception):
    pass


class Machine:
    def __init__(self, game_dir=GAME_DIR, args='', coverage=False, verbose=False):
        self.game_dir = game_dir
        self.verbose = verbose
        self.vga = VGA(lambda: self.instr)
        self.console = []
        self.log = []
        self.files = {}
        self.next_handle = 5
        self.blocks = []            # DOS memory arena: [seg, paragraphs, used]
        self.dta = (PSP_SEG, 0x80)
        self.find_state = None
        self.ticks = 0
        self.instr = 0
        self.next_irq0 = INSTR_PER_TICK
        self.pit_divisor = 0x10000
        self.pit_latch = []
        self.irq_mask = 0
        self.in_service = 0
        self.kbd_queue = []         # (scancode, ascii) for INT 16h when INT 9 is not hooked
        self.kbd_port = 0
        self.key_events = []        # (tick, scancode byte)
        self.pending = None
        self._smc_undo = None      # pre-write bytes for stopped instructions
        self._smc_stop = False      # see _code_write
        self._smc_pass = False
        self.smc_stops = 0
        self.exit_code = None
        self.blocked = None
        self.coverage = set() if coverage else None
        self.unknown = set()
        self.port_log = {}
        self.int_counts = {}
        self.trace = None           # a list: port accesses and serviced interrupts, for tests/machine.py
        self.joystick = None        # tests: a callable giving port 201h's next value (else FFh)
        self.devices = {}           # tests: port -> a device with read(port) and write(port, value)
        self.irq_request = None     # an IRQ a device raised, delivered when it can be (raise_irq)
        self.ems = None             # tests: a dict of EMS state; INT 67h then acts as a small EMM
        self._build(args)

    # ------------------------------------------------------------ setup
    def _build(self, args):
        uc = self.uc = Uc(UC_ARCH_X86, UC_MODE_16)
        uc.mem_map(0, 0xA0000, UC_PROT_ALL)
        # Video memory is ordinary RAM as far as the CPU emulator knows; every access is
        # trapped by the hooks below. (An MMIO region is not usable here: Unicorn widens an
        # unaligned 2-byte MMIO read to two aligned ones, which loads the EGA latches from
        # the wrong byte.)
        uc.mem_map(0xA0000, 0x10000, UC_PROT_ALL)
        uc.mem_map(0xB0000, 0x60000, UC_PROT_ALL)
        d = open(EXE, 'rb').read()
        (_, lastpg, pages, nrel, hdrpar, minal, maxal, ss, sp, _, ip, cs, reloff, _) = \
            struct.unpack_from('<2s13H', d, 0)
        img = bytearray(d[hdrpar * 16:])
        for i in range(nrel):
            off, seg = struct.unpack_from('<HH', d, reloff + 4 * i)
            a = seg * 16 + off
            struct.pack_into('<H', img, a, (struct.unpack_from('<H', img, a)[0] + LOAD_SEG) & 0xFFFF)
        uc.mem_write(LOAD_SEG * 16, bytes(img))
        self.image_paras = (len(img) + 15) // 16 + minal
        # environment + PSP
        env = b'COMSPEC=C:\\COMMAND.COM\0PATH=C:\\\0\0\x01\0C:\\TERM\\TERM.EXE\0'
        uc.mem_write(ENV_SEG * 16, env)
        psp = bytearray(256)
        psp[0:2] = b'\xCD\x20'
        struct.pack_into('<H', psp, 2, MEM_TOP)
        struct.pack_into('<H', psp, 0x2C, ENV_SEG)
        tail = (' ' + args if args else '').encode()
        psp[0x80] = len(tail)
        psp[0x81:0x81 + len(tail)] = tail
        psp[0x81 + len(tail)] = 0x0D
        uc.mem_write(PSP_SEG * 16, bytes(psp))
        self.blocks = [[PSP_SEG, MEM_TOP - PSP_SEG, True]]
        # interrupt vectors: every vector gets a stub "INT n; IRET" in the BIOS segment
        for n in range(256):
            uc.mem_write(BIOS_SEG * 16 + n * 4, bytes((0xCD, n, 0xCF, 0x90)))
            uc.mem_write(n * 4, struct.pack('<HH', n * 4, BIOS_SEG))
        # BIOS data area
        bda = bytearray(256)
        struct.pack_into('<H', bda, 0x10, 0x0021)
        struct.pack_into('<H', bda, 0x13, 640)
        bda[0x49] = 3
        struct.pack_into('<H', bda, 0x4A, 80)
        struct.pack_into('<H', bda, 0x63, 0x3D4)
        struct.pack_into('<HH', bda, 0x1A, 0x1E, 0x1E)
        struct.pack_into('<HH', bda, 0x80, 0x1E, 0x3E)
        bda[0x84] = 24
        bda[0x87], bda[0x88], bda[0x89] = 0x60, 0xF9, 0x51
        uc.mem_write(0x400, bytes(bda))
        uc.mem_write(0xFFFF5, b'01/01/92')
        uc.mem_write(0xFFFFE, b'\xFC')
        for r in (UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX, UC_X86_REG_SI,
                  UC_X86_REG_DI, UC_X86_REG_BP):
            uc.reg_write(r, 0)
        uc.reg_write(UC_X86_REG_DS, PSP_SEG)
        uc.reg_write(UC_X86_REG_ES, PSP_SEG)
        uc.reg_write(UC_X86_REG_SS, (ss + LOAD_SEG) & 0xFFFF)
        uc.reg_write(UC_X86_REG_SP, sp)
        self.cs, self.ip = (cs + LOAD_SEG) & 0xFFFF, ip
        uc.reg_write(UC_X86_REG_EFLAGS, 0x0202)
        self._clean_ctx = uc.context_save()
        self._hooks()

    def _hooks(self):
        uc = self.uc
        uc.hook_add(UC_HOOK_INTR, self._on_int)
        uc.hook_add(UC_HOOK_INSN, self._on_in, None, 1, 0, UC_X86_INS_IN)
        uc.hook_add(UC_HOOK_INSN, self._on_out, None, 1, 0, UC_X86_INS_OUT)
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._on_unmapped)
        uc.hook_add(UC_HOOK_MEM_READ, self._vread, None, 0x9FFF0, 0xAFFFF)
        uc.hook_add(UC_HOOK_MEM_WRITE, self._vwrite, None, 0x9FFF0, 0xAFFFF)
        for lo, hi in CODE_SEGMENTS:
            uc.hook_add(UC_HOOK_MEM_WRITE, self._code_write, None,
                        (lo + LOAD_SEG) << 4, ((hi + LOAD_SEG) << 4) - 1)
        if self.coverage is not None:
            uc.hook_add(UC_HOOK_BLOCK, self._on_block)

    # ------------------------------------------------------------ helpers
    def r(self, reg):
        return self.uc.reg_read(reg)

    def w(self, reg, v):
        self.uc.reg_write(reg, v & 0xFFFF)

    def rb(self, seg, off, n=1):
        return bytes(self.uc.mem_read(((seg << 4) + (off & 0xFFFF)) & 0xFFFFF, n))

    def rw(self, seg, off):
        return struct.unpack('<H', self.rb(seg, off, 2))[0]

    def wb(self, seg, off, data):
        # API/bulk writes (notably DOS READ) bypass Unicorn's CPU memory hooks.
        # Mirror video bytes through the card as well as its backing RAM.
        address = ((seg << 4) + (off & 0xFFFF)) & 0xFFFFF
        data = bytes(data)
        self.uc.mem_write(address, data)
        lo, hi = max(address, 0xA0000), min(address + len(data), 0xB0000)
        for at in range(lo, hi):
            self.vga.mem_write(at - 0xA0000, data[at - address])

    def ww(self, seg, off, v):
        self.wb(seg, off, struct.pack('<H', v & 0xFFFF))

    def asciiz(self, seg, off, limit=128):
        s = self.rb(seg, off, limit)
        return s.split(b'\0')[0].decode('latin1')

    def ivt(self, n):
        off, seg = struct.unpack('<HH', bytes(self.uc.mem_read(n * 4, 4)))
        return seg, off

    def hooked(self, n):
        return self.ivt(n) != (BIOS_SEG, n * 4)

    def set_flag(self, mask, on):
        """Set a flag for the caller of the current INT service."""
        if self._via_stub:
            ss, sp = self.r(UC_X86_REG_SS), self.r(UC_X86_REG_SP)
            f = self.rw(ss, sp + 4)
            self.ww(ss, sp + 4, (f | mask) if on else (f & ~mask))
        else:
            f = self.r(UC_X86_REG_EFLAGS)
            self.uc.reg_write(UC_X86_REG_EFLAGS, (f | mask) if on else (f & ~mask))

    def ax(self):
        return self.r(UC_X86_REG_AX)

    # ------------------------------------------------------------ video memory
    def _vread(self, uc, access, address, size, value, ud):
        """Only bytes physically inside A000..AFFF reach the video card. The
        hook begins sixteen bytes earlier because Unicorn filters by the access
        start, even for a word/dword that overlaps the window. Word operations
        at offset FFFF do not wrap their second byte back into video memory."""
        lo, hi = max(address, 0xA0000), min(address + size, 0xB0000)
        if lo >= hi:
            return
        v = self.vga
        if lo == address and hi == address + size:
            uc.mem_write(address, bytes(v.mem_read(where - 0xA0000) for where in range(lo, hi)))
        else:
            raw = bytearray(uc.mem_read(address, size))
            for where in range(lo, hi):
                raw[where - address] = v.mem_read(where - 0xA0000)
            uc.mem_write(address, bytes(raw))

    def _vwrite(self, uc, access, address, size, value, ud):
        for where in range(max(address, 0xA0000), min(address + size, 0xB0000)):
            self.vga.mem_write(where - 0xA0000, (value >> (8 * (where - address))) & 0xFF)

    # ------------------------------------------------------------ self-modifying code
    def _code_write(self, uc, access, address, size, value, ud):
        """Isolate unaligned writes to executable pages (Unicorn 2.1.4).
        Stopping in MEM_WRITE commits the bytes but leaves IP/flags at the start
        of the instruction. Restore the old bytes before replay; otherwise INC
        and other read-modify-write operations happen twice. A short isolated
        replay also restores hooks lost by the Unicorn SMC path.
        """
        if address & (size - 1) and not self._smc_pass:
            self._smc_undo = (address, bytes(uc.mem_read(address, size)))
            self._smc_stop = True
            uc.emu_stop()

    def step(self, until, count):
        """Run up to `count` instructions from self.cs:self.ip, stopping at linear address
        `until`. Every emu_start in this project should go through here."""
        uc = self.uc
        uc.reg_write(UC_X86_REG_CS, self.cs)
        uc.emu_start((self.cs << 4) + self.ip, until, count=count)
        self.cs, self.ip = self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)
        while self._smc_stop:
            self._smc_stop = False
            self.smc_stops += 1
            if self._smc_undo is not None:
                address, old = self._smc_undo
                uc.mem_write(address, old)
                self._smc_undo = None
            self._smc_pass = True
            try:
                # two, not one: a single-instruction slice never gets past an instruction
                # that patches code just ahead of itself
                uc.emu_start((self.cs << 4) + self.ip, until, count=2)
            finally:
                self._smc_pass = False
            self.cs, self.ip = self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)

    # ------------------------------------------------------------ ports
    def _on_in(self, uc, port, size, ud):
        if port in self.devices:
            v = self.devices[port].read(port) & 0xFF
        elif 0x3C0 <= port <= 0x3DA:
            v = self.vga.port_in(port)
        elif port == 0x60:
            v = self.kbd_port
        elif port == 0x61:
            self._p61 = getattr(self, '_p61', 0) ^ 0x10      # refresh-toggle bit for delay loops
            v = self._p61
        elif port == 0x64:
            v = 0x14
        elif port == 0x21:
            v = self.irq_mask
        elif port == 0x20:
            v = self.in_service
        elif port in (0x40, 0x41, 0x42):
            # free-running counter read: derive from instruction count
            if not self.pit_rd:
                c = (0x10000 - ((self.instr * 65536 // INSTR_PER_TICK) & 0xFFFF)) & 0xFFFF
                self.pit_rd = [c & 0xFF, c >> 8]
            v = self.pit_rd.pop(0)
        elif port == 0x201:
            v = self.joystick() if self.joystick else 0xFF
        else:
            v = 0xFF
            self.port_log[('in', port)] = self.port_log.get(('in', port), 0) + 1
        if size == 2:
            v |= 0xFF00 if not (0x3C0 <= port <= 0x3DA) else (self.vga.port_in(port + 1) << 8)
        if self.trace is not None:
            self.trace.append(('in', port, size, v))
        return v

    pit_rd = []

    def _on_out(self, uc, port, size, value, ud):
        if self.trace is not None:
            self.trace.append(('out', port, size, value & (0xFFFF if size == 2 else 0xFF)))
        if size == 2:
            self._out8(port, value & 0xFF)
            self._out8(port + 1, (value >> 8) & 0xFF)
        else:
            self._out8(port, value & 0xFF)

    def _out8(self, port, v):
        if port in self.devices:
            self.devices[port].write(port, v)
        elif 0x3C0 <= port <= 0x3DA:
            self.vga.port_out(port, v)
        elif port == 0x20:
            if v == 0x20:
                # non-specific EOI: clear highest-priority in-service bit
                for i in range(8):
                    if self.in_service >> i & 1:
                        self.in_service &= ~(1 << i)
                        break
        elif port == 0x21:
            self.irq_mask = v
        elif port == 0x43:
            self.pit_latch = []
            self.pit_rd = []
            self.pit_mode = v
        elif port == 0x40:
            self.pit_latch.append(v)
            if len(self.pit_latch) == 2:
                d = self.pit_latch[0] | self.pit_latch[1] << 8
                self.pit_divisor = d or 0x10000
                self.pit_latch = []
                self.log.append(f'PIT divisor {self.pit_divisor} at tick {self.ticks}')
        elif port in (0x61, 0x42, 0x60, 0x64):
            pass
        else:
            self.port_log[('out', port)] = self.port_log.get(('out', port), 0) + 1

    # ------------------------------------------------------------ interrupts
    def _on_unmapped(self, uc, access, address, size, value, ud):
        self.log.append(f'unmapped access {access} at {address:#x} from '
                        f'{self.r(UC_X86_REG_CS):04x}:{self.r(UC_X86_REG_IP):04x}')
        return False

    def _on_block(self, uc, address, size, ud):
        self.coverage.add(address)

    def _on_int(self, uc, n, ud):
        # Unicorn reports a software INT with IP already past the instruction; a CPU fault
        # (divide error...) with IP at the faulting instruction.
        cs, ip = self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)
        prev = self.rb(cs, ip - 2, 2)
        soft = (prev[0] == 0xCD and prev[1] == n) or (n == 3 and prev[1] == 0xCC) or (n == 4 and prev[1] == 0xCE)
        next_ip = ip
        self.int_counts[n] = self.int_counts.get(n, 0) + 1
        self._via_stub = (cs == BIOS_SEG)
        if not soft:
            # CPU fault (divide error...): deliver through the vector table, return address = this instruction
            self.pending = ('fault', n, cs, ip)
            uc.emu_stop()
            return
        if not self._via_stub and self.hooked(n):
            # the program replaced this vector: enter its handler
            self.pending = ('int', n, cs, next_ip)
            uc.emu_stop()
            return
        if self.trace is not None:
            self._traced_service(n)
            return
        try:
            self._service(n)
        except Exit:
            self.pending = ('exit',)
            uc.emu_stop()

    TRACE_REGS = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'ds', 'es')

    def _traced_service(self, n):
        """_service, recorded: the registers before and after, the memory pages it changed and
        the video state afterwards (planes, card, mode-13h screen, DAC, mode)."""
        regs = lambda: {r: self.r(self.REG_BY_NAME[r]) for r in self.TRACE_REGS} | {
            'flags': self.r(UC_X86_REG_EFLAGS) & 0xFFFF}
        before, memory = regs(), bytes(self.uc.mem_read(0, 0x100000))
        exited = False
        try:
            self._service(n)
        except Exit:
            exited = True
        after = bytes(self.uc.mem_read(0, 0x100000))
        pages = {i: after[i * 4096:(i + 1) * 4096] for i in range(256)
                 if after[i * 4096:(i + 1) * 4096] != memory[i * 4096:(i + 1) * 4096]}
        video = (b''.join(bytes(p) for p in self.vga.planes) + self.vga.card_state(), bytes(self.vga.chunky),
                 bytes(self.vga.dac), self.vga.mode)
        self.trace.append(('int', n, before, regs(), pages, video))
        if exited:
            self.pending = ('exit',)
            self.uc.emu_stop()

    def _enter(self, n, ret_cs, ret_ip):
        uc = self.uc
        ss, sp = self.r(UC_X86_REG_SS), self.r(UC_X86_REG_SP)
        fl = self.r(UC_X86_REG_EFLAGS) & 0xFFFF
        sp = (sp - 6) & 0xFFFF
        self.wb(ss, sp, struct.pack('<HHH', ret_ip, ret_cs, fl))
        self.w(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_EFLAGS, fl & ~(IF_ | TF))
        seg, off = self.ivt(n)
        self.cs, self.ip = seg, off

    def raise_irq(self, irq):
        """A device raises IRQ irq (0..7): the emulation stops after this instruction, and the
        interrupt is delivered to the program's handler as soon as interrupts are enabled and
        the line unmasked (checked between slices; traced as ('irq', vector))."""
        self.irq_request = irq
        self.uc.emu_stop()

    def _deliver_request(self):
        irq = self.irq_request
        fl = self.r(UC_X86_REG_EFLAGS)
        if not (fl & IF_) or (self.irq_mask >> irq & 1) or (self.in_service & ((1 << (irq + 1)) - 1)):
            return False
        self.irq_request = None
        self.in_service |= 1 << irq
        if self.trace is not None:
            self.trace.append(('irq', 8 + irq))
        self._enter(8 + irq, self.cs, self.ip)
        return True

    def _irq(self, irq):
        """Deliver a hardware interrupt if possible. Returns True if delivered."""
        fl = self.r(UC_X86_REG_EFLAGS)
        if not (fl & IF_) or (self.irq_mask >> irq & 1) or (self.in_service & ((1 << (irq + 1)) - 1)):
            return False
        n = 8 + irq
        if self.hooked(n):
            self.in_service |= 1 << irq
            self._enter(n, self.cs, self.ip)
        else:
            self._bios_irq(irq)
        return True

    def _bios_irq(self, irq):
        if irq == 0:
            t = struct.unpack('<I', self.rb(0x40, 0x6C, 4))[0] + 1
            self.wb(0x40, 0x6C, struct.pack('<I', t))
            if self.hooked(0x1C):
                self._enter(0x1C, self.cs, self.ip)
        elif irq == 1:
            sc = self.kbd_port
            if not sc & 0x80:
                name = next((k for k, v in SCANCODES.items() if v == sc), None)
                self.kbd_queue.append((sc, ASCII.get(name, 0)))

    # ------------------------------------------------------------ BIOS / DOS services
    def _service(self, n):
        if n == 0x21:
            self._dos()
        elif n == 0x10:
            self._video()
        elif n == 0x16:
            self._keyboard()
        elif n == 0x1A:
            ah = self.ax() >> 8
            if ah == 0:
                t = struct.unpack('<I', self.rb(0x40, 0x6C, 4))[0]
                self.w(UC_X86_REG_CX, t >> 16)
                self.w(UC_X86_REG_DX, t & 0xFFFF)
                self.w(UC_X86_REG_AX, 0)
            else:
                self.set_flag(CF, True)
        elif n == 0x11:
            self.w(UC_X86_REG_AX, 0x0021)
        elif n == 0x12:
            self.w(UC_X86_REG_AX, 640)
        elif n == 0x08:
            self._bios_irq0_from_stub()
        elif n == 0x09:
            self._bios_irq(1)
            self._eoi(1)
        elif n == 0x1C or n == 0x23 or n == 0x24 or n == 0x1B:
            pass
        elif n == 0x33:
            if self.ax() == 0:
                self.w(UC_X86_REG_AX, 0)
        elif n == 0x15:
            self.set_flag(CF, True)
            self.w(UC_X86_REG_AX, (0x86 << 8) | (self.ax() & 0xFF))
        elif n == 0x67 and self.ems is not None:
            self._ems()
        elif n == 0x67:
            self.w(UC_X86_REG_AX, 0x8400 | (self.ax() & 0xFF))
        elif n == 0x20:
            raise Exit()
        elif n == 0x2F:
            pass
        else:
            self.unknown.add(('int', n, self.ax() >> 8))

    def _ems(self):
        """A small EMM for tests: status, version, page frame, page counts, allocate, map,
        release, save / restore the map. self.ems holds 'frame', 'free', 'total', 'fail' (a
        function number that fails with 80h) and the handles given out."""
        e, ah, al = self.ems, self.ax() >> 8, self.ax() & 0xFF
        status = 0x80 if e.get('fail') == ah else 0
        if not status:
            if ah == 0x46:
                al = e.get('version', 0x40)
            elif ah == 0x41:
                self.w(UC_X86_REG_BX, e.get('frame', 0xE000))
            elif ah == 0x42:
                self.w(UC_X86_REG_BX, e.get('free', 16))
                self.w(UC_X86_REG_DX, e.get('total', 16))
            elif ah == 0x43:
                e['handle'] = e.get('handle', 0) + 1
                self.w(UC_X86_REG_DX, e['handle'])
            elif ah == 0x44:
                e.setdefault('mapped', []).append((al, self.r(UC_X86_REG_BX), self.r(UC_X86_REG_DX)))
        self.w(UC_X86_REG_AX, status << 8 | al)

    def _eoi(self, irq):
        self.in_service &= ~(1 << irq)

    def _bios_irq0_from_stub(self):
        # the program's INT 8 handler chained to the BIOS one
        t = struct.unpack('<I', self.rb(0x40, 0x6C, 4))[0] + 1
        self.wb(0x40, 0x6C, struct.pack('<I', t))
        self._eoi(0)
        if self.hooked(0x1C):
            cs, ip = self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)
            self.pending = ("int", 0x1C, cs, ip)
            self.uc.emu_stop()

    def _keyboard(self):
        ah = self.ax() >> 8
        if ah in (0x00, 0x10):
            if not self.kbd_queue:
                cs, ip = self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)
                self.pending = ('wait_key', cs, ip)
                self.uc.emu_stop()
                return
            sc, ch = self.kbd_queue.pop(0)
            self.w(UC_X86_REG_AX, (sc << 8) | ch)
        elif ah in (0x01, 0x11):
            if self.kbd_queue:
                sc, ch = self.kbd_queue[0]
                self.w(UC_X86_REG_AX, (sc << 8) | ch)
                self.set_flag(ZF, False)
            else:
                self.set_flag(ZF, True)
        elif ah in (0x02, 0x12):
            self.w(UC_X86_REG_AX, self.ax() & 0xFF00)
        else:
            self.unknown.add(('int16', ah))

    def _video(self):
        ax = self.ax()
        ah, al = ax >> 8, ax & 0xFF
        v = self.vga
        if ah == 0x00:
            v.set_mode(al & 0x7F, clear=not (al & 0x80))
            self.wb(0x40, 0x49, bytes([al & 0x7F]))
            self.ww(0x40, 0x4A, 40 if (al & 0x7F) in (0x0D, 0x13, 0, 1) else 80)
            self.log.append(f'video mode {al & 0x7F:02X}h at tick {self.ticks}')
        elif ah == 0x0F:
            self.w(UC_X86_REG_AX, (self.rw(0x40, 0x4A) & 0xFF) << 8 | v.mode)
            self.w(UC_X86_REG_BX, self.r(UC_X86_REG_BX) & 0xFF)
        elif ah == 0x05:
            if v.mode == 0x0D:
                start = (al & 7) * 0x2000
            elif v.mode == 0x10:
                start = (al & 1) * 0x8000
            elif v.mode == 0x0E:
                start = (al & 3) * 0x4000
            else:
                start = 0
            v.crtc[0x0C], v.crtc[0x0D] = start >> 8, start & 0xFF
            self.wb(0x40, 0x62, bytes([al]))
        elif ah == 0x10:
            bx = self.r(UC_X86_REG_BX)
            if al == 0x00:
                v.attr[bx & 0x1F] = bx >> 8
            elif al == 0x02:
                es, dx = self.r(UC_X86_REG_ES), self.r(UC_X86_REG_DX)
                v.attr[:16] = list(self.rb(es, dx, 16))
            elif al == 0x10:
                cx, dx = self.r(UC_X86_REG_CX), self.r(UC_X86_REG_DX)
                i = (bx & 0xFF) * 3
                v.dac[i:i + 3] = bytes(((dx >> 8) & 63, (cx >> 8) & 63, cx & 63))
            elif al == 0x12:
                es, dx, cx = self.r(UC_X86_REG_ES), self.r(UC_X86_REG_DX), self.r(UC_X86_REG_CX)
                data = bytes(b & 63 for b in self.rb(es, dx, cx * 3))
                i = (bx & 0xFF) * 3
                v.dac[i:i + len(data)] = data[:768 - i]
            elif al == 0x15:
                i = (bx & 0xFF) * 3
                self.w(UC_X86_REG_DX, v.dac[i] << 8 | (self.r(UC_X86_REG_DX) & 0xFF))
                self.w(UC_X86_REG_CX, v.dac[i + 1] << 8 | v.dac[i + 2])
            elif al == 0x17:
                es, dx, cx = self.r(UC_X86_REG_ES), self.r(UC_X86_REG_DX), self.r(UC_X86_REG_CX)
                i = (bx & 0xFF) * 3
                self.wb(es, dx, v.dac[i:i + cx * 3])
            elif al in (0x01, 0x03):
                pass
            else:
                self.unknown.add(('int10', 0x10, al))
        elif ah == 0x12:
            bl = self.r(UC_X86_REG_BX) & 0xFF
            if bl == 0x10:
                self.w(UC_X86_REG_BX, 0x0003)
                self.w(UC_X86_REG_CX, 0x0009)
        elif ah == 0x1A:
            if al == 0:
                self.w(UC_X86_REG_AX, 0x001A)
                self.w(UC_X86_REG_BX, 0x0008)
        elif ah == 0x0E:
            self.console.append(chr(al))
        elif ah in (0x09, 0x0A):
            self.console.append(chr(al) * max(1, min(80, self.r(UC_X86_REG_CX))))
        elif ah == 0x03:
            self.w(UC_X86_REG_DX, 0)
            self.w(UC_X86_REG_CX, 0x0607)
        elif ah == 0x08:
            self.w(UC_X86_REG_AX, 0x0720)
        elif ah in (0x01, 0x02, 0x06, 0x07, 0x0B, 0x11, 0x13):
            pass
        else:
            self.unknown.add(('int10', ah, al))

    # ---- DOS
    def _path(self, name):
        name = name.replace('/', '\\')
        base = name.split('\\')[-1].split(':')[-1]
        for f in os.listdir(self.game_dir):
            if f.upper() == base.upper():
                return os.path.join(self.game_dir, f)
        return os.path.join(self.game_dir, base.upper())

    def _err(self, code):
        self.w(UC_X86_REG_AX, code)
        self.set_flag(CF, True)

    def _alloc(self, paras):
        for i, (seg, size, used) in enumerate(self.blocks):
            if not used and size >= paras + 1:
                rest = size - paras - 1
                self.blocks[i] = [seg, paras + 1, True]
                if rest > 0:
                    self.blocks.insert(i + 1, [seg + paras + 1, rest, False])
                return seg + 1
        return None

    def _largest(self):
        return max([size - 1 for seg, size, used in self.blocks if not used] + [0])

    def _free(self, seg):
        for i, b in enumerate(self.blocks):
            if b[0] + 1 == seg and b[2]:
                b[2] = False
                self._merge()
                return True
        return False

    def _merge(self):
        i = 0
        while i + 1 < len(self.blocks):
            a, b = self.blocks[i], self.blocks[i + 1]
            if not a[2] and not b[2]:
                a[1] += b[1]
                del self.blocks[i + 1]
            else:
                i += 1

    def _dos(self):
        ax = self.ax()
        ah, al = ax >> 8, ax & 0xFF
        R, W = self.r, self.w
        ds, dx, bx, cx = R(UC_X86_REG_DS), R(UC_X86_REG_DX), R(UC_X86_REG_BX), R(UC_X86_REG_CX)
        ok = lambda: self.set_flag(CF, False)  # noqa: E731
        if ah == 0x4C:
            self.exit_code = al
            raise Exit()
        elif ah == 0x00:
            raise Exit()
        elif ah == 0x09:
            s = self.rb(ds, dx, 512).split(b'$')[0].decode('latin1')
            self.console.append(s)
        elif ah in (0x02, 0x06) and (dx & 0xFF) != 0xFF:
            self.console.append(chr(dx & 0xFF))
        elif ah == 0x06:
            if self.kbd_queue:
                sc, ch = self.kbd_queue.pop(0)
                W(UC_X86_REG_AX, (ah << 8) | ch)
                self.set_flag(ZF, False)
            else:
                W(UC_X86_REG_AX, ah << 8)
                self.set_flag(ZF, True)
        elif ah in (0x01, 0x07, 0x08):
            if not self.kbd_queue:
                self.pending = ('wait_key', R(UC_X86_REG_CS), R(UC_X86_REG_IP))
                self.uc.emu_stop()
                return
            sc, ch = self.kbd_queue.pop(0)
            W(UC_X86_REG_AX, (ah << 8) | ch)
        elif ah == 0x0B:
            W(UC_X86_REG_AX, (ah << 8) | (0xFF if self.kbd_queue else 0))
        elif ah == 0x0C:
            self.kbd_queue.clear()
        elif ah == 0x0E:
            W(UC_X86_REG_AX, (ah << 8) | 3)
        elif ah == 0x19:
            W(UC_X86_REG_AX, (ah << 8) | 2)
        elif ah == 0x1A:
            self.dta = (ds, dx)
        elif ah == 0x25:
            self.uc.mem_write(al * 4, struct.pack('<HH', dx, ds))
            self.log.append(f'set vector {al:02X}h -> {ds - LOAD_SEG & 0xFFFF:04X}:{dx:04X} (file seg) at tick {self.ticks}')
        elif ah == 0x35:
            seg, off = self.ivt(al)
            W(UC_X86_REG_ES, seg)
            W(UC_X86_REG_BX, off)
        elif ah == 0x2A:
            W(UC_X86_REG_CX, 1992)
            W(UC_X86_REG_DX, 0x0101)
            W(UC_X86_REG_AX, (ah << 8) | 3)
        elif ah == 0x2C:
            t = self.ticks * 10000 // 182
            W(UC_X86_REG_CX, ((t // 360000) % 24) << 8 | (t // 6000) % 60)
            W(UC_X86_REG_DX, ((t // 100) % 60) << 8 | t % 100)
        elif ah in (0x2B, 0x2D):
            W(UC_X86_REG_AX, ah << 8)
        elif ah == 0x2F:
            W(UC_X86_REG_ES, self.dta[0])
            W(UC_X86_REG_BX, self.dta[1])
        elif ah == 0x30:
            W(UC_X86_REG_AX, 0x0005)
            W(UC_X86_REG_BX, 0)
            W(UC_X86_REG_CX, 0)
        elif ah == 0x33:
            W(UC_X86_REG_DX, R(UC_X86_REG_DX) & 0xFF00)
        elif ah == 0x36:
            W(UC_X86_REG_AX, 8)
            W(UC_X86_REG_BX, 20000)
            W(UC_X86_REG_CX, 512)
            W(UC_X86_REG_DX, 40000)
        elif ah in (0x3B, 0x0D):
            ok()
        elif ah in (0x3C, 0x5B):
            name = self.asciiz(ds, dx)
            try:
                f = open(self._path(name), 'w+b')
            except OSError:
                return self._err(5)
            h = self.next_handle
            self.next_handle += 1
            self.files[h] = [f, name]
            self.log.append(f'create {name} -> {h}')
            W(UC_X86_REG_AX, h)
            ok()
        elif ah == 0x3D:
            name = self.asciiz(ds, dx)
            p = self._path(name)
            if not os.path.isfile(p):
                self.log.append(f'open {name}: not found')
                return self._err(2)
            f = open(p, 'rb' if (al & 3) == 0 else 'r+b')
            h = self.next_handle
            self.next_handle += 1
            self.files[h] = [f, name]
            self.log.append(f'open {name} -> {h}')
            W(UC_X86_REG_AX, h)
            ok()
        elif ah == 0x3E:
            f = self.files.pop(bx, None)
            if f:
                f[0].close()
            ok()
        elif ah == 0x3F:
            if bx in self.files:
                data = self.files[bx][0].read(cx)
                self.wb(ds, dx, data) if data else None
                W(UC_X86_REG_AX, len(data))
                ok()
            elif bx == 0:
                W(UC_X86_REG_AX, 0)
                ok()
            else:
                self._err(6)
        elif ah == 0x40:
            data = self.rb(ds, dx, cx) if cx else b''
            if bx in (1, 2):
                self.console.append(data.decode('latin1'))
            elif bx in self.files:
                f = self.files[bx][0]
                if cx == 0:
                    f.truncate()
                else:
                    f.write(data)
            else:
                return self._err(6)
            W(UC_X86_REG_AX, cx)
            ok()
        elif ah == 0x41:
            p = self._path(self.asciiz(ds, dx))
            if os.path.isfile(p):
                os.remove(p)
                ok()
            else:
                self._err(2)
        elif ah == 0x42:
            if bx not in self.files:
                return self._err(6)
            off = (cx << 16) | dx
            if off & 0x80000000:
                off -= 1 << 32
            f = self.files[bx][0]
            f.seek(off, al)
            pos = f.tell()
            W(UC_X86_REG_AX, pos & 0xFFFF)
            W(UC_X86_REG_DX, pos >> 16)
            ok()
        elif ah == 0x43:
            p = self._path(self.asciiz(ds, dx))
            if os.path.isfile(p):
                W(UC_X86_REG_CX, 0x20)
                ok()
            else:
                self._err(2)
        elif ah == 0x44:
            if al == 0 and bx <= 4:
                W(UC_X86_REG_DX, 0x80D3)
                ok()
            elif al == 0 and bx in self.files:
                W(UC_X86_REG_DX, 0x0002)
                ok()
            else:
                self._err(1)
        elif ah == 0x47:
            self.wb(ds, R(UC_X86_REG_SI), b'\0')
            ok()
        elif ah == 0x48:
            seg = self._alloc(bx)
            if seg is None:
                W(UC_X86_REG_BX, self._largest())
                self.log.append(f'alloc {bx:#x} paragraphs FAILED (largest {self._largest():#x})')
                return self._err(8)
            self.log.append(f'alloc {bx:#x} paragraphs -> {seg:04X}')
            W(UC_X86_REG_AX, seg)
            ok()
        elif ah == 0x49:
            es = R(UC_X86_REG_ES)
            if self._free(es):
                ok()
            else:
                self._err(9)
        elif ah == 0x4A:
            es = R(UC_X86_REG_ES)
            for i, b in enumerate(self.blocks):
                if (b[0] == es and i == 0) or (b[0] + 1 == es and i > 0):
                    hdr = 0 if i == 0 else 1
                    avail = b[1] - hdr
                    if i + 1 < len(self.blocks) and not self.blocks[i + 1][2]:
                        avail += self.blocks[i + 1][1]
                    if bx > avail:
                        W(UC_X86_REG_BX, avail)
                        return self._err(8)
                    total = b[1] + (self.blocks[i + 1][1] if i + 1 < len(self.blocks) and not self.blocks[i + 1][2] else 0)
                    if i + 1 < len(self.blocks) and not self.blocks[i + 1][2]:
                        del self.blocks[i + 1]
                    b[1] = bx + hdr
                    if total - b[1] > 0:
                        self.blocks.insert(i + 1, [b[0] + b[1], total - b[1], False])
                    self.log.append(f'resize block {es:04X} to {bx:#x} paragraphs')
                    return ok()
            self._err(9)
        elif ah in (0x4E, 0x4F):
            self._find(ah, ds, dx)
        elif ah in (0x51, 0x62):
            W(UC_X86_REG_BX, PSP_SEG)
        elif ah == 0x57:
            W(UC_X86_REG_CX, 0)
            W(UC_X86_REG_DX, 0x1621)
            ok()
        elif ah == 0x59:
            W(UC_X86_REG_AX, 2)
        elif ah == 0x56:
            ok()
        else:
            self.unknown.add(('int21', ah, al))
            self._err(1)

    def _find(self, ah, ds, dx):
        import fnmatch
        if ah == 0x4E:
            pat = self.asciiz(ds, dx).split('\\')[-1].upper()
            names = sorted(f.upper() for f in os.listdir(self.game_dir)
                           if fnmatch.fnmatch(f.upper(), pat if '.' in pat else pat + '.*') or f.upper() == pat)
            self.find_state = names
        names = self.find_state or []
        if not names:
            return self._err(18)
        name = names.pop(0)
        st = os.stat(self._path(name))
        seg, off = self.dta
        rec = bytearray(43)
        rec[0x15] = 0x20
        struct.pack_into('<HHI', rec, 0x16, 0, 0x1621, st.st_size)
        rec[0x1E:0x1E + len(name) + 1] = name.encode() + b'\0'
        self.wb(seg, off, rec)
        self.set_flag(CF, False)

    # ------------------------------------------------------------ running
    def press(self, tick, name, hold=1):
        sc = SCANCODES[name]
        self.key_events.append((tick, sc))
        self.key_events.append((tick + hold, sc | 0x80))
        self.key_events.sort()

    def _apply_pending(self):
        p, self.pending = self.pending, None
        kind = p[0]
        if kind == 'int':
            self.cs, self.ip = p[2], p[3]
            self._enter(p[1], p[2], p[3])
        elif kind == 'fault':
            self._clear_exception_state()
            if self.hooked(p[1]):
                self.faults = getattr(self, 'faults', 0) + 1
                self._enter(p[1], p[2], p[3])
            else:
                self.log.append(f'CPU exception {p[1]} at {p[2]:04x}:{p[3]:04x}')
                self.blocked = f'unhandled CPU exception {p[1]} at {p[2]:04x}:{p[3]:04x}'
        elif kind == 'exit':
            self.blocked = 'program exited'
        elif kind == 'wait_key':
            # re-run the INT once a key is available; let time pass meanwhile
            self.cs, self.ip = p[1], p[2]
            if not self.key_events and not self.kbd_queue:
                self.blocked = 'waiting for a key with no scripted keys left'
            else:
                self.instr = max(self.instr, self.next_irq0)

    _CTX_REGS = [UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI,
                 UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS, UC_X86_REG_CS,
                 UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS, UC_X86_REG_FS, UC_X86_REG_GS]

    def _clear_exception_state(self):
        """Unicorn hands CPU faults to our hook without completing delivery, so QEMU still
        believes an exception is in progress and turns the next divide error into a double
        fault. Restoring a pristine CPU context and re-writing the registers clears that."""
        uc = self.uc
        vals = [uc.reg_read(r) for r in self._CTX_REGS]
        uc.context_restore(self._clean_ctx)
        for r, v in zip(self._CTX_REGS, vals):
            uc.reg_write(r, v)

    def run(self, ticks=None, until=None, max_seconds=None):
        """Run until `ticks` virtual timer ticks have elapsed, until(self) is true, or the
        program exits/blocks. Returns the reason."""
        uc = self.uc
        t_end = None if ticks is None else self.ticks + ticks
        wall = time.time()
        while True:
            if self.blocked:
                return self.blocked
            if t_end is not None and self.ticks >= t_end:
                return 'ticks'
            if until is not None and until(self):
                return 'until'
            if max_seconds is not None and time.time() - wall > max_seconds:
                return 'wall-clock limit'
            # Hardware events. The keyboard is offered first: with the timer reprogrammed to
            # 16.5 kHz (the game's PC-speaker sample player) a timer interrupt is due at almost
            # every boundary and would otherwise starve it.
            period = max(40, INSTR_PER_TICK * self.pit_divisor // 65536)
            delivered = False
            if self.key_events and self.key_events[0][0] <= self.ticks:
                sc = self.key_events[0][1]
                if self.hooked(9):
                    self.kbd_port = sc
                    if self._irq(1):
                        self.key_events.pop(0)
                        delivered = True
                else:
                    self.kbd_port = sc
                    self.key_events.pop(0)
                    self._bios_irq(1)
            if not delivered and self.instr >= self.next_irq0:
                if self._irq(0):
                    self.next_irq0 += period
                    self._tick_fraction = getattr(self, '_tick_fraction', 0) + self.pit_divisor
                    while self._tick_fraction >= 65536:
                        self._tick_fraction -= 65536
                        self.ticks += 1
                elif self.instr > self.next_irq0 + 50 * period:
                    self.next_irq0 = self.instr  # interrupts held off for a long time; do not pile up
            n = max(32, min(SLICE, self.next_irq0 - self.instr))
            try:
                self.step(0, n)
            except UcError as e:
                self.cs, self.ip = self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)
                where = f'{self.cs:04x}:{self.ip:04x} (file {self.cs - LOAD_SEG & 0xFFFF:04X}:{self.ip:04X})'
                self.blocked = f'CPU error {e} at {where}'
                return self.blocked
            self.instr += n
            if self.pending is not None:
                self._apply_pending()

    # ------------------------------------------------------------ calling single routines
    REG_BY_NAME = {'ax': UC_X86_REG_AX, 'bx': UC_X86_REG_BX, 'cx': UC_X86_REG_CX, 'dx': UC_X86_REG_DX,
                   'si': UC_X86_REG_SI, 'di': UC_X86_REG_DI, 'bp': UC_X86_REG_BP, 'sp': UC_X86_REG_SP,
                   'ds': UC_X86_REG_DS, 'es': UC_X86_REG_ES, 'ss': UC_X86_REG_SS, 'flags': UC_X86_REG_EFLAGS}
    DATA_SEG = LOAD_SEG + 0x5C27     # the game's main data segment at run time

    def call(self, seg, off, far=False, max_instr=20_000_000, stack=(), irqs=False, **regs):
        """Run one routine of the game to its return, with interrupts off, and return the
        registers afterwards. seg:off is a file address (as in the disassembly). Registers not
        given keep their current values, except DS and ES which default to the main data
        segment. `stack` is a sequence of words pushed before the call (last one pushed first,
        so stack[0] ends up at the lowest address, like C arguments). irqs: run with interrupts
        enabled, for the IRQs devices raise (raise_irq)."""
        uc = self.uc
        cs = (seg + LOAD_SEG) & 0xFFFF
        regs.setdefault('ds', self.DATA_SEG)
        regs.setdefault('es', self.DATA_SEG)
        for name, val in regs.items():
            uc.reg_write(self.REG_BY_NAME[name], val & 0xFFFF)
        uc.reg_write(UC_X86_REG_EFLAGS, uc.reg_read(UC_X86_REG_EFLAGS) & ~(IF_ | TF) & 0xFFFF | 2 | (IF_ if irqs else 0))
        ss, sp = self.r(UC_X86_REG_SS), self.r(UC_X86_REG_SP)
        sp_before = sp
        for wv in reversed(stack):
            sp = (sp - 2) & 0xFFFF
            self.ww(ss, sp, wv)
        if far:
            ret_cs, ret_ip = BIOS_SEG, 0xFF00
            sp = (sp - 4) & 0xFFFF
            self.wb(ss, sp, struct.pack('<HH', ret_ip, ret_cs))
        else:
            ret_cs, ret_ip = cs, 0xFFFF
            sp = (sp - 2) & 0xFFFF
            self.ww(ss, sp, ret_ip)
        self.w(UC_X86_REG_SP, sp)
        until = ((ret_cs << 4) + ret_ip) & 0xFFFFF
        self.cs, self.ip = cs, off
        self.pending = None
        budget = max_instr
        while True:
            step = min(budget, 1_000_000)
            self.step(until, step)
            budget -= step
            if self.pending is not None:
                self._apply_pending()
                if self.blocked:
                    raise RuntimeError(self.blocked)
                continue
            if self.irq_request is not None and self._deliver_request():
                continue
            if ((self.cs << 4) + self.ip) & 0xFFFFF == until:
                break
            if budget <= 0:
                raise RuntimeError(f'routine did not return within {max_instr} instructions '
                                   f'(at file {self.file_addr()})')
        out = {name: self.r(reg) for name, reg in self.REG_BY_NAME.items()}
        self.w(UC_X86_REG_SP, sp_before)      # drop the arguments, as a cdecl caller would
        return out

    def ds_read(self, off, n):
        return self.rb(self.DATA_SEG, off, n)

    def ds_write(self, off, data):
        self.wb(self.DATA_SEG, off, data)

    # ------------------------------------------------------------ output
    def screenshot(self, path):
        from PIL import Image
        s = self.vga.screenshot()
        if s is None:
            return False
        w, h, data = s
        Image.frombytes('RGB', (w, h), data).save(path)
        return True

    def text_screen(self):
        raw = bytes(self.uc.mem_read(0xB8000, 4000))
        return '\n'.join(''.join(chr(c) if 32 <= c < 127 else ' ' for c in raw[r * 160:r * 160 + 160:2]).rstrip()
                         for r in range(25))

    def file_addr(self):
        return f'{self.cs - LOAD_SEG & 0xFFFF:04X}:{self.ip:04X}'

    # ------------------------------------------------------------ snapshots
    REGS = [UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX, UC_X86_REG_SI, UC_X86_REG_DI,
            UC_X86_REG_BP, UC_X86_REG_SP, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS, UC_X86_REG_EFLAGS,
            UC_X86_REG_FS, UC_X86_REG_GS]

    def save(self, path):
        st = {
            'regs': [self.r(x) for x in self.REGS], 'cs': self.cs, 'ip': self.ip,
            'low': bytes(self.uc.mem_read(0, 0xA0000)), 'high': bytes(self.uc.mem_read(0xB0000, 0x60000)),
            'vga': {k: (bytes(v) if isinstance(v, bytearray) else v) for k, v in self.vga.__dict__.items()
                    if k not in ('planes', 'clock')},
            'planes': [bytes(p) for p in self.vga.planes],
            'files': {h: (name, f.tell(), f.mode) for h, (f, name) in self.files.items()},
            'state': {k: getattr(self, k) for k in (
                'next_handle', 'blocks', 'dta', 'find_state', 'ticks', 'instr', 'next_irq0', 'pit_divisor',
                'irq_mask', 'in_service', 'kbd_queue', 'kbd_port', 'key_events', 'console', 'log')},
        }
        with open(path, 'wb') as f:
            pickle.dump(st, f)

    def load(self, path):
        st = pickle.load(open(path, 'rb'))
        for x, v in zip(self.REGS, st['regs']):
            self.uc.reg_write(x, v)
        self.cs, self.ip = st['cs'], st['ip']
        self.uc.mem_write(0, st['low'])
        self.uc.mem_write(0xB0000, st['high'])
        for k, v in st['vga'].items():
            setattr(self.vga, k, bytearray(v) if isinstance(v, bytes) else v)
        self.vga.planes = [bytearray(p) for p in st['planes']]
        for h, (name, pos, mode) in st['files'].items():
            f = open(self._path(name), mode)
            f.seek(pos)
            self.files[h] = [f, name]
        for k, v in st['state'].items():
            setattr(self, k, v)
        self.pending = None
        self.blocked = None

    def write_coverage(self, path):
        """Merge executed block addresses (file segment:offset) into a text file."""
        have = set()
        if os.path.exists(path):
            have = {ln.strip() for ln in open(path) if ln.strip() and not ln.startswith('#')}
        base = LOAD_SEG * 16
        segs = [0x0000, 0x0FBA, 0x101F, 0x10BB, 0x11BC, 0x14A7, 0x14B5, 0x151B, 0x15AD, 0x1609, 0x1720,
                0x5776, 0x57C5, 0x5819, 0x5A4D, 0x5B0D, 0x5B1D, 0x5B48, 0x5B67, 0x5C01, 0x5C27]
        for a in self.coverage:
            rel = a - base
            if 0 <= rel < 0x6ACE0:
                seg = max(s for s in segs if s * 16 <= rel)
                have.add(f'{seg:04X}:{rel - seg * 16:04X}')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write('# code block starts executed under tools/dosemu.py (file segment:offset)\n')
            f.write('\n'.join(sorted(have)) + '\n')
        return len(have)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['run'])
    ap.add_argument('--ticks', type=int, default=200)
    ap.add_argument('--keys', default='')
    ap.add_argument('--shots')
    ap.add_argument('--every', type=int, default=18)
    ap.add_argument('--coverage', action='store_true')
    ap.add_argument('--save')
    ap.add_argument('--load')
    ap.add_argument('--args', default='')
    a = ap.parse_args()
    m = Machine(args=a.args, coverage=a.coverage)
    if a.load:
        m.load(a.load)
    for item in filter(None, a.keys.split(',')):
        t, name = item.split(':')
        m.press(int(t), name.strip())
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
    t0 = time.time()
    end = m.ticks + a.ticks
    reason = 'ticks'
    while m.ticks < end:
        reason = m.run(ticks=min(a.every, end - m.ticks))
        if a.shots:
            m.screenshot(os.path.join(a.shots, f'shot_{m.ticks:05d}.png'))
        if reason != 'ticks':
            break
    print(f'stopped: {reason}; tick {m.ticks}, {m.instr} instructions, at file {m.file_addr()}, '
          f'video mode {m.vga.mode:02X}h, {time.time() - t0:.1f}s wall')
    print('console:', repr(''.join(m.console))[:600])
    for ln in m.log[-40:]:
        print('  log:', ln)
    if m.unknown:
        print('unhandled services:', sorted(m.unknown))
    if m.port_log:
        print('unhandled ports:', {f'{k[0]} {k[1]:#x}': v for k, v in sorted(m.port_log.items())})
    if a.coverage:
        n = m.write_coverage(os.path.join(ROOT, 'disasm', 'coverage.txt'))
        print('coverage entries:', n)
    if a.save:
        m.save(a.save)


if __name__ == '__main__':
    main()
