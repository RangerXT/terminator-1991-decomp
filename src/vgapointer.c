/* Missing indexed VGA cursor branch of 1492/1517/153A and 6128/830F. */
#include "term.h"

static uint8_t *linear_pixel(Game *g, uint8_t *screen, uint32_t address)
{
    address &= 0xFFFFF;
    return address >= 0xA0000 && address < 0xB0000 ? screen + (address - 0xA0000) : g->mem + address;
}
static uint8_t *pixel(Game *g, uint8_t *screen, uint16_t seg, uint16_t off)
{
    return linear_pixel(g, screen, ((uint32_t)seg << 4) + off);
}

/* REP MOVSW wraps SI/DI after each word, not between its two bytes. In
 * particular a word at offset FFFF accesses the next physical paragraph page. */
static void copy_word(Game *g, uint8_t *screen, uint16_t srcseg, uint16_t source, uint16_t dstseg, uint16_t dest)
{
    uint32_t from = ((uint32_t)srcseg << 4) + source, to = ((uint32_t)dstseg << 4) + dest;
    uint8_t lo = *linear_pixel(g, screen, from), hi = *linear_pixel(g, screen, from + 1);
    *linear_pixel(g, screen, to) = lo;
    *linear_pixel(g, screen, to + 1) = hi;
}

/* 1517 saves/restores sixteen rows even when the next mask uses another height.
 * The source's zero-position sentinel deliberately does not restore a cursor at 0. */
void screen_restore_mask16_vga(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    uint16_t dest = DS_U16(ds, 0x1210), source = DS_U16(ds, 0x1212), seg = DS_U16(ds, 0x1214),
             video = DS_U16(ds, DS_SEG_SCREEN);
    for (unsigned row = 0; row < 16; ++row) {
        for (unsigned i = 0; i < 8; ++i) {
            copy_word(g, screen, seg, source, video, dest);
            source += 2;
            dest += 2;
        }
        dest += 304;
    }
}

/* Return source AX=FF00, not the cursor's byte offset (kept separately in 1210). */
uint16_t screen_draw_mask16_vga(Game *g, uint8_t *screen, uint16_t x, uint16_t y, uint16_t rows, uint16_t mask)
{
    uint8_t *ds = g->ds;
    uint16_t video = DS_U16(ds, DS_SEG_SCREEN);
    if (DS_U16(ds, 0x1210))
        screen_restore_mask16_vga(g, screen);
    uint16_t dest = y * 320 + x, source = dest, buffer = DS_U16(ds, 0x1212), seg = DS_U16(ds, 0x1214);
    DS_U16(ds, 0x1210) = dest;
    for (unsigned row = 0; row < 16; ++row) {
        for (unsigned i = 0; i < 8; ++i) {
            copy_word(g, screen, video, source, seg, buffer);
            source += 2;
            buffer += 2;
        }
        source += 304;
    }
    unsigned count = rows ? rows : 65536;
    for (unsigned row = 0; row < count; ++row) {
        for (unsigned i = 0; i < 2; ++i) {
            uint8_t bits = DS_U8(ds, mask++);
            for (unsigned bit = 0; bit < 8; ++bit) {
                if (bits & 128)
                    *pixel(g, screen, video, dest) = 255;
                bits <<= 1;
                ++dest;
            }
        }
        dest += 304;
    }
    return 0xFF00;
}

int map_draw_pointer_display(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_FACILITY_SCREEN))
        return map_draw_pointer(g);
    if (!screen)
        return -1;
    DS_U16(ds, 0x7C94) = screen_draw_mask16_vga(g, screen, DS_U16(ds, DS_POINTER_X), DS_U16(ds, DS_POINTER_Y),
                                                DS_U16(ds, 0x7BF6), 0x7C00);
    return 0;
}

int map_pointer_step_display(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_FACILITY_SCREEN))
        return map_pointer_step(g);
    uint16_t step = DS_U8(ds, KEY_DOWN(SC_RSHIFT)) ? 4 : 1, x = DS_U16(ds, DS_POINTER_X), y = DS_U16(ds, DS_POINTER_Y);
    if (DS_U8(ds, KEY_DOWN(SC_RIGHT))) {
        x += step;
        if (x >= DS_U16(ds, 0x724C))
            x = DS_U16(ds, 0x724C);
    }
    if (DS_U8(ds, KEY_DOWN(SC_LEFT))) {
        x -= step;
        if ((int16_t)x < 0)
            x = 0;
    }
    if (DS_U8(ds, KEY_DOWN(SC_DOWN))) {
        y += step;
        if (y >= DS_U16(ds, 0x9A5A))
            y = DS_U16(ds, 0x9A5A);
    }
    if (DS_U8(ds, KEY_DOWN(SC_UP))) {
        y -= step;
        if ((int16_t)y < 0)
            y = 0;
    }
    DS_U16(ds, DS_POINTER_X) = x;
    DS_U16(ds, DS_POINTER_Y) = y;
    return map_draw_pointer_display(g, screen);
}
