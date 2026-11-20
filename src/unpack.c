/* The two decompressors used by the game's data files. */
#include "term.h"

/* Direct buffers retain the established public codec API. A Game-backed stream
 * performs 16-bit offset wrapping and interleaves all reads/writes, including aliases. */
typedef struct {
    const uint8_t *src;
    uint8_t *dst;
    Game *game;
    uint16_t src_seg, src_off, dst_seg, dst_off, packed_len;
} CodecIO;

static uint8_t codec_memory_read(Game *g, uint16_t seg, uint16_t off)
{
    uint32_t address = (((uint32_t)seg << 4) + off) & 0xFFFFF;
    return address >= 0xA0000 && address < 0xB0000 ? ega_load(g->planes, (uint16_t)(address - 0xA0000))
                                                   : *far_ptr(g, seg, off);
}

static uint8_t codec_source(const CodecIO *io, long off)
{
    return io->game ? codec_memory_read(io->game, io->src_seg, (uint16_t)(io->src_off + off)) : io->src[off];
}

static uint8_t codec_output(const CodecIO *io, long off)
{
    if (io->game && io->dst)
        return io->dst[(uint16_t)(io->dst_off + off)];
    return io->game ? codec_memory_read(io->game, io->dst_seg, (uint16_t)(io->dst_off + off)) : io->dst[off];
}

static void codec_write(const CodecIO *io, long off, uint8_t value)
{
    if (!io->game) {
        io->dst[off] = value;
        return;
    }
    if (io->dst) {
        io->dst[(uint16_t)(io->dst_off + off)] = value;
        return;
    }
    uint16_t dest = (uint16_t)(io->dst_off + off);
    uint32_t address = (((uint32_t)io->dst_seg << 4) + dest) & 0xFFFFF;
    if (address >= 0xA0000 && address < 0xB0000)
        ega_store(io->game->planes, (uint16_t)(address - 0xA0000), value);
    else
        *far_ptr(io->game, io->dst_seg, dest) = value;
}

/* ---------------------------------------------------------------- ByteKiller
 * orig 0000:B425  cdecl (src_off, src_seg, dst_off, dst_seg, packed_len), returns 0 if the
 * checksum matches, 0xFFFF otherwise.
 *
 * The packed block is read backwards from its end and the output is written backwards.
 * Trailer (last 6 bytes): u16be first_bits, u16le checksum, u16le unpacked_size.
 * Returns 0 when the XOR of every word read equals the checksum, -1 otherwise.
 */
typedef struct {
    const CodecIO *io;
    long pos;      /* offset of the next word to read, moving down */
    uint16_t bits; /* bit buffer with a sentinel bit on top */
    uint16_t check;
} BkState;

static uint16_t bk_word(BkState *s)
{
    s->pos -= 2;
    uint16_t w = (uint16_t)(codec_source(s->io, s->pos) << 8 | codec_source(s->io, s->pos + 1));
    s->check ^= w;
    return w;
}

static unsigned bk_bit(BkState *s)
{
    unsigned c = s->bits & 1;
    s->bits >>= 1;
    if (s->bits == 0) { /* that was the sentinel: refill */
        uint16_t w = bk_word(s);
        c = w & 1;
        s->bits = (uint16_t)((w >> 1) | 0x8000);
    }
    return c;
}

static unsigned bk_bits(BkState *s, int n)
{
    unsigned v = 0;
    while (n--)
        v = (v << 1) | bk_bit(s);
    return v;
}

static int bk_decode(const CodecIO *io, uint16_t packed_len)
{
    BkState s;
    s.io = io;
    s.pos = packed_len;
    s.pos -= 2;
    long di = (long)(codec_source(io, s.pos) | codec_source(io, s.pos + 1) << 8); /* unpacked size */
    s.pos -= 2;
    s.check = (uint16_t)(codec_source(io, s.pos) | codec_source(io, s.pos + 1) << 8);
    s.bits = bk_word(&s);

    int more = io->game ? 1 : di > 0;
    while (more) {
        unsigned count, offset = 0;
        int literal;
        if (bk_bit(&s) == 0) {
            if (bk_bit(&s) == 0) {
                count = bk_bits(&s, 3) + 1;
                literal = 1;
            } else {
                count = 2;
                offset = bk_bits(&s, 8);
                literal = 0;
            }
        } else {
            unsigned k = bk_bits(&s, 2);
            if (k < 2) {
                count = k + 3;
                offset = bk_bits(&s, 9 + k);
                literal = 0;
            } else if (k == 3) {
                count = bk_bits(&s, 8) + 9;
                literal = 1;
            } else {
                count = bk_bits(&s, 8) + 1;
                offset = bk_bits(&s, 12);
                literal = 0;
            }
        }
        /* The original does not stop inside a run: it finishes the run and only then
         * compares the write position with the start of the buffer. */
        if (literal) {
            while (count--) {
                di--;
                codec_write(io, di, (uint8_t)bk_bits(&s, 8));
            }
        } else {
            while (count--) {
                di--;
                codec_write(io, di, codec_output(io, di + offset));
            }
        }
        more = io->game ? (uint16_t)(io->dst_off + di) > io->dst_off : di > 0;
    }
    return s.check == 0 ? 0 : -1;
}

int bytekiller_unpack(const uint8_t *src, uint16_t packed_len, uint8_t *dst)
{
    CodecIO io = {0};
    io.src = src;
    io.dst = dst;
    return bk_decode(&io, packed_len);
}

/* ---------------------------------------------------------------- LZHUF
 * orig 14B5:0216  in DS:SI = packed data, ES:DI = destination, CX = packed length.
 *
 * Yoshizaki/Okumura LZHUF (1988) with N = 4096, F = 60, THRESHOLD = 2 and a 16-bit
 * unpacked-size prefix. Returns the size from the prefix. The destination needs up to
 * LZ_F - 1 bytes of slack because the last match is not clipped.
 */
#define LZ_N         4096
#define LZ_F         60
#define LZ_THRESHOLD 2
#define LZ_NCHAR     (256 - LZ_THRESHOLD + LZ_F)
#define LZ_T         (LZ_NCHAR * 2 - 1)
#define LZ_R         (LZ_T - 1)
#define LZ_MAX_FREQ  0x8000

typedef struct {
    const CodecIO *io;
    size_t pos;
    unsigned bitbuf, bitcnt;
    uint16_t freq[LZ_T + 1];
    int16_t prnt[LZ_T + LZ_NCHAR];
    int16_t son[LZ_T];
} LzState;

static unsigned lz_bit(LzState *s)
{
    if (s->bitcnt == 0) {
        s->bitbuf = s->io->game && s->pos >= s->io->packed_len ? 0 : codec_source(s->io, (long)s->pos);
        s->pos++;
        s->bitcnt = 8;
    }
    s->bitcnt--;
    return (s->bitbuf >> s->bitcnt) & 1;
}

static unsigned lz_byte(LzState *s)
{
    unsigned v = 0;
    for (int i = 0; i < 8; i++)
        v = (v << 1) | lz_bit(s);
    return v;
}

static void lz_start(LzState *s)
{
    int i, j;
    for (i = 0; i < LZ_NCHAR; i++) {
        s->freq[i] = 1;
        s->son[i] = (int16_t)(i + LZ_T);
        s->prnt[i + LZ_T] = (int16_t)i;
    }
    i = 0;
    j = LZ_NCHAR;
    while (j <= LZ_R) {
        s->freq[j] = (uint16_t)(s->freq[i] + s->freq[i + 1]);
        s->son[j] = (int16_t)i;
        s->prnt[i] = s->prnt[i + 1] = (int16_t)j;
        i += 2;
        j++;
    }
    s->freq[LZ_T] = 0xFFFF;
    s->prnt[LZ_R] = 0;
}

static void lz_reconst(LzState *s)
{
    int i, j, k;
    unsigned f;
    j = 0;
    for (i = 0; i < LZ_T; i++) {
        if (s->son[i] >= LZ_T) {
            s->freq[j] = (uint16_t)((s->freq[i] + 1) / 2);
            s->son[j] = s->son[i];
            j++;
        }
    }
    for (i = 0, j = LZ_NCHAR; j < LZ_T; i += 2, j++) {
        k = i + 1;
        f = s->freq[j] = (uint16_t)(s->freq[i] + s->freq[k]);
        for (k = j - 1; f < s->freq[k]; k--)
            ;
        k++;
        memmove(&s->freq[k + 1], &s->freq[k], (size_t)(j - k) * sizeof(s->freq[0]));
        s->freq[k] = (uint16_t)f;
        memmove(&s->son[k + 1], &s->son[k], (size_t)(j - k) * sizeof(s->son[0]));
        s->son[k] = (int16_t)i;
    }
    for (i = 0; i < LZ_T; i++) {
        k = s->son[i];
        if (k >= LZ_T)
            s->prnt[k] = (int16_t)i;
        else
            s->prnt[k] = s->prnt[k + 1] = (int16_t)i;
    }
}

static void lz_update(LzState *s, int c)
{
    int i, j, l;
    unsigned k;
    if (s->freq[LZ_R] == LZ_MAX_FREQ)
        lz_reconst(s);
    c = s->prnt[c + LZ_T];
    do {
        k = ++s->freq[c];
        l = c + 1;
        if (k > s->freq[l]) {
            while (k > s->freq[l + 1])
                l++;
            s->freq[c] = s->freq[l];
            s->freq[l] = (uint16_t)k;
            i = s->son[c];
            s->prnt[i] = (int16_t)l;
            if (i < LZ_T)
                s->prnt[i + 1] = (int16_t)l;
            j = s->son[l];
            s->son[l] = (int16_t)i;
            s->prnt[j] = (int16_t)c;
            if (j < LZ_T)
                s->prnt[j + 1] = (int16_t)c;
            s->son[c] = (int16_t)j;
            c = l;
        }
    } while ((c = s->prnt[c]) != 0);
}

static const uint8_t lz_d_len_runs[6][2] = {{3, 32}, {4, 48}, {5, 64}, {6, 48}, {7, 48}, {8, 16}};

static uint16_t lz_decode(const CodecIO *io, uint32_t *written)
{
    static uint8_t d_code[256], d_len[256];
    static int tables_ready;
    if (!tables_ready) {
        int n = 0, code = 0;
        for (int r = 0; r < 6; r++) {
            int len = lz_d_len_runs[r][0];
            int span = 1 << (8 - len); /* how many byte values share one code */
            for (int i = 0; i < lz_d_len_runs[r][1]; i += span, code++) {
                for (int k = 0; k < span; k++, n++) {
                    d_code[n] = (uint8_t)code;
                    d_len[n] = (uint8_t)len;
                }
            }
        }
        tables_ready = 1;
    }

    LzState s;
    uint8_t text[LZ_N];
    uint16_t size = (uint16_t)(codec_source(io, 0) | codec_source(io, 1) << 8);
    unsigned r = LZ_N - LZ_F, count = 0;
    s.io = io;
    s.pos = 2;
    s.bitbuf = s.bitcnt = 0;
    lz_start(&s);
    memset(text, ' ', sizeof text);
    /* The last 60 ring bytes were not initialized by the original. Preserve them
     * for segmented calls, where the old scratch segment is part of the input. */
    uint16_t workspace = 0;
    if (io->game) {
        workspace = (uint16_t)(io->game->ds_seg - 0x5C27 + 0x5819);
        for (unsigned k = LZ_N - LZ_F; k < LZ_N; ++k)
            text[k] = *far_ptr(io->game, workspace, (uint16_t)(0x113A + k));
    }
    int first = io->game != NULL;
    while (first || (io->game ? (uint16_t)count : count) < size) {
        first = 0;
        int c = s.son[LZ_R];
        while (c < LZ_T)
            c = s.son[c + (int)lz_bit(&s)];
        c -= LZ_T;
        lz_update(&s, c);
        if (c < 256) {
            codec_write(io, count++, (uint8_t)c);
            text[r] = (uint8_t)c;
            r = (r + 1) & (LZ_N - 1);
        } else {
            unsigned i = lz_byte(&s);
            unsigned hi = (unsigned)d_code[i] << 6;
            for (int j = d_len[i] - 2; j > 0; j--)
                i = (i << 1) | lz_bit(&s);
            unsigned p = (r - (hi | (i & 0x3F)) - 1) & (LZ_N - 1);
            unsigned len = (unsigned)c - 255 + LZ_THRESHOLD;
            /* like the original, a match is copied whole even if it runs past `size` */
            for (unsigned k = 0; k < len; k++) {
                uint8_t b = text[(p + k) & (LZ_N - 1)];
                codec_write(io, count++, b);
                text[r] = b;
                r = (r + 1) & (LZ_N - 1);
            }
        }
    }
    if (io->game)
        for (unsigned k = 0; k < LZ_N; ++k)
            *far_ptr(io->game, workspace, (uint16_t)(0x113A + k)) = text[k];
    if (written)
        *written = count;
    return size;
}

uint16_t lzhuf_unpack(const uint8_t *src, uint8_t *dst)
{
    CodecIO io = {0};
    io.src = src;
    io.dst = dst;
    return lz_decode(&io, NULL);
}

/* orig 0000:19CC. Valid compressed image header required (1..16 mask bits,
 * at least one stored plane). Other header fields are read as the executable does.
 * LZHUF's private adaptive tables/bit-reader scratch stay local, rather than being
 * mirrored into the old segment; the ring is retained because its uninitialized
 * tail is an observable input to a later stream. Returns 0, or -1 for an unsupported
 * header. AX is returned through ax_out; checksum failures are ignored as in 19CC. */
int image_unpack_compressed(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest_seg, uint16_t dest,
                            uint16_t *ax_out)
{
    uint8_t *ds = g->ds;
    CodecIO io = {0};
    io.game = g;
    io.src_seg = source_seg;
    io.dst_seg = dest_seg;
    DS_U16(ds, 0x1220) = source;
    DS_U16(ds, 0x1222) = source_seg;
    uint16_t mask = DS_U16(far_ptr(g, source_seg, source), 0);
    uint16_t bits = DS_U16(far_ptr(g, source_seg, (uint16_t)(source + 2)), 0);
    uint16_t type = DS_U16(far_ptr(g, source_seg, (uint16_t)(source + 12)), 0);
    uint16_t plane_bytes = DS_U16(far_ptr(g, source_seg, (uint16_t)(source + 14)), 0);
    if (!bits || bits > 16)
        return -1;
    unsigned count = 0;
    for (unsigned i = 0; i < bits; ++i)
        count += (mask >> i) & 1;
    if (!count)
        return -1;
    uint16_t lengths = source + 16, data = source + 32, current = dest;
    uint32_t written = 0;
    for (unsigned i = 0; i < count; ++i) {
        io.src_off = data;
        io.dst_off = current;
        io.packed_len = DS_U16(far_ptr(g, source_seg, (uint16_t)(lengths + 2 * i)), 0);
        if (type & 4)
            bk_decode(&io, io.packed_len);
        else
            lz_decode(&io, &written);
        data += io.packed_len;
        current += plane_bytes;
    }
    if (ax_out)
        *ax_out = type & 4 ? (uint16_t)(current - dest) : (uint16_t)written;
    return 0;
}

/* Segmented block entry for the cached/file image services. Type bit 4 chooses
 * ByteKiller; otherwise LZHUF. Native callers retain the original checksum policy. */
int unpack_block(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest_seg, uint16_t dest, uint16_t packed_len,
                 uint16_t type)
{
    CodecIO io = {0};
    io.game = g;
    io.src_seg = source_seg;
    io.src_off = source;
    io.dst_seg = dest_seg;
    io.dst_off = dest;
    io.packed_len = packed_len;
    if (type & 4)
        return bk_decode(&io, packed_len);
    lz_decode(&io, NULL);
    return 0;
}

/* Segmented source and observable LZHUF ring, with an external 64 KB linear
 * framebuffer destination. VGA callers keep hardware pixels outside Game. */
int unpack_block_linear(Game *g, uint16_t source_seg, uint16_t source, uint8_t *dest, uint16_t offset,
                        uint16_t packed_len, uint16_t type)
{
    CodecIO io = {0};
    io.game = g;
    io.src_seg = source_seg;
    io.src_off = source;
    io.dst = dest;
    io.dst_off = offset;
    io.packed_len = packed_len;
    if (type & 4)
        return bk_decode(&io, packed_len);
    lz_decode(&io, NULL);
    return 0;
}
