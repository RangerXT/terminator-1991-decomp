"""Native camera reset with real image bytes and independent emulator platform services."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_polyfill import planes_of
from test_imageload import Files, regions, compare
from test_mapsetupreal import RESOURCE, Resources
from test_blast import c_events, set_clock
from unicorn import UC_HOOK_CODE
CASES = 0

class Platform:
    def __init__(self, ctx, m):
        self.ctx = ctx
        self.vm = dosemu.Machine()
        self.vm.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        self.files = Files(m, record=False)
        self.calls = []
        self.callback = RESOURCE(self.service)
        self.host = Resources(self.callback, None)
    def service(self, gp, op, a, b, user):
        self.calls.append((op, a, b))
        g = gp.contents
        if op == 0x6962:
            return self.ctx.lib.image_map_service(gp, op, a, b, ctypes.cast(ctypes.byref(self.files.host), ctypes.c_void_p))
        vm = self.vm
        vm.uc.mem_write(0, ctypes.string_at(g.mem, 0xA0000))
        screen = ctypes.string_at(g.planes, 4*65536+16)
        card = screen[4*65536:]
        vm.vga.planes = [bytearray(screen[p*65536:(p+1)*65536]) for p in range(4)]
        vm.vga.seq[2] = card[0]
        vm.vga.gc[:9] = list(card[1:10])
        vm.vga.gc_index = card[10]
        vm.vga.latch = list(card[11:15])
        if op == 0xFF10:
            vm.w(dosemu.UC_X86_REG_AX, a)
            vm._video()
        elif op == 0x0C6B:
            vm.call(0, 0x0C6B, ax=a)
        elif op == 0x7AAF:
            vm.call(0, 0x7AAF)
        elif op == 0x0BE8:
            vm.call(0, 0x0BE8, dx=a)
        else:
            raise RuntimeError('Unexpected camera platform op %04x'%op)
        ctypes.memmove(g.mem, bytes(vm.uc.mem_read(0, 0xA0000)), 0xA0000)
        ctypes.memmove(g.planes, planes_of(vm), 4*65536+16)
        return 0

def run(ctx):
    global CASES
    fails = []
    for i in range(18):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0x11CA, bytes([1+i%2]))
        m.ds_write(0x1234, struct.pack('<H', i%3*0x2000))
        m.ds_write(0x8685, bytes([255 if i%3 else 0]))
        host = Platform(ctx, m)
        g, mem, planes = make_game(m)
        status = ctx.lib.camera_reset_full_view(ctypes.byref(g), ctypes.byref(host.host))
        m.call(0, 0x7946, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status:
            return ['camera reset unavailable %d'%i]
        compare('camera reset %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if host.calls != [(0xFF10, 13, 0), (0x0C6B, 2, 0), (0x7AAF, 0, 0), (0x6962, 0x915A, 0)]:
            return ['camera service order']
        if host.files.handles:
            return ['camera image handle leak']
    for i in range(12):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0x11CA, bytes([1]))
        m.ds_write(0x01DE, bytes([0]))
        m.ds_write(0x11A0, struct.pack('<H', 1))
        m.ds_write(0x10F0, bytes(72))
        x = 0 if i%2 else 800
        z = 0 if i%2 else 1000
        m.ds_write(0x10F0, struct.pack('<9H', x, 0, z, 128, 1, 0x8300, x, z, 65535))
        m.ds_write(0x8300, struct.pack('<6H', x, 0, z, 0x2000, 0, 0))
        m.ds_write(0x020E, bytes([0, 0]))
        m.ds_write(0x8685, bytes([255]))
        calls = []
        for kind, s, off, reg in [(1, 0, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0, 0x0A4F, dosemu.UC_X86_REG_BX), (4, 0x151B, 0x02DE, dosemu.UC_X86_REG_SI)]:
            m.wb(dosemu.LOAD_SEG+s, off, bytes([0xCB if s else 0xC3]))
            addr = ((dosemu.LOAD_SEG+s)<<4)+off
            def hook(uc, a, size, user, kind=kind, reg=reg):
                calls.append((kind, uc.reg_read(reg)&(255 if kind in [1, 5] else 65535)))
            m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
        host = Platform(ctx, m)
        g, mem, planes = make_game(m)
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.weapon_guided_projectiles_step_host(ctypes.byref(g), ctypes.byref(host.host))
        m.call(0, 0xD8D2, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['camera-impact status/events %d'%i]
        compare('projectile camera impact %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if len(host.calls) != 4:
            return ['camera impact missed reset']
    return fails
