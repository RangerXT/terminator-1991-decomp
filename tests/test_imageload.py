"""Shared image loader vs original: real file reads and synthetic in-memory cache.

Only DOS open/read/close are supplied by the host. No decoder, game state or
screen effects are replayed. LZHUF private tables/bit reader are excluded, as in the
existing image-unpack tests; its entire history ring is still compared.
"""
import ctypes
import io
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import Game, make_game
from test_polyfill import planes_of, screen_differences
from test_imageunpack import write_wrapped
import dosemu

CASES = 0
ImageCall = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(Game), ctypes.c_uint16,
                            ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16,
                            ctypes.c_uint16, ctypes.c_void_p)


class ImageIO(ctypes.Structure):
    _fields_ = [('call', ImageCall), ('user', ctypes.c_void_p)]


def regions(m):
    stack = m.r(dosemu.UC_X86_REG_SS) << 4
    scratch = (dosemu.LOAD_SEG + 0x5819) << 4
    excluded = sorted([(stack, stack + 1024), (scratch + 4, scratch + 0x113A),
                       (scratch + 0x233A, scratch + 0x233B)])
    result, start = [], 0
    for lo, hi in excluded:
        result.append((start, lo))
        start = hi
    return result + [(start, 0xA0000)]


def check_memory(got, want, spans):
    for lo, hi in spans:
        if got[lo:hi] != want[lo:hi]:
            first = next(i for i in range(lo, hi) if got[i] != want[i])
            return f'first memory difference {first:05X}'
    return None


class Files:
    """Real asset bytes and independent DOS-style handles; never writes game files."""
    def __init__(self, m, record=True):
        self.machine, self.next_handle, self.handles = m, m.next_handle, {}
        self.calls, self.record = [], record
        self.callback = ImageCall(self.call)
        self.host = ImageIO(self.callback, None)

    def call(self, gp, op, handle, seg, off, count, user):
        g = gp.contents
        if self.record:
            self.calls.append(((op, handle, seg, off, count),
                               ctypes.string_at(g.mem, 0xA0000),
                               ctypes.string_at(g.planes, 4 * 65536 + 16)))
        if op == 0x43:
            ptr = g.mem + (((seg << 4) + off) & 0xFFFFF)
            name = ctypes.string_at(ptr, 256).split(bytes([0]), 1)[0].decode('ascii')
            return 0 if os.path.isfile(self.machine._path(name)) else 0x10002
        if op == 0x3D:
            ptr = g.mem + (((seg << 4) + off) & 0xFFFFF)
            name = ctypes.string_at(ptr, 256).split(b'\0', 1)[0].decode('ascii')
            path = self.machine._path(name)
            if not os.path.isfile(path):
                return 0x10002
            data = open(path, 'rb').read()
            new_handle = self.next_handle
            self.next_handle += 1
            self.handles[new_handle] = io.BytesIO(data)
            return new_handle
        if op == 0x3F:
            if getattr(self, 'fail_read', False):
                return 0x10005
            if handle not in self.handles:
                return 0x10006
            data = self.handles[handle].read(count)
            ctypes.memmove(g.mem + (((seg << 4) + off) & 0xFFFFF), data, len(data))
            return len(data)
        if op == 0x3E:
            stream = self.handles.pop(handle, None)
            if stream:
                stream.close()
            return 0
        return 0xFFFFFFFF


def trace_dos(m):
    old = m._dos
    m.image_calls = []
    def logged():
        ax = m.ax()
        op = ax >> 8
        if op in (0x3D, 0x43):
            args = (op, ax & 255, m.r(dosemu.UC_X86_REG_DS), m.r(dosemu.UC_X86_REG_DX), 0)
        elif op == 0x3F:
            args = (op, m.r(dosemu.UC_X86_REG_BX), m.r(dosemu.UC_X86_REG_DS),
                    m.r(dosemu.UC_X86_REG_DX), m.r(dosemu.UC_X86_REG_CX))
        elif op == 0x3E:
            args = (op, m.r(dosemu.UC_X86_REG_BX), 0, 0, 0)
        else:
            return old()
        m.image_calls.append((args, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m)))
        return old()
    m._dos = logged


def assets(m):
    for name in ['FRAME.IMG', 'MAP.IMG', 'BMAP.IMG', 'HUD1.IMG', 'HUD6.IMG', 'PANEL.IMG']:
        path = m._path(name)
        if not os.path.isfile(path):
            continue
        raw = open(path, 'rb').read()
        header = struct.unpack_from('<8H', raw)
        if header[0] == 15 and header[1] == 4 and header[6] & 12:
            yield name, raw, header


def compare(label, mem, planes, m, spans, fails):
    error = check_memory(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans)
    error = error or screen_differences(planes.raw, planes_of(m))
    if error:
        fails.append(label + ': ' + error)


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    spans = regions(m)
    trace_dos(m)
    records = list(assets(m))
    if not {r[0] for r in records}.issuperset({'FRAME.IMG', 'MAP.IMG', 'BMAP.IMG'}):
        return ['missing required four-plane loader assets']
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    for name, raw, header in records:
        for variant in range(8):
            m.ds_write(0, saved)
            word(0x0208, 0)
            word(0xC4AE, 20 if variant & 1 else 0)
            word(0x805C, min(header[7] // 2, [0, 2200, 4000, 14000][variant % 4]))
            word(0x8082, 0x100 if variant & 2 else 0)
            word(0x1234, (variant % 3) * 0x2000)
            word(0x1228, 80 if header[2] > 320 else 40)
            m.ds_write(0x8088, bytes([variant & 1]))
            m.ds_write(0x8000, name.encode('ascii') + b'\0')
            m.vga.gc[3] = ((variant // 2) % 4) << 3
            m.vga.gc[5] = variant % 3
            g, mem, planes = make_game(m)
            native = Files(m)
            m.image_calls.clear()
            status = ctx.lib.image_load_screen(ctypes.byref(g), ctypes.byref(native.host), 0x8000)
            m.call(0, 0x6962, dx=0x8000, max_instr=120_000_000)
            CASES += 1
            label = f'{name} file {variant}'
            if status or len(native.calls) != len(m.image_calls):
                return [label + ': status/IO count differs']
            for c, original in zip(native.calls, m.image_calls):
                if c[0] != original[0]:
                    return [label + f': DOS arguments differ {c[0]} vs {original[0]}']
                error = check_memory(c[1], original[1], spans) or screen_differences(c[2], original[2])
                if error:
                    return [label + ' before DOS: ' + error]
            if native.handles or native.next_handle != m.next_handle:
                return [label + ': handle lifecycle differs']
            compare(label, mem, planes, m, spans, fails)
            if fails:
                return fails
    for name, raw, header in records:
        for variant in range(12):
            m.ds_write(0, saved)
            source = [0x100, 0xFFF0, 0xFFFE][variant % 3]
            write_wrapped(m, 0x7800, source, raw)
            word(0x0208, 0x7800)
            word(0xC4AE, 20)
            word(0x00B1, source)
            word(0x7B8A, [0, 0x100, 0xFFF0][(variant // 3) % 3])
            word(0x7B8C, 0x8800)
            word(0x805C, min(4000, header[7] // 2))
            word(0x1234, (variant % 3) * 0x2000)
            word(0x1228, 80 if header[2] > 320 else 40)
            m.ds_write(0x8088, bytes([variant & 1]))
            g, mem, planes = make_game(m)
            m.image_calls.clear()
            status = ctx.lib.image_load_screen(ctypes.byref(g), None, 0)
            m.call(0, 0x6962, max_instr=120_000_000)
            CASES += 1
            label = f'{name} cached {variant}'
            if status or m.image_calls:
                return [label + ': cache unexpectedly needs DOS']
            compare(label, mem, planes, m, spans, fails)
            if fails:
                return fails
    for i in range(8):
        m.ds_write(0, saved)
        name, raw, header = records[i % len(records)]
        write_wrapped(m, 0x7800, 0xFFF0, raw)
        word(0x0208, 0x7800)
        word(0xC4AE, 20)
        word(0x00B1, 0xFFF0)
        m.ds_write(0x8087, b'\xff')
        es = 0x7000 if i & 1 else m.DATA_SEG
        g, mem, planes = make_game(m)
        status = ctx.lib.image_prepare(ctypes.byref(g), None, 0, es)
        m.call(0, 0x6AAE, es=es)
        CASES += 1
        compare(f'cached header ES {es:04X}', mem, planes, m, spans, fails)
        if status or fails:
            return fails or ['cached header unavailable']
    print(f'    image service: {len(records)} real assets; native file bytes and cache paths; private LZHUF scratch excluded')
    return fails
