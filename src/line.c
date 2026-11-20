/* Line drawing on the EGA screen, and polygon outlines built from it. */
#include "term.h"

enum {
    LN_CUR_X = 0x122E, /* u16: current drawing position */
    LN_CUR_Y = 0x1230,
    LN_PAGE_OFFSET = 0x1234,
    LN_ROW_OFFSETS = 0x1252, /* u16[200]: y * 40 */
    LN_COLOUR = 0x468C,
    LN_POINTS = 0x4694, /* polygon points left by polygon_setup */
    LN_FIRST_X = 0x7752,
    LN_FIRST_Y = 0x7754,
};

/* stride: 40 bytes a row (320 wide), or 80 for the 640-wide screen, whose routines double
 * the 40-byte row table's entries */
static uint16_t row_offset(const uint8_t *ds, uint16_t y, uint16_t stride)
{
    uint16_t row = DS_U16(ds, (uint16_t)(LN_ROW_OFFSETS + (uint16_t)(y * 2)));
    return stride == 80 ? (uint16_t)(row * 2) : row;
}

static uint16_t row_address(const uint8_t *ds, uint16_t x, uint16_t y, uint16_t stride)
{
    return (uint16_t)((x >> 3) + row_offset(ds, y, stride) + DS_U16(ds, LN_PAGE_OFFSET));
}

/* OR ES:[DI],AL: read the byte (loading the latches) and write it back with `value` OR-ed
 * in. With set/reset enabled for all planes the value does not matter; the bit mask does. */
static void or_byte(uint8_t *planes, uint16_t addr, uint8_t value)
{
    ega_store(planes, addr, (uint8_t)(ega_load(planes, addr) | value));
}

/* orig 0000:0DC7 (and 1090 for the 640-wide screen)   vertical line, both ends included. Not
 * drawn on the left or right edge of the view window (those are clipping artefacts).
 * Like the horizontal line, it sets the bit mask and set/reset but neither the plane mask
 * nor the write mode: it draws in whatever planes the last routine left enabled. */
static void line_vertical(const uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y0, uint16_t y1,
                          uint16_t stride)
{
    if (x == DS_U16(ds, DS_VIEW_LEFT) || x == DS_U16(ds, DS_VIEW_RIGHT) || y0 == y1)
        return;
    if (y0 > y1) {
        uint16_t t = y0;
        y0 = y1;
        y1 = t;
    }
    uint16_t addr = row_address(ds, x, y0, stride);
    /* The original doubles BX for the row lookup, then shifts it back.
     * Its high bit is lost before subtracting from the far endpoint. */
    uint16_t rows = (uint16_t)(y1 - (y0 & 0x7FFF) + 1);
    ega_gc(planes, 8, (uint8_t)(0x80 >> (x & 7)));
    ega_gc(planes, 1, 0x0F);
    ega_gc(planes, 0, DS_U8(ds, LN_COLOUR));
    do {
        or_byte(planes, addr, 0);
        addr = (uint16_t)(addr + stride);
    } while (--rows);
    ega_gc(planes, 1, 0);
    ega_gc(planes, 8, 0xFF);
}

/* orig 0000:0E39 (and 1106)   horizontal line from the smaller x up to, but not including, the
 * larger. Not drawn on the top or bottom edge of the view window. */
static void line_horizontal(const uint8_t *ds, uint8_t *planes, uint16_t x0, uint16_t x1, uint16_t y,
                            uint16_t stride)
{
    if (y == DS_U16(ds, DS_VIEW_TOP) || y == DS_U16(ds, DS_VIEW_BOTTOM) || x0 == x1)
        return;
    if (x0 > x1) {
        uint16_t t = x0;
        x0 = x1;
        x1 = t;
    }
    ega_gc(planes, 1, 0x0F);
    ega_gc(planes, 0, DS_U8(ds, LN_COLOUR));
    uint16_t left_byte = (uint16_t)(x0 >> 3), right_byte = (uint16_t)(x1 >> 3);
    uint16_t addr = (uint16_t)(row_offset(ds, y, stride) + left_byte + DS_U16(ds, LN_PAGE_OFFSET));
    uint8_t rmask = (uint8_t)(0xFF00u >> (x1 & 7));
    if (left_byte == right_byte) {
        uint8_t lmask = (uint8_t)(((left_byte & 0xFF00u) | 0xFFu) >> (x0 & 7));
        ega_gc(planes, 8, (uint8_t)(lmask & rmask));
        or_byte(planes, addr, 8);
        ega_gc(planes, 8, 0xFF);
        ega_gc(planes, 1, 0);
        return;
    }
    uint16_t span = (uint16_t)(right_byte - left_byte);
    ega_gc(planes, 8, (uint8_t)(0xFF >> (x0 & 7)));
    or_byte(planes, addr, 8);
    addr++;
    if (span != 1) {
        ega_gc(planes, 8, 0xFF);
        for (uint16_t n = (uint16_t)(span - 1); n; n--) { /* REP STOSB of the value 8 */
            ega_store(planes, addr, 8);
            addr++;
        }
    }
    ega_gc(planes, 8, rmask);
    or_byte(planes, addr, 8);
    ega_gc(planes, 1, 0);
    ega_gc(planes, 8, 0xFF);
}

/* orig 0000:0F32 (stride 40) and 0000:1201 (stride 80, the 640-wide screen, with the octants
 * 12A3..12F7 and the start 1313)   in AX = x, BX = y
 * Draws from the current position to (x, y) in the fill colour and makes (x, y) the current
 * position. Sloped lines are drawn from their upper end and leave out their lower end. */
static uint32_t line_draw(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y, uint16_t stride)
{
    uint16_t ax = x, bx = y, cx = DS_U16(ds, LN_CUR_X), dx = DS_U16(ds, LN_CUR_Y);
    if (ax == cx) {
        line_vertical(ds, planes, ax, bx, dx, stride);
        if (x != DS_U16(ds, DS_VIEW_LEFT) && x != DS_U16(ds, DS_VIEW_RIGHT) && bx != dx) {
            /* 1090 keeps its stride in BX for the loop */
            bx = stride == 80 ? 0x50 : (bx < dx ? bx : dx) & 0x7FFF;
            dx = 0x03CE;
        }
    } else if (bx == dx) {
        line_horizontal(ds, planes, ax, cx, bx, stride);
        if (y != DS_U16(ds, DS_VIEW_TOP) && y != DS_U16(ds, DS_VIEW_BOTTOM)) {
            bx = (ax >> 3) == (cx >> 3) ? (uint16_t)(0xFF00u >> ((ax > cx ? ax : cx) & 7)) : (uint16_t)(y * 2);
            dx = 0x03CE;
        }
    } else {
        if (dx < bx) { /* start from the upper end */
            uint16_t t = ax;
            ax = cx;
            cx = t;
            t = bx;
            bx = dx;
            dx = t;
        }
        uint16_t height = (uint16_t)(dx - bx);
        int16_t run = (int16_t)(cx - ax);
        uint16_t addr = row_address(ds, ax, bx, stride);
        uint8_t mask = (uint8_t)(0x80 >> (ax & 7));
        int rightwards = run >= 0;
        uint16_t width = (uint16_t)(rightwards ? run : -run);
        int16_t err;
        uint16_t n;
        /* orig 0000:1075: sloped lines also set the function and write mode, not the plane mask */
        ega_gc(planes, 1, 0x0F);
        ega_gc(planes, 0, DS_U8(ds, LN_COLOUR));
        ega_gc(planes, 3, 0);
        ega_gc(planes, 5, 0);
        ega_gc_select(planes, 8);
        if (width >= height) { /* one pixel per column */
            err = (int16_t)-width;
            n = width;
            do {
                ega_gc_data(planes, mask);
                or_byte(planes, addr, mask);
                if (rightwards) {
                    if (mask & 1)
                        addr++;
                    mask = (uint8_t)((mask >> 1) | (mask << 7));
                } else {
                    if (mask & 0x80)
                        addr--;
                    mask = (uint8_t)((mask << 1) | (mask >> 7));
                }
                err = (int16_t)(err + height);
                if (err >= 0) {
                    err = (int16_t)(err - width);
                    addr = (uint16_t)(addr + stride);
                }
            } while (--n);
        } else { /* one pixel per row */
            err = (int16_t)-height;
            n = height;
            do {
                ega_gc_data(planes, mask);
                or_byte(planes, addr, mask);
                addr = (uint16_t)(addr + stride);
                err = (int16_t)(err + width);
                if (err >= 0) {
                    err = (int16_t)(err - height);
                    if (rightwards) {
                        if (mask & 1)
                            addr++;
                        mask = (uint8_t)((mask >> 1) | (mask << 7));
                    } else {
                        if (mask & 0x80)
                            addr--;
                        mask = (uint8_t)((mask << 1) | (mask >> 7));
                    }
                }
            } while (--n);
        }
        bx = (uint16_t)err;
        ega_gc_data(planes, 0xFF);
        ega_gc(planes, 1, 0);
        dx = 0x03CE;
    }
    DS_U16(ds, LN_CUR_X) = x;
    DS_U16(ds, LN_CUR_Y) = y;
    return bx | ((uint32_t)dx << 16);
}

uint32_t line_to_registers(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    return line_draw(ds, planes, x, y, 40);
}

uint32_t line_to_wide_registers(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    return line_draw(ds, planes, x, y, 80);
}

void line_to_wide(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    (void)line_draw(ds, planes, x, y, 80);
}

uint16_t line_to_bx(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    return (uint16_t)line_to_registers(ds, planes, x, y);
}

void line_to(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    (void)line_to_bx(ds, planes, x, y);
}

/* orig 0000:48A5   draws the closed outline of the polygon whose points polygon_setup left
 * at DS:4694, in the fill colour. */
uint16_t polygon_outline_dx(uint8_t *ds, uint8_t *planes, uint16_t dx)
{
    uint16_t si = LN_POINTS;
    uint16_t x = DS_U16(ds, si);
    if (x == 0xFFFF)
        return dx;
    uint16_t y = DS_U16(ds, (uint16_t)(si + 2));
    si = (uint16_t)(si + 4);
    DS_U16(ds, LN_CUR_X) = x;
    DS_U16(ds, LN_FIRST_X) = x;
    DS_U16(ds, LN_CUR_Y) = y;
    DS_U16(ds, LN_FIRST_Y) = y;
    for (;;) {
        x = DS_U16(ds, si);
        si = (uint16_t)(si + 2);
        if (x == 0xFFFF)
            break;
        y = DS_U16(ds, si);
        si = (uint16_t)(si + 2);
        dx = line_to_registers(ds, planes, x, y) >> 16;
    }
    x = DS_U16(ds, LN_FIRST_X);
    y = DS_U16(ds, LN_FIRST_Y);
    if (x != DS_U16(ds, LN_CUR_X) || y != DS_U16(ds, LN_CUR_Y))
        dx = line_to_registers(ds, planes, x, y) >> 16;
    return dx;
}

void polygon_outline(uint8_t *ds, uint8_t *planes)
{
    (void)polygon_outline_dx(ds, planes, 0);
}
