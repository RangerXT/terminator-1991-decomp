"""rotate_xz and its three siblings against the originals at 0000:1B7D / 1BB0 / 1B46 / 1BE5."""
import ctypes
import random

CASES = 0


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def run(ctx):
    global CASES
    m = ctx.game()
    ds = ctx.ds_copy()
    lib = ctx.lib
    rnd = random.Random(1991)
    fails = []
    # (C function, original offset, first register, second register)
    variants = [(lib.rotate_xz, 0x1B7D, 'ax', 'cx'), (lib.rotate_xz_inverse, 0x1BB0, 'ax', 'cx'),
                (lib.rotate_bc, 0x1B46, 'bx', 'cx'), (lib.rotate_ab, 0x1BE5, 'ax', 'bx')]
    edge = [0, 1, -1, 16383, 16384, -16384, -16385, 32767, -32768]
    for fn, off, ra, rb in variants:
        for i in range(1500):
            if i < len(edge) ** 2:
                a, b = edge[i % len(edge)], edge[i // len(edge)]
                ang = (i * 37) & 511
            else:
                a, b, ang = rnd.randint(-32768, 32767), rnd.randint(-32768, 32767), rnd.randint(0, 511)
            got = m.call(0x0000, off, **{ra: a, rb: b, 'dx': ang})
            ca, cb = ctypes.c_int16(a), ctypes.c_int16(b)
            fn(ds, ctypes.byref(ca), ctypes.byref(cb), ctypes.c_uint16(ang))
            CASES += 1
            if (s16(got[ra]), s16(got[rb])) != (ca.value, cb.value):
                fails.append(f'{off:04X}({a},{b},{ang}): original {s16(got[ra])},{s16(got[rb])} '
                             f'C {ca.value},{cb.value}')
    return fails
