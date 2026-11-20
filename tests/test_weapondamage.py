"""Single-player A07B damage against original with only sound/player-hit/serial bodies external."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    seg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(seg, 0, 0x9000)
    calls = []
    fails = []
    backing = m.ds_read(m.rw(m.DATA_SEG, 0x01FE), 12)
    for kind, s, o, reg in [(1, 0, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0, 0x0A4F, dosemu.UC_X86_REG_BX), (4, 0x151B, 0x02DE, dosemu.UC_X86_REG_SI)]:
        m.wb(dosemu.LOAD_SEG+s, o, bytes([0xCB if s else 0xC3]))
        addr = ((dosemu.LOAD_SEG+s)<<4)+o
        def hook(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&(255 if kind in [1, 5] else 65535)))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    def word(off, v):
        m.ds_write(off, struct.pack('<H', v&65535))
    killed = survived = missed = 0
    for i in range(384):
        m.ds_write(0, saved)
        variant = i%8
        damage = [0, 1, 10, 127, 128, 255][(i//8)%6]
        m.wb(seg, 0, bytes([1 if variant == 2 else 0])*0x9000)
        m.ds_write(0x01DE, bytes([0]))
        m.ds_write(0x7A18, bytes([0]))
        word(0x03A0, 0x0508)
        m.ds_write(0x508, struct.pack('<5H', 0, 100, 0, 0, 0))
        m.ds_write(0x516, bytes([i%2]))
        m.ds_write(0x521, bytes([0]))
        word(0x118E, 1)
        m.ds_write(0x575, bytes([damage]))
        word(0xB64C, 0xB520)
        word(0xB64E, 0 if variant == 0 else 2)
        word(0x11A2, 159)
        word(0x11A4, 60)
        word(0x118A, 0)
        word(0x118C, 0)
        m.ds_write(0x9000, backing)
        word(0xDE4C, 0x9000)
        word(0x119A, 2)
        word(0x119C, 2)
        word(0x03A4, 0xDF0+24)
        for j in range(3):
            m.ds_write(0xB30+j*22, struct.pack('<11H', [0, 2, 4, 14][(i//48)%4], 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            m.ds_write(0xDF0+j*12, struct.pack('<6H', 0, 0, 100, 0x4000, j*2, 127 if variant == 3 else 0))
        flags = 4 if variant == 5 else 32 if variant in [6, 7] else 0x4000
        word(0xDF6, flags)
        if variant == 5:
            m.ds_write(0x54A, bytes([1]))
            word(0x556, 99)
        if variant in [6, 7]:
            word(0x04BA, 0x508)
            word(0x522, 99)
            if variant == 7:
                m.ds_write(0x516, bytes([0]))
                word(0x538, 32767)
        for j in range(2):
            m.ds_write(0xB18E+j*18, struct.pack('<9H', 0xDF0+j*12, 0, 100, 200 if variant == 1 else 8, 220 if variant == 1 else 311, 8, 110, 0, 0))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.weapon_scan_damage(ctypes.byref(g))
        m.call(0, 0xA07B, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status:
            return ['unexpected damage status %d'%i]
        got = c_events(ctx.lib)
        if got != calls:
            return ['damage events %d: %s != %s'%(i, got, calls)]
        compare('weapon damage %d'%i, mem, planes, m, fails)
        if fails:
            raw = bytes(m.uc.mem_read(0, 0xA0000))
            ours = mem.raw[:0xA0000]
            diffs = [j for j in range(0xA0000) if ours[j] != raw[j]]
            print('damage case', i, 'events', calls, 'differences', [(hex(j), ours[j], raw[j]) for j in diffs[:60]])
            print('DS differences', [(hex(j-(m.DATA_SEG<<4)), ours[j], raw[j]) for j in diffs if (m.DATA_SEG<<4) <= j < (m.DATA_SEG<<4)+0xEA70][:30])
            return fails
        killed += m.rw(m.DATA_SEG, 0x119A) < 2
        survived += m.rw(m.DATA_SEG, 0x037C) != struct.unpack_from('<H', saved, 0x037C)[0] and m.rw(m.DATA_SEG, 0x119A) == 2
        missed += variant in [0, 1, 2]
    print('    damage: killed=%d other hits=%d miss cases=%d'%(killed, survived, missed))
    if not all([killed, survived, missed]):
        return ['missing damage coverage']
    for i in range(48):
        m.ds_write(0, saved)
        m.wb(seg, 0, bytes(0x9000))
        m.ds_write(0x01DE, bytes([0]))
        m.ds_write(0x7A18, bytes([0]))
        word(0x03A0, 0x508)
        m.ds_write(0x508, struct.pack('<5H', 0, 100, 0, 0, 0))
        word(0x118E, 1)
        m.ds_write(0x575, bytes([127]))
        word(0xB64C, 0xB520)
        word(0xB64E, 1)
        word(0x119A, 0)
        word(0x11A2, 159)
        word(0x11A4, 60)
        word(0x118A, 0)
        word(0x118C, 0)
        m.ds_write(0x9000, backing)
        word(0x9006, 0)
        word(0x900A, 0)
        m.ds_write(0xAAF2, backing)
        word(0xAAFC, 30)
        ident = m.rw(m.DATA_SEG, 0x9008)
        word(0x9A64, ident if i%2 else ident^65535)
        word(0x0B0E, 23)
        word(0x50AC, 0)
        m.ds_write(0xB18E, struct.pack('<9H', 0x9000, 0, 100, 8, 311, 8, 110, 0, 0))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.weapon_scan_damage(ctypes.byref(g))
        m.call(0, 0xA07B, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['explosive damage events/status %d'%i]
        compare('explosive/timed damage %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    m.ds_write(0, saved)
    m.ds_write(0x01DE, bytes([1]))
    g, mem, planes = make_game(m)
    before = mem.raw
    screen = planes.raw
    if ctx.lib.weapon_scan_damage(ctypes.byref(g)) != -1 or mem.raw != before or planes.raw != screen:
        return ['serial rejection must be atomic']
    CASES += 1
    m.wb(seg, 0, collision)
    return fails
