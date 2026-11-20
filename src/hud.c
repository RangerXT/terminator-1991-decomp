/* Numeric text shared by the HUD and local map. */
#include "term.h"

/* orig 5776:0154: five-row clear measured in whole bytes. */
void hud_clear_bytes(Game *g, uint16_t dest, uint16_t width)
{
    uint8_t *p = g->planes;
    ega_seq_mask(p, 15);
    ega_gc(p, 0, 0);
    ega_gc(p, 1, 15);
    ega_gc(p, 8, 255);
    dest += DS_U16(g->ds, DS_DRAW_PAGE);
    for (int row = 0; row < 5; ++row)
        for (unsigned i = 0; i < width; ++i)
            ega_store(p, (uint16_t)(dest + row * 40 + i), 8);
    ega_gc(p, 1, 0);
}

/* orig 0000:73C1: normal-view speed field, with a doubled vehicle reading. */
void hud_draw_speed(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint8_t flags = DS_U8(ds, player + 14);
    uint16_t dest = (flags & 2) ? 0x1501 : 0x12DF;
    if (!(flags & 3))
        return;
    hud_clear_bytes(g, dest, 1);
    if ((flags & 2) && !DS_U8(ds, 0x114C))
        return;
    DS_U8(ds, DS_NUMBER_DIGITS) = 2;
    DS_U8(ds, DS_NUMBER_COLOUR) = (flags & 2) ? DS_U8(ds, DS_TEXT_COLOUR) : 15;
    uint16_t value = DS_U16(ds, player + 10);
    if (flags & 2)
        value = (uint16_t)(value * 2);
    hud_draw_number(g, value, dest);
    if (flags & 2)
        DS_U8(ds, DS_NUMBER_COLOUR) = 15;
    DS_U8(ds, DS_NUMBER_DIGITS) = 3;
}

/* orig 0000:7428: the vehicle field at player record +30h. */
void hud_draw_vehicle_counter(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 2))
        return;
    hud_clear_bytes(g, 0x14F3, 1);
    DS_U8(ds, DS_NUMBER_DIGITS) = 2;
    DS_U8(ds, DS_NUMBER_COLOUR) = 15;
    hud_draw_number(g, DS_U16(ds, player + 0x30), 0x14F3);
    DS_U8(ds, DS_NUMBER_COLOUR) = 15;
    DS_U8(ds, DS_NUMBER_DIGITS) = 3;
}

/* orig 11BC:1A01. Erase this page's old compass needle, then draw its new heading. */
uint32_t hud_compass_needle_registers(Game *g, uint16_t history, uint16_t heading, uint8_t colour, uint16_t dx)
{
    uint8_t *ds = g->ds;
    uint16_t at = history + DS_U16(ds, DS_PAGE_DRAWN) * 4;
    if (DS_I16(ds, at) >= 0) {
        uint16_t x = DS_U16(ds, at), y = DS_U16(ds, at + 2);
        DS_U16(ds, at) = DS_U16(ds, at + 2) = 65535;
        DS_U8(ds, DS_FILL_COLOUR) = 0;
        DS_U16(ds, DS_PEN_X) = 212;
        DS_U16(ds, DS_PEN_Y) = 143;
        dx = (uint16_t)(line_to_registers(ds, g->planes, x, y) >> 16);
    }
    if (DS_U8(ds, 0x7AC5))
        return heading | ((uint32_t)dx << 16);
    DS_U8(ds, DS_FILL_COLOUR) = colour;
    uint16_t index = (uint16_t)(heading * 2);
    uint16_t x = (uint16_t)(212 + mul_hi(16, DS_I16(ds, 0x4188 + index)));
    uint16_t y = (uint16_t)(143 + mul_hi(-16, DS_I16(ds, 0x4288 + index)));
    DS_U16(ds, DS_PEN_X) = 212;
    DS_U16(ds, DS_PEN_Y) = 143;
    /* Re-read the page after line_to: it is game state, rather than a local page id. */
    at = history + DS_U16(ds, DS_PAGE_DRAWN) * 4;
    DS_U16(ds, at) = x;
    DS_U16(ds, at + 2) = y;
    return line_to_registers(ds, g->planes, x, y);
}

uint16_t hud_compass_needle_bx(Game *g, uint16_t history, uint16_t heading, uint8_t colour)
{
    return (uint16_t)hud_compass_needle_registers(g, history, heading, colour, 0);
}

void hud_compass_needle(Game *g, uint16_t history, uint16_t heading, uint8_t colour)
{
    (void)hud_compass_needle_bx(g, history, heading, colour);
}

/* orig 0000:4F2A. Walking compass overlay, if enabled. */
void hud_draw_compass(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, player + 14) == 1 && DS_U8(ds, 0xAA96))
        hud_compass_needle(g, 0x7B3C, DS_U16(ds, player + 6), 14);
}

/* orig 5776:018A. Clear a five-row numeric field, measured in half-byte glyphs.
 * The odd trailing half-byte uses XCHG, so its read updates the EGA latches. */
void hud_clear_number(Game *g, uint16_t dest, uint16_t digits)
{
    uint8_t *p = g->planes;
    ega_seq_mask(p, 15);
    ega_gc(p, 0, 0);
    ega_gc(p, 1, 15);
    ega_gc(p, 8, 255);
    dest += DS_U16(g->ds, DS_DRAW_PAGE);
    for (int row = 0; row < 5; ++row)
        for (unsigned i = 0; i < (digits >> 1); ++i)
            ega_store(p, (uint16_t)(dest + row * 40 + i), 8);
    if (digits & 1) {
        ega_gc(p, 8, 0xF0);
        uint8_t value = 8;
        for (int row = 0; row < 5; ++row) {
            uint16_t at = dest + (digits >> 1) + row * 40;
            uint8_t old = ega_load(p, at);
            ega_store(p, at, value);
            value = old;
        }
        ega_gc(p, 8, 255);
    }
    ega_gc(p, 1, 0);
}

/* orig 0000:5998. The doubled heading wraps at 16 bits before unsigned MUL. */
uint16_t heading_degrees(uint16_t heading)
{
    return (uint16_t)(((uint32_t)(uint16_t)(heading * 2) * 0x5A00) >> 16);
}

/* orig 0000:772B. Six numeric fields along the full-height view's lower edge. */
void hud_draw_counters(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_CAMERA_MODE))
        return;
    static const uint16_t dest[] = {0x1E5B, 0x1E60, 0x1E66, 0x1E6C, 0x1E70, 0x1E75};
    static const uint8_t field[] = {10, 6, 30, 32, 0, 4};
    static const uint8_t width[] = {2, 3, 3, 3, 4, 4};
    static const uint8_t colour[] = {4, 14, 11, 11, 3, 3};
    for (int i = 0; i < 6; ++i) {
        /* The original writes only the low byte of the width word. */
        if (i == 1 || i == 4)
            DS_U8(ds, DS_NUMBER_DIGITS) = width[i];
        hud_clear_number(g, dest[i], width[i]);
        if (i == 0)
            DS_U8(ds, DS_NUMBER_DIGITS) = 2;
        uint16_t player = DS_U16(ds, DS_PLAYER);
        uint16_t value = DS_U16(ds, player + field[i]);
        if (i == 1)
            value = heading_degrees(value);
        if (i != 3 && i != 5)
            DS_U8(ds, DS_NUMBER_COLOUR) = colour[i];
        hud_draw_number(g, value, dest[i]);
    }
    DS_U8(ds, DS_NUMBER_COLOUR) = 15;
    DS_U8(ds, DS_NUMBER_DIGITS) = 3;
}

/* orig 0000:C872: fixed-width decimal, discarding higher digits. */
void hud_format_number(uint8_t *ds, uint16_t value)
{
    uint16_t count = DS_U16(ds, DS_NUMBER_DIGITS);
    for (uint16_t i = count; i; --i) {
        DS_U8(ds, 0x7B90 + i - 1) = (uint8_t)('0' + value % 10);
        value /= 10;
    }
}

/* orig 0000:C766. Destination is an EGA byte offset before adding the page. */
uint16_t hud_draw_number_bx(Game *g, uint16_t value, uint16_t dest)
{
    uint8_t *ds = g->ds, *p = g->planes;
    dest += DS_U16(ds, DS_DRAW_PAGE);
    ega_seq_mask(p, 15);
    ega_gc(p, 5, 2);
    ega_gc_select(p, 8);
    hud_format_number(ds, value);
    uint16_t half = DS_U16(ds, 0xE170);
    uint16_t count = DS_U16(ds, DS_NUMBER_DIGITS), bx = 10;
    for (uint16_t i = 0; i < count; ++i) {
        uint8_t ch = (uint8_t)(DS_U8(ds, 0x7B90 + i) - 0x21);
        uint16_t font = 0xE02A + (ch >> 1);
        uint8_t mask = 0xF0;
        if (ch & 1) {
            mask = 0x0F;
            if (!half) {
                font += 0xA0;
                mask = 0xF0;
            }
        } else if (half) {
            font += 0xA0;
            mask = 0x0F;
        }
        bx = (uint16_t)((mask << 8) | 10);
        for (int row = 0; row < 5; ++row) {
            ega_gc_data(p, DS_U8(ds, font + row * 32) & mask);
            uint16_t at = dest + row * 40;
            ega_load(p, at);
            ega_store(p, at, DS_U8(ds, DS_NUMBER_COLOUR));
        }
        half = (uint16_t)~half;
        unsigned carry = half >> 15;
        half = (uint16_t)((half << 1) | carry);
        dest += !carry;
    }
    ega_gc_data(p, 255);
    ega_gc(p, 5, 0);
    return bx;
}

void hud_draw_number(Game *g, uint16_t value, uint16_t dest)
{
    (void)hud_draw_number_bx(g, value, dest);
}

/* orig 11BC:2E46: thirteen column labels and eight row labels. */
void map_draw_grid_labels(Game *g, uint16_t column, uint16_t row)
{
    uint8_t *ds = g->ds;
    for (unsigned i = 0; i < 13; ++i, ++column) {
        unsigned x = 18 + i * 21;
        DS_U16(ds, 0xE170) = (x & 7) >= 4 ? 0xFFFF : 0;
        if (column < 192)
            hud_draw_number(g, column, (uint16_t)(0x142 + (x >> 3)));
    }
    DS_U16(ds, 0xE170) = 0;
    for (uint16_t dest = 0x1B9; dest < 0x1A90; dest += 0x348, ++row)
        if (row < 128)
            hud_draw_number(g, row, dest + 0xF0);
}

/* orig 0000:C7ED: zero-terminated small text, with lowercase folded to capitals.
 * Unlike numeric drawing this routine preserves the existing sequencer mask. */
void hud_draw_text(Game *g, uint16_t text, uint16_t dest)
{
    uint8_t *ds = g->ds, *p = g->planes;
    dest += DS_U16(ds, DS_DRAW_PAGE);
    ega_gc(p, 5, 2);
    ega_gc_select(p, 8);
    uint16_t half = DS_U16(ds, 0xE170);
    for (;;) {
        uint8_t ch = DS_U8(ds, text++);
        if (!ch)
            break;
        if (ch != ' ') {
            if (ch >= 'a' && ch <= 'z')
                ch -= 32;
            ch = (uint8_t)(ch - 0x21);
            uint16_t font = 0xE02A + (ch >> 1);
            uint8_t mask = 0xF0;
            if (ch & 1) {
                mask = 0x0F;
                if (!half) {
                    font += 0xA0;
                    mask = 0xF0;
                }
            } else if (half) {
                font += 0xA0;
                mask = 0x0F;
            }
            for (int row = 0; row < 5; ++row) {
                ega_gc_data(p, DS_U8(ds, font + row * 32) & mask);
                uint16_t at = dest + row * 40;
                ega_load(p, at);
                ega_store(p, at, DS_U8(ds, DS_NUMBER_COLOUR));
            }
        }
        half = (uint16_t)~half;
        unsigned carry = half >> 15;
        half = (uint16_t)((half << 1) | carry);
        dest += !carry;
    }
    ega_gc_data(p, 255);
    ega_gc(p, 5, 0);
}
