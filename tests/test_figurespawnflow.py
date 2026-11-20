"""Complete AD00/AD37 spawning and AFD0 replacement with native dependencies."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    seg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(seg, 0, 0x9000)
    rng = random.Random(0xAD37)
    fails = []
    ctx.lib.figure_spawn_dx.restype = ctypes.c_uint16
    spawned = deferred = removed = replaced = 0
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value&65535))
    def prepare(i, count):
        m.ds_write(0, saved)
        m.wb(seg, 0, [collision, bytes(0x9000), bytes([1])*0x9000, bytes(1 if (j%192)%9 == 0 else 0 for j in range(0x9000))][i%4])
        word(0x119A, count)
        word(0x119C, count)
        word(0x03A4, 0xDF0+12*count)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *[rng.randrange(65536) for _ in range(200)]))
        for j in range(32):
            flags = [0, 2, 4, 10, 12, 16][(i+j)%6]
            m.ds_write(0xB30+j*22, struct.pack('<11H', flags, 0, 0, 0, 0, j%4, 0, j*7, 0x0301, 0, 0))
            m.ds_write(0xDF0+j*12, struct.pack('<6H', 100+j*10, 0, 400+j*5, 0x4000, j*2, 10))
        m.ds_write(0xB735, bytes([i%2]))
    for i in range(192):
        civilian = (i//4)%2
        count = [0, 1, 8, 27, 29, 30][(i//8)%6]
        requested = [0, 1, 2, 3][(i//48)%4]
        if civilian:
            requested = min(requested, 30-count)
        prepare(i, count)
        g, mem, planes = make_game(m)
        dx = ctx.lib.figure_spawn_dx(ctypes.byref(g), requested, civilian, 0x1234)
        out = m.call(0, 0xAD37 if civilian else 0xAD00, ax=requested, dx=0x1234, es=m.DATA_SEG, max_instr=50000000)
        if dx != out['dx']:
            return ['spawn DX %d: %x != %x'%(i, dx, out['dx'])]
        CASES += 1
        compare('spawn flow %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        if m.rw(m.DATA_SEG, 0x119A) > count:
            spawned += 1
        elif requested and m.rw(m.DATA_SEG, 0xB82A) == 0:
            deferred += 1
    for i in range(96):
        count = [1, 2, 8, 30][i%4]
        prepare(i, count)
        index = [0, count-1][(i//4)%2]
        record = 0xDF0+index*12
        word(0xB30+index*22, [0, 2, 4, 14][(i//8)%4])
        m.ds_write(0xB69F, bytes([(i//32)%2]))
        m.ds_write(0x115A, bytes([(i//64)%2]))
        g, mem, planes = make_game(m)
        ctx.lib.figure_remove_complete(ctypes.byref(g), record)
        m.call(0, 0xAFD0, bx=record, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        compare('remove/replace %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        removed += m.rw(m.DATA_SEG, 0x119A) < count
        replaced += m.rw(m.DATA_SEG, 0x119A) == count
    print('    figure flows: spawned=%d deferred=%d removed=%d replaced=%d'%(spawned, deferred, removed, replaced))
    if not all([spawned, deferred, removed, replaced]):
        return ['missing spawn/removal branch coverage']
    return fails
