/* Raw planar image drawing and the five system-HUD background pieces. */
#include "term.h"

static uint32_t address(uint16_t seg, uint16_t off)
{
    return (((uint32_t)seg << 4) + off) & 0xFFFFF;
}

static uint8_t read_byte(Game *g, uint32_t at)
{
    at &= 0xFFFFF;
    return at >= 0xA0000 && at < 0xB0000 ? ega_load(g->planes, (uint16_t)at) : g->mem[at];
}

static void write_byte(Game *g, uint32_t at, uint8_t value)
{
    at &= 0xFFFFF;
    if (at >= 0xA0000 && at < 0xB0000)
        ega_store(g->planes, (uint16_t)at, value);
    else
        g->mem[at] = value;
}

static uint16_t header_word(Game *g, uint16_t seg, uint16_t off)
{
    uint32_t at = address(seg, off);
    return (uint16_t)(read_byte(g, at) | (read_byte(g, at + 1) << 8));
}

/* orig 1A4D. Header is DS:1220/1222, pixels are source_seg:source. Low return
 * word = SI, high = DI. Plane count 1..7 is supported; other counts return -1.
 * The row padding depends on (stride-width)&1, including odd output strides. */
int64_t screen_blit_planar(Game *g, uint16_t source_seg, uint16_t source)
{
    uint8_t *ds = g->ds;
    uint16_t header = DS_U16(ds, 0x1220), seg = DS_U16(ds, 0x1222);
    unsigned count = header_word(g, seg, (uint16_t)(header + 2)) & 31;
    if (count < 1 || count > 7)
        return -1;
    uint8_t stop = (uint8_t)(1u << count);
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    DS_U8(far_ptr(g, code, 0x1B44), 0) = stop;
    uint16_t y = header_word(g, seg, (uint16_t)(header + 10));
    uint16_t x = header_word(g, seg, (uint16_t)(header + 8));
    uint16_t dest = (uint16_t)(DS_U16(ds, 0x1252 + (uint16_t)(2 * y)) + (x >> 3));
    uint16_t width = (uint16_t)(header_word(g, seg, (uint16_t)(header + 4)) + 7) >> 3;
    uint16_t rows = header_word(g, seg, (uint16_t)(header + 6));
    dest += DS_U16(ds, DS_DRAW_PAGE);
    uint16_t skip = (uint16_t)(DS_U16(ds, 0x1228) - width);
    uint16_t dest_seg = DS_U16(ds, DS_SEG_SCREEN);
    for (uint8_t plane = 1; !(plane & stop); plane = (uint8_t)(plane * 2)) {
        ega_seq_mask(g->planes, plane);
        uint16_t out = dest;
        unsigned height = rows ? rows : 65536;
        for (unsigned row = 0; row < height; ++row) {
            for (unsigned col = 0; col < (width >> 1); ++col) {
                /* MOVSW reads both bytes before either is written. Word accesses
                 * are contiguous physically; only the subsequent SI/DI wraps. */
                uint32_t from = address(source_seg, source), to = address(dest_seg, out);
                uint8_t lo = read_byte(g, from), hi = read_byte(g, from + 1);
                write_byte(g, to, lo);
                write_byte(g, to + 1, hi);
                source += 2;
                out += 2;
            }
            if (width & 1) {
                uint8_t value = read_byte(g, address(source_seg, source++));
                write_byte(g, address(dest_seg, out++), value);
            }
            out += skip;
            if (skip & 1)
                ++source;
        }
    }
    ega_seq_mask(g->planes, 15);
    return (uint32_t)source | ((uint32_t)dest << 16);
}

/* orig 1B19. Each piece retains its header pointer in main DS before blitting. */
int hud_restore_background(Game *g)
{
    uint8_t *ds = g->ds;
    for (unsigned i = 0; i < 5; ++i) {
        uint16_t source = DS_U16(ds, 0x1216 + 2 * i), seg = DS_U16(ds, 0x120E);
        DS_U16(ds, 0x1220) = source;
        DS_U16(ds, 0x1222) = seg;
        if (screen_blit_planar(g, seg, (uint16_t)(source + 16)) < 0)
            return -1;
    }
    return 0;
}
