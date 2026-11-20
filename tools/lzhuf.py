"""LZHUF decoder (Yoshizaki / Okumura, 1988) as used by The Terminator (1991).

The game's copy (segment 14B5 of the unpacked exe) is the stock algorithm with
N=4096, F=60, THRESHOLD=2; the only change is a 16-bit uncompressed-size prefix
instead of the usual 32-bit one.
"""
N = 4096
F = 60
THRESHOLD = 2
N_CHAR = 256 - THRESHOLD + F
T = N_CHAR * 2 - 1
R = T - 1
MAX_FREQ = 0x8000

D_CODE = bytes([0] * 32 + [1] * 16 + [2] * 16 + [3] * 16 +
               sum(([c] * 8 for c in range(4, 12)), []) +
               sum(([c] * 4 for c in range(12, 24)), []) +
               sum(([c] * 2 for c in range(24, 48)), []) +
               list(range(48, 64)))
D_LEN = bytes([3] * 32 + [4] * 48 + [5] * 64 + [6] * 48 + [7] * 48 + [8] * 16)
assert len(D_CODE) == 256 and len(D_LEN) == 256


def decode(src, pos=0, size=None):
    """Decode one LZHUF stream. If size is None a u16 size prefix is read at pos.

    Returns (data, end_pos) where end_pos is the offset just past the last byte consumed.
    """
    if size is None:
        size = src[pos] | src[pos + 1] << 8
        pos += 2
    freq = [1] * N_CHAR + [0] * (T + 1 - N_CHAR)
    son = [i + T for i in range(N_CHAR)] + [0] * (T - N_CHAR)
    prnt = [0] * (T + N_CHAR)
    for i in range(N_CHAR):
        prnt[i + T] = i
    i, j = 0, N_CHAR
    while j <= R:
        freq[j] = freq[i] + freq[i + 1]
        son[j] = i
        prnt[i] = prnt[i + 1] = j
        i += 2
        j += 1
    freq[T] = 0xffff
    prnt[R] = 0

    n = len(src)
    bitbuf = 0
    bitcnt = 0

    def getbit():
        nonlocal bitbuf, bitcnt, pos
        if bitcnt == 0:
            bitbuf = src[pos] if pos < n else 0
            pos += 1
            bitcnt = 8
        bitcnt -= 1
        return (bitbuf >> bitcnt) & 1

    def getbyte():
        v = 0
        for _ in range(8):
            v = (v << 1) | getbit()
        return v

    def reconst():
        j = 0
        for i in range(T):
            if son[i] >= T:
                freq[j] = (freq[i] + 1) // 2
                son[j] = son[i]
                j += 1
        i = 0
        for j in range(N_CHAR, T):
            k = i + 1
            f = freq[j] = freq[i] + freq[k]
            k = j - 1
            while f < freq[k]:
                k -= 1
            k += 1
            freq[k + 1:j + 1] = freq[k:j]
            freq[k] = f
            son[k + 1:j + 1] = son[k:j]
            son[k] = i
            i += 2
        for i in range(T):
            k = son[i]
            if k >= T:
                prnt[k] = i
            else:
                prnt[k] = prnt[k + 1] = i

    def update(c):
        if freq[R] == MAX_FREQ:
            reconst()
        c = prnt[c + T]
        while True:
            freq[c] += 1
            k = freq[c]
            l = c + 1
            if k > freq[l]:
                while k > freq[l + 1]:
                    l += 1
                freq[c] = freq[l]
                freq[l] = k
                i = son[c]
                prnt[i] = l
                if i < T:
                    prnt[i + 1] = l
                j = son[l]
                son[l] = i
                prnt[j] = c
                if j < T:
                    prnt[j + 1] = c
                son[c] = j
                c = l
            c = prnt[c]
            if c == 0:
                break

    text = bytearray(b' ' * N)
    r = N - F
    out = bytearray()
    while len(out) < size:
        c = son[R]
        while c < T:
            c = son[c + getbit()]
        c -= T
        update(c)
        if c < 256:
            out.append(c)
            text[r] = c
            r = (r + 1) & (N - 1)
        else:
            i = getbyte()
            hi = D_CODE[i] << 6
            for _ in range(D_LEN[i] - 2):
                i = (i << 1) | getbit()
            p = (r - (hi | (i & 0x3f)) - 1) & (N - 1)
            for k in range(c - 255 + THRESHOLD):
                b = text[(p + k) & (N - 1)]
                out.append(b)
                text[r] = b
                r = (r + 1) & (N - 1)
    return bytes(out[:size]), pos
