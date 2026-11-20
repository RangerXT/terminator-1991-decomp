"""Score arithmetic, masked x86 shifts, bonuses, and variable-length HUD decimal text."""
import ctypes
import random
import struct

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = ctx.game()
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xD6CB)
    ctx.lib.score_update.restype = ctypes.c_uint16
    fields = [0x0386, 0x0384, 0x0388, 0x037E, 0x037C, 0x0380, 0x0378, 0x117E]
    for i in range(1536):
        m.ds_write(0, saved)
        for off in fields:
            value = rng.randrange(65536) if i >= 512 else (1 if off == 0x0386 else 0)
            m.ds_write(off, struct.pack('<H', value))
        if i >= 1280:
            for off in fields:
                m.ds_write(off, b'\0\0')
            m.ds_write(0x0386, struct.pack('<H', 10920 + i % 8))
        m.ds_write(0x03F0, struct.pack('<H', i & 255))
        m.ds_write(0x1157, bytes([255 if i & 256 else 0, 1 if i & 512 else 0]))
        initial = m.ds_read(0, 65536)
        ds = ctypes.create_string_buffer(initial, 65536)
        result = ctx.lib.score_update(ds)
        out = m.call(0, 0xD6CB)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70) or result != out['ax']:
            return [f'score {i}: state/AX differs']
        m.ds_write(0, initial)
        ds = ctypes.create_string_buffer(initial, 65536)
        ctx.lib.hud_format_score(ds)
        m.call(0, 0xE26D)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return [f'score text {i}: DS differs']
    return fails
