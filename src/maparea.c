/* Full-area map's 640-pixel line and viewport overlay. */
#include "term.h"
static void or_byte(uint8_t *p, uint16_t at, uint8_t value)
{
    ega_store(p, at, (uint8_t)(ega_load(p, at) | value));
}

/* orig 1343, including 13E3..1482. All lines omit their final pixel. */
void area_line_to(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    uint16_t ax = x, bx = y, cx = DS_U16(ds, DS_PEN_X), dx = DS_U16(ds, DS_PEN_Y);
    if (ax == cx && bx == dx)
        return;
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
    uint16_t addr =
        (uint16_t)((ax >> 3) + 2 * DS_U16(ds, (uint16_t)(0x1252 + (uint16_t)(bx * 2))) + DS_U16(ds, DS_DRAW_PAGE));
    uint8_t mask = (uint8_t)(0x80 >> (ax & 7));
    int rightwards = run >= 0;
    uint16_t width = (uint16_t)(rightwards ? run : -run);
    int16_t err;
    uint16_t n;
    /* orig 0000:1075: retain the plane mask; set function and write mode. */
    ega_gc(planes, 1, 0x0F);
    ega_gc(planes, 0, DS_U8(ds, DS_FILL_COLOUR));
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
                addr = (uint16_t)(addr + 80);
            }
        } while (--n);
    } else { /* one pixel per row */
        err = (int16_t)-height;
        n = height;
        do {
            ega_gc_data(planes, mask);
            or_byte(planes, addr, mask);
            addr = (uint16_t)(addr + 80);
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
    ega_gc_data(planes, 0xFF);
    ega_gc(planes, 1, 0);
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
}

/* orig D102: retain the original unsigned clipping tests, including the 639
 * horizontal-line Y limit. Always retain the requested endpoint in the pen state. */
void area_line_clipped(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    uint16_t ax = x, bx = y, cx = DS_U16(ds, DS_PEN_X), dx = DS_U16(ds, DS_PEN_Y);
    int draw = 1;
    if (ax == cx) {
        if ((int16_t)ax < 0 || ax > 639)
            draw = 0;
        else {
            if ((int16_t)bx >= (int16_t)dx) {
                uint16_t t = ax;
                ax = cx;
                cx = t;
                t = bx;
                bx = dx;
                dx = t;
            }
            if ((int16_t)bx < 0)
                bx = 0;
            if (dx > 349)
                dx = 349;
        }
    } else {
        if ((int16_t)bx < 0 || bx > 639)
            draw = 0;
        else {
            if ((int16_t)ax >= (int16_t)cx) {
                uint16_t t = ax;
                ax = cx;
                cx = t;
                t = bx;
                bx = dx;
                dx = t;
            }
            if ((int16_t)ax < 0)
                ax = 0;
            if (cx > 639)
                cx = 639;
        }
    }
    if (draw) {
        DS_U16(ds, DS_PEN_X) = cx;
        DS_U16(ds, DS_PEN_Y) = dx;
        area_line_to(ds, planes, ax, bx);
    }
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
}

static uint16_t area_divide(uint32_t value, uint16_t divisor)
{
    uint32_t q = value / divisor;
    return q > 65535 ? (uint16_t)value : (uint16_t)q;
}

/* orig D0A6: mark the player's position and the local map's view rectangle. */
void map_area_viewport(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t p = DS_U16(ds, DS_PLAYER);
    uint32_t wx = DS_U16(ds, p + 34) | ((uint32_t)DS_U16(ds, p + 36) << 16);
    uint32_t wz = DS_U16(ds, p + 42) | ((uint32_t)DS_U16(ds, p + 44) << 16);
    uint16_t x = area_divide(wx, 307), y = area_divide(wz, 374);
    DS_U16(ds, DS_POINTER_X) = x;
    DS_U16(ds, DS_POINTER_Y) = y;
    x -= 27;
    y -= 15;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
    DS_U8(ds, DS_FILL_COLOUR) = 12;
    area_line_clipped(ds, g->planes, (uint16_t)(x + 54), y);
    area_line_clipped(ds, g->planes, (uint16_t)(x + 54), (uint16_t)(y + 30));
    area_line_clipped(ds, g->planes, x, (uint16_t)(y + 30));
    area_line_clipped(ds, g->planes, x, y);
}
