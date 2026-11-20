"""ByteKiller-style decoder used by The Terminator (1991) for image type flag 0x04.

Transcribed from the routine at 0000:B425 in the unpacked exe. It is the Amiga
"ByteKiller" scheme with 16-bit words: the stream is read backwards from the end
and the output is written backwards from the end.

  trailer (last 6 bytes, in file order):  u16be first_bits, u16le checksum, u16le unpacked_size
  every further word is read big-endian, walking towards the start of the data;
  the XOR of all words (including first_bits) with the checksum must be 0.
"""


def decode(src, start=0, length=None):
    """Decode the packed block src[start:start+length]. Returns (data, checksum_ok)."""
    if length is None:
        length = len(src) - start
    si = start + length
    si -= 2
    size = src[si] | src[si + 1] << 8
    si -= 2
    chk = src[si] | src[si + 1] << 8
    si -= 2
    ax = src[si] << 8 | src[si + 1]
    chk ^= ax
    out = bytearray(size)
    di = size

    def bit():
        nonlocal ax, si, chk
        c = ax & 1
        ax >>= 1
        if ax == 0:  # that was the sentinel; fetch the next word
            si -= 2
            w = src[si] << 8 | src[si + 1]
            chk ^= w
            c = w & 1
            ax = (w >> 1) | 0x8000
        return c

    def bits(n):
        v = 0
        for _ in range(n):
            v = (v << 1) | bit()
        return v

    while di > 0:
        if bit() == 0:
            if bit() == 0:
                count, lit = bits(3) + 1, True
            else:
                count, off, lit = 2, bits(8), False
        else:
            k = bits(2)
            if k < 2:
                count, off, lit = k + 3, bits(9 + k), False
            elif k == 3:
                count, lit = bits(8) + 9, True
            else:
                count = bits(8) + 1
                off, lit = bits(12), False
        if lit:
            for _ in range(count):
                di -= 1
                if di < 0:
                    break
                out[di] = bits(8)
        else:
            for _ in range(count):
                di -= 1
                if di < 0:
                    break
                out[di] = out[di + off]
    return bytes(out), chk == 0
