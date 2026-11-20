/* WHEELS.CIF vehicle display and its shared compressed-plane helpers. */
#include "term.h"

static uint8_t read_at(Game *g, uint32_t at)
{
    at &= 0xFFFFF;
    return at >= 0xA0000 && at < 0xB0000 ? ega_load(g->planes, (uint16_t)at) : g->mem[at];
}

static uint16_t word_at(Game *g, uint16_t seg, uint16_t off)
{
    uint32_t at = (((uint32_t)seg << 4) + off) & 0xFFFFF;
    return (uint16_t)(read_at(g, at) | (read_at(g, at + 1) << 8));
}

/* orig 72E5 (ByteKiller, DS:8544 planes) / 731D (LZHUF, four planes).
 * Both use DS:850E/8510 far segments. Return SI | DI<<16 | BX<<32 | AX<<48.
 * Unsupported ByteKiller counts outside 1..8 return UINT64_MAX. */
uint64_t image_unpack_shared(Game *g, uint16_t source, uint16_t dest, uint8_t lzhuf)
{
    uint8_t *ds = g->ds;
    uint16_t source_seg = DS_U16(ds, DS_UNPACK_SRC_SEG);
    uint16_t step = word_at(g, source_seg, (uint16_t)(source + 14));
    uint16_t data = (uint16_t)(source + 32);
    source += 16;
    uint16_t count = lzhuf ? 4 : DS_U16(ds, 0x8544);
    if (!count || count > 8)
        return UINT64_MAX;
    uint16_t packed = 0;
    for (unsigned i = 0; i < count; ++i) {
        packed = word_at(g, source_seg, source);
        source += 2;
        /* 731D switches DS to the source before reading [8510]. Retain that
         * source-segment lookup, rather than the apparent main-DS destination. */
        uint16_t dest_seg = lzhuf ? word_at(g, source_seg, 0x8510) : DS_U16(ds, DS_UNPACK_DST_SEG);
        unpack_block(g, source_seg, data, dest_seg, dest, packed, lzhuf ? 0 : 4);
        data += packed;
        dest += step;
    }
    return source | ((uint64_t)dest << 16) | ((uint64_t)data << 32) | ((uint64_t)packed << 48);
}

/* orig 5776:00A6. The source really loops over masks 1,2,4,8,16: the fifth pass
 * consumes source words while selecting no visible plane. Return SI | DI<<16. */
uint32_t screen_blit_five_planes(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest, uint16_t words,
                                 uint16_t rows, uint16_t stride)
{
    uint8_t *p = g->planes;
    ega_gc(p, 3, 0);
    ega_gc(p, 5, 0);
    ega_gc(p, 8, 255);
    ega_gc(p, 1, 0);
    for (unsigned plane = 0; plane < 5; ++plane) {
        ega_seq_mask(p, (uint8_t)(1u << plane));
        uint16_t out = dest;
        unsigned height = rows ? rows : 65536;
        for (unsigned row = 0; row < height; ++row) {
            uint16_t at = out;
            for (unsigned col = 0; col < words; ++col) {
                uint32_t from = (((uint32_t)source_seg << 4) + source) & 0xFFFFF;
                uint8_t lo = read_at(g, from), hi = read_at(g, from + 1);
                ega_store(p, at, lo);
                ega_store(p, (uint16_t)(at + 1), hi);
                at += 2;
                source += 2;
            }
            out += stride;
        }
    }
    ega_seq_mask(p, 15);
    return source | ((uint32_t)dest << 16);
}

/* orig 70AA. Five offsets are indexed from segment offset zero, as in the source. */
int vehicle_hud_load(Game *g, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_WORK_BUFFER_SEG), offset = DS_U16(ds, DS_WORK_BUFFER);
    uint32_t result = file_load(g, io, 0x8140, seg, offset);
    if (result == UINT32_MAX)
        return -1;
    uint16_t source = 0;
    for (unsigned i = 0; i < 5; ++i) {
        DS_U16(ds, 0x848C + 2 * i) = source;
        uint16_t size = word_at(g, seg, (uint16_t)(source + 16));
        size += word_at(g, seg, (uint16_t)(source + 18));
        size += word_at(g, seg, (uint16_t)(source + 20));
        size += word_at(g, seg, (uint16_t)(source + 22));
        source += (uint16_t)(size + 32);
    }
    return 0;
}

/* orig 7250. Repaint only when the selected vehicle frame changes, on all three pages. */
int vehicle_hud_draw(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 2) || DS_U8(ds, DS_CAMERA_MODE))
        return 0;
    uint16_t frame = DS_U16(ds, 0x11A6);
    if (frame == DS_U16(ds, 0x1182))
        return 0;
    DS_U16(ds, 0x1182) = frame;
    DS_U16(ds, DS_UNPACK_SRC_SEG) = DS_U16(ds, DS_WORK_BUFFER_SEG);
    uint16_t source = DS_U16(ds, 0x848C + frame);
    DS_U16(ds, DS_UNPACK_DST_SEG) = DS_U16(ds, 0xE16E);
    if (image_unpack_shared(g, source, 0, 0) == UINT64_MAX)
        return -1;
    DS_U16(ds, DS_UNPACK_DST_SEG) = g->ds_seg;
    DS_U16(ds, DS_UNPACK_SRC_SEG) = g->ds_seg;
    for (unsigned page = 0; page < 3; ++page)
        screen_blit_five_planes(g, DS_U16(ds, 0xE16E), 0, (uint16_t)(0x11FC + page * 0x2000), 6, 64, 40);
    return 0;
}

/* 5776:00E5: byte-width sibling, five source passes and padding of odd rows. */
uint32_t screen_blit_five_plane_bytes(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest, uint16_t width,
                                      uint16_t rows, uint16_t stride)
{
    uint8_t *p = g->planes;
    ega_gc(p, 3, 0);
    ega_gc(p, 5, 0);
    ega_gc(p, 8, 255);
    ega_gc(p, 1, 0);
    for (unsigned plane = 0; plane < 5; ++plane) {
        ega_seq_mask(p, 1u << plane);
        uint16_t out = dest;
        unsigned height = rows ? rows : 65536;
        for (unsigned row = 0; row < height; ++row) {
            for (uint32_t col = 0; col < width; ++col) {
                uint32_t at = (((uint32_t)source_seg << 4) + source) & 0xFFFFF;
                ega_store(p, (uint16_t)(out + col), read_at(g, at));
                source++;
            }
            if (width & 1)
                source++;
            out += stride;
        }
    }
    ega_seq_mask(p, 15);
    return source | ((uint32_t)dest << 16);
}
