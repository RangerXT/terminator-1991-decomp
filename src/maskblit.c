/* Monochrome mask blitter shared by HUD zoom and the area-map overlay. */
#include "term.h"

/* orig 0000:1985. The original takes colour/stride from patchable code bytes
 * CS:1B41/1B42; callers pass those values explicitly here. Source rows are padded
 * to an even byte width. Return SI in the low word and DI in the high word. */
uint32_t screen_blit_mask(Game *g, uint16_t source_segment, uint16_t source, uint16_t dest, uint16_t width,
                          uint16_t rows, uint8_t colour, uint16_t stride)
{
    uint8_t *p = g->planes;
    ega_seq_mask(p, 15);
    ega_gc(p, 1, 15);
    ega_gc(p, 0, colour);
    ega_gc_select(p, 8);
    unsigned height = rows ? rows : 65536;
    unsigned count = width ? width : 65536;
    for (unsigned row = 0; row < height; ++row) {
        for (unsigned col = 0; col < count; ++col) {
            uint32_t address = (((uint32_t)source_segment << 4) + source) & 0xFFFFF;
            uint8_t mask = address >= 0xA0000 && address < 0xB0000 ? ega_load(p, (uint16_t)(address - 0xA0000))
                                                                   : *far_ptr(g, source_segment, source);
            ++source;
            ega_gc_data(p, mask);
            uint8_t old = ega_load(p, dest);
            ega_store(p, dest++, old);
        }
        if (width & 1)
            ++source;
        dest += (uint16_t)(stride - width);
    }
    ega_gc_data(p, 255);
    ega_gc(p, 1, 0);
    return source | ((uint32_t)dest << 16);
}
