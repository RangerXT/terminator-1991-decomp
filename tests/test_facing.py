"""face_is_hidden against the original at 11BC:168B (a pure function of four registers)."""
import ctypes
import random

CASES = 0


def run(ctx):
    global CASES
    m = ctx.game()
    fn = ctx.lib.face_is_hidden
    fn.restype = ctypes.c_uint8
    rnd = random.Random(168)
    fails = []
    edge = [0, 1, -1, 2, -2, 255, 256, -256, 319, -320, 32767, -32768, -32767]
    cases = [(a, b, c, d) for a in edge for b in edge for c in (0, 1, -1, 300, -32768) for d in (0, 1, -1, -300, 32767)]
    for _ in range(20000):
        span = rnd.choice((4, 40, 400, 32768))
        cases.append(tuple(rnd.randint(-span, span - 1) for _ in range(4)))
    for a, b, c, d in cases:
        r = m.call(0x11BC, 0x168B, ax=a, bx=b, cx=c, dx=d)
        got = fn(ctypes.c_int16(a), ctypes.c_int16(b), ctypes.c_int16(c), ctypes.c_int16(d))
        CASES += 1
        if got != (r['ax'] & 0xFF):
            fails.append(f'({a},{b},{c},{d}): original {r["ax"] & 0xFF} C {got}')
    return fails
