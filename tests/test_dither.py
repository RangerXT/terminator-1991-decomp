"""build_dither_table against the original at 0000:1F50."""
CASES = 1


def run(ctx):
    m = ctx.game()
    saved = m.ds_read(0x4A6D, 240)
    m.ds_write(0x4A6D, bytes(240))
    m.call(0x0000, 0x1F50)
    want = m.ds_read(0x4A6D, 240)
    m.ds_write(0x4A6D, saved)
    ds = ctx.ds_copy()
    ds[0x4A6D:0x4A6D + 240] = bytes(240)
    ctx.lib.build_dither_table(ds)
    got = bytes(ds[0x4A6D:0x4A6D + 240])
    return [] if got == want else ['table differs']
