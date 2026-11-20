"""font8_load, def_slot_of and the start-up loaders (src/session.c) against the original
0000:168E (with 11BC:2A5E), 11BC:11ED, 0000:CA1A and 0000:E475.

168E from the in-game snapshot (the 8x8 font read again into far DS:155A; its segment into
the code words 0000:16A7 and 11BC:2A63), CA1A and E475 (their files read again), 1AC9 (hud1..5.img unpacked again from the area's start). 11ED with random loaded-DEF lists (none, some, the
number missing or present, repeated) and records. Compared: all memory but the stack.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.font8_load.restype = ctypes.c_int
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.wb(dosemu.LOAD_SEG, 0x16A7, b'\0\0')
    m.wb(dosemu.LOAD_SEG + 0x11BC, 0x2A63, b'\0\0')
    g, mem, planes = make_game(m)
    files = Files(m, record=False)
    status = lib.font8_load(ctypes.byref(g), ctypes.byref(files.host))
    m.call(0, 0x168E)
    CASES += 1
    if status:
        return [f'168E: status {status}']
    compare('168E', mem, planes, m, regions(m), fails)
    if fails:
        return fails
    for name, address in (('session_load_swapped', 0xCA1A), ('session_load_records', 0xE475),
                          ('session_load_pictures', 0x1AC9)):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        if address == 0x1AC9:                          # as at start-up: hud1.img, the area from its start
            m.ds_write(0x1553, b'1')
            m.ds_write(0x120C, b'\0\0')
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        getattr(lib, name).restype = ctypes.c_int
        status = getattr(lib, name)(ctypes.byref(g), ctypes.byref(files.host))
        m.call(0, address, max_instr=1_000_000_000)
        CASES += 1
        if status:
            return [f'{address:04X}: status {status}']
        compare(f'{address:04X}', mem, planes, m, regions(m), fails)
        if fails:
            return fails
    rng = random.Random(0x11ED)
    for i in range(20):                                    # F879: the seed from the BIOS ticks
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.uc.mem_write(0x46C, struct.pack('<I', rng.randrange(1 << 32)))
        g, mem, planes = make_game(m)
        lib.random_seed_from_clock(ctypes.byref(g))
        m.call(0, 0xF879)
        CASES += 1
        compare(f'F879 case {i}', mem, planes, m, regions(m), fails)
        if fails:
            return fails
    for i in range(200):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        count = 0 if i % 10 == 0 else rng.randrange(1, 60)
        ids = [rng.randrange(256) for _ in range(count)]
        m.ds_write(0x5DC0, bytes(ids))
        m.ds_write(0x72B4, struct.pack('<H', count))
        record = rng.randrange(0x0B00, 0x0D00)
        wanted = rng.choice(ids) if ids and i % 3 else rng.randrange(256)
        m.ds_write(record, bytes(rng.randrange(256) for _ in range(6)) + bytes([wanted]))
        g, mem, planes = make_game(m)
        lib.def_slot_of(ctypes.c_void_p(g.ds), record)
        m.call(0x11BC, 0x11ED, far=True, si=record)
        CASES += 1
        compare(f'11ED case {i}', mem, planes, m, regions(m), fails)
        if fails:
            return fails
    return fails
