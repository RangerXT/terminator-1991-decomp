"""inventory_transfer (src/inventory.c) against the original 0000:5558.

Random player (DS:05B0) and Sarah (DS:085C) lists of 6-byte records, random items, both
directions (DS:03FE = from, DS:0400 = to), adding to the destination and removing from the
source as the game does (and the remove-only setting of 5546), existing and new items,
counts that run out, items in neither list, and removals started at a record inside the
list (as 58F9 does). Compared: the whole data segment but the call's own stack.
"""
import ctypes
import random
import struct

import dosemu

CASES = 0


def same_outside_stack(got, m):
    want = m.ds_read(0, 0x10000)
    stack = ((m.r(dosemu.UC_X86_REG_SS) << 4) + m.r(dosemu.UC_X86_REG_SP) - (m.DATA_SEG << 4)) & 0xFFFF
    lo, hi = max(stack - 128, 0), min(stack + 8, 0x10000)
    return got[:lo] == want[:lo] and got[hi:] == want[hi:]


def write_list(m, at, records):
    for name, ident, weight, category, count in records:
        m.ds_write(at, struct.pack('<HBBBB', name, ident, weight, category, count))
        at += 6
    m.ds_write(at, bytes(6))
    return at


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.inventory_transfer.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_int]
    m = ctx.game()
    saved = m.ds_read(0, 0x10000)
    rng = random.Random(0x5558)
    fails = []
    seen = set()
    try:
        for i in range(600):
            m.ds_write(0, saved)
            ids = rng.sample(range(1, 60), 12)

            def records(n):
                return [(rng.choice([0x8448, 0x8452, 0x8474]), rng.choice(ids), rng.randrange(8),
                         rng.randrange(1, 8), rng.choice([1, 1, 2, 5, 255])) for _ in range(n)]

            player = records(rng.randrange(0, 9))
            sarah = records(rng.randrange(0, 6))
            end = write_list(m, 0x05B0, player)
            write_list(m, 0x085C, sarah)
            m.ds_write(0x03A2, struct.pack('<H', end))
            # as the game uses it: add to DS:0400's list (copying from DS:03FE's), remove from
            # DS:03FE's; the remove-only entry 5546 clears both and removes from the player's
            take = rng.random() < 0.5
            src, dst = (0x085C, 0x05B0) if take else (0x05B0, 0x085C)
            m.ds_write(0x03FE, struct.pack('<H', src))
            m.ds_write(0x0400, struct.pack('<H', dst))
            remove = rng.random() < 0.5
            if remove and rng.random() < 0.2:
                m.ds_write(0x03FE, bytes(4))
                src = 0x05B0
            source = player if src == 0x05B0 else sarah
            item = rng.choice([r[1] for r in source] + [rng.randrange(1, 60)]) if source else rng.randrange(1, 60)
            target = src if remove else dst
            if remove and rng.random() < 0.3:               # start at a record inside (as 58F9 does)
                target += 6 * rng.randrange(len(source) + 1)
            ds = ctx.ds_copy()
            lib.inventory_transfer(ds, target, item, 1 if remove else 0)
            m.call(0, 0x5558, di=target, ax=item, bp=0xFFFF if remove else 0, es=m.DATA_SEG)
            CASES += 1
            seen.add((remove, take))
            if not same_outside_stack(ds.raw, m):
                first = next(j for j in range(0x10000) if ds.raw[j] != m.ds_read(j, 1)[0])
                fails.append(f'case {i}: {"remove" if remove else "add"} {item:02X} at {target:04X}, '
                             f'first difference DS:{first:04X}')
                break
    finally:
        m.ds_write(0, saved)
    if len(seen) < 4:
        fails.append('not every direction and mode was covered')
    return fails
