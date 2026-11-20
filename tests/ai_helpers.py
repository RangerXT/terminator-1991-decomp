"""Prepared opponent/companion encounter state shared by native differential suites."""
import struct


def prepare(m, saved, rng, collision, barriers, i, vehicle=False):
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    collisionseg = m.rw(m.DATA_SEG, 0x91B2)
    m.ds_write(0, saved)
    player = [0x0508, 0x04D4][i%2]
    actor = [0x04D4, 0x0508][i%2]
    word(0x03A0, player)
    word(0x04BA, actor)
    m.ds_write(player+14, b'\1')
    word(player+26, 0)
    word(player+28, 1000)
    word(actor+28, 200)
    word(actor+26, [0, 100, 199][i%3])
    col = m.rw(m.DATA_SEG, player+30)
    row = m.rw(m.DATA_SEG, player+32)
    shift = [0, 2, 3][(i//2)%3]
    word(actor+30, col+shift)
    word(actor+32, row)
    word(actor, rng.randrange(1024))
    word(actor+4, rng.randrange(1024))
    word(actor+6, (i*37)%512)
    wx = (col+shift)*1024+m.rw(m.DATA_SEG, actor)
    wz = row*1024+1024-m.rw(m.DATA_SEG, actor+4)
    word(actor+34, wx)
    word(actor+36, wx>>16)
    word(actor+42, wz)
    word(actor+44, wz>>16)
    for at in [0x053C, 0x0540]:
        word(at, rng.randrange(1024))
    word(0x0556, i%4)
    word(0x0558, [7, 8, 200][i%3])
    word(0x04D2, 0 if i%5 == 0 else 80)
    word(0x11C0, 200)
    word(0x1174, i%1000)
    word(0x03F0, i%4)
    m.ds_write(0xDE3D, bytes([i%7 == 0]))
    m.ds_write(0x1154, bytes([i%7 == 0]))
    m.ds_write(0x1152, bytes([i%11 == 0]))
    m.ds_write(0xAA83, bytes([i%13 == 0]))
    m.ds_write(0xAA98, b'\0')
    for at, v in [(0x0356, [0, 1, 2][i%3]), (0x0357, [1, 2][i%2]), (0x0358, 1), (0x0359, i%3 != 0), (0x0355, 1 if i%4 == 0 else 80), (0x035F, 3)]:
        m.ds_write(at, bytes([v]))
    word(0xDE46, i%4)
    m.ds_write(0x0351, bytes([1, 2, 3, 4]))
    word(0xDECA, 65535)
    word(0xDE52, 100)
    word(0xDE54, 200)
    word(0xB64C, 0xB520)
    m.ds_write(0xE3E0, b'\0')
    m.ds_write(0xB735, b'\0')
    word(0x1208, 0x100)
    word(0x120A, 0x8000)
    ids = [x for pair in struct.unpack_from('<4H', saved, 0xDE3E) for x in [pair&255, pair>>8]]
    for j, item in enumerate(ids):
        m.wb(0x8000, 0x100+j*6, struct.pack('<H4B', 0, item, 0, 2, 0 if i%17 == 0 else 2))
    m.wb(0x8000, 0x130, bytes(12))
    word(0x9948, 0x97B8)
    word(0x994A, 0x9948)
    for j in range(80):
        word(0x97B8+j*2, [0, 0xFE4C, 0xFF46, 0xFFDC, 65535, rng.randrange(65536)][(i+j)%6])
    m.wb(collisionseg, 0, [collision, bytes(0x9000), barriers, bytes([1])*0x9000][i%4])
    m.ds_write(0xB740, [bytes(144), bytes([1])*144, bytes(j%3 == 0 for j in range(144))][i%3])
    for plane in m.vga.planes:
        plane[0x6000:0x8000] = bytes(8192)
    if vehicle:
        m.ds_write(player+14, bytes([2]))
        word(player+48, 1000)
