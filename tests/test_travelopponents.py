"""D177 composed with native simulation loop, interruption and encounter placement.

Only B5F9 (world-step body) and 3B88 (cell streaming) are stubbed on both sides.
No final/reference state is supplied to C. Compare their input state and all memory/EGA.
"""
import ctypes, os, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
from test_blast import set_clock
CASES = 0


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    active = [None]
    calls = []
    fails = []
    encounters = 0
    retries = 0
    for off in [0xB5F9, 0x3B88]:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')
        at = (dosemu.LOAD_SEG<<4)+off
        def hook(uc, address, size, ud, off=off):
            active[0](off, 0)
        m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
    for off in [0xBBF1, 0xC35F, 0xDC7B]:
        at = (dosemu.LOAD_SEG<<4)+off
        def watch(uc, address, size, ud, off=off):
            calls.append(off)
        m.uc.hook_add(UC_HOOK_CODE, watch, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    barriers = bytes(1 if (j%192)%9 == 0 else 0 for j in range(0x9000))
    modes = ['complete', 'accepted', 'health_retry', 'inventory_retry', 'space_retry']
    for i in range(160):
        mode = modes[i%5]
        player = [0x04D4, 0x0508][(i//5)%2]
        other = [0x0508, 0x04D4][(i//5)%2]
        m.ds_write(0, saved)
        word(0x03A0, player)
        word(0x04BA, other)
        word(player+10, 20)
        word(player+6, (i*37)%512)
        word(0xE272, 400)
        col = m.rw(m.DATA_SEG, player+30)
        row = m.rw(m.DATA_SEG, player+32)
        m.ds_write(0xE26A, struct.pack('<4H', col+1, row+1, 111, 777))
        word(other+28, 5 if mode == 'health_retry' else 200)
        word(other+26, 0)
        word(0x0558, 7 if i%4 == 0 else 200)
        word(0x0556, 0)
        m.ds_write(0x0359, b'\0')
        m.ds_write(0x034B, b'\0')
        word(0x1208, 0x100)
        word(0x120A, 0x8000)
        pairs = struct.unpack_from('<4H', saved, 0xDE3E)
        ids = [x for pair in pairs for x in [pair&255, pair>>8]]
        for j, item in enumerate(ids):
            m.wb(0x8000, 0x100+j*6, struct.pack('<H4B', 0, item, 0, 2, 0 if mode == 'inventory_retry' else 2))
        m.wb(0x8000, 0x130, bytes(6))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        for j in range(50):
            word(0x97B8+j*2, (i*1777+j*717)&65535)
        m.wb(m.rw(m.DATA_SEG, 0x91B2), 0, bytes(0x9000) if mode == 'space_retry' else barriers)
        for plane in m.vga.planes:
            plane[0x6000:0x8000] = bytes(8192)
        g, mem, planes = make_game(m)
        set_clock(ctx.lib, m)
        logs = [[], []]
        steps = [0, 0]
        calls.clear()
        def effect(which, read, write, service, arg):
            logs[which].append((service, read(0x0300, 0x300), read(0xE26A, 20), read(0xDE3C, 2)))
            # Same small independent IO effect proves the caller observes host writes.
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            if service == 0xB5F9:
                steps[which] += 1
                write(0x1153, bytes([255 if mode != 'complete' and steps[which] == 12 else 0]))
            elif service != 0x3B88:
                raise AssertionError('unexpected host service %04x'%service)
            return 0
        active[0] = lambda service, arg:effect(1, m.ds_read, m.ds_write, service, arg)
        errors = []
        @CALLBACK
        def callback(gp, service, arg, user):
            try:
                return effect(0, lambda off, n:ctypes.string_at(g.ds+off, n), lambda off, b:ctypes.memmove(g.ds+off, b, len(b)), service, arg)
            except Exception as exc:
                errors.append(repr(exc))
                return 0xFFFFFFFF
        host = Services(callback, None)
        status = ctx.lib.travel_run_native_opponents(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0xD177, max_instr=10_000_000)
        CASES += 1
        if status or errors or logs[0] != logs[1] or steps[0] != steps[1]:
            return ['composed travel %d %s: service state/status differs %s'%(i, mode, errors)]
        compare('composed travel %d %s'%(i, mode), mem, planes, m, fails)
        if fails:
            return fails
        if calls:
            encounters += 1
            expected = [0xBBF1] if player == 0x04D4 else [0xC35F, 0xDC7B]
            if calls != expected:
                return ['unexpected original encounter sequence %s'%calls]
        elif mode != 'complete':
            retries += 1
    print('    composed native travel: encounters=%d retries=%d; only world-step/cell IO external'%(encounters, retries))
    if encounters < 16 or retries < 16:
        return ['missing encounter/retry branches']
    return fails
