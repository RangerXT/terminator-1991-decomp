/* Scan conversion and filling of one projected, clipped polygon. */
#include "term.h"

enum {
    PF_COUNT = 0x4688, /* u16: vertex count of the polygon */
    PF_COUNT_X2 = 0x468A,
    PF_FILL_COLOUR = 0x468C, /* u8: 0-15 solid, 16-135 dither pair index + 16 */
    PF_CHAIN_B_PTR = 0x468E, /* u16: current segment of the edge chain walked backwards */
    PF_CHAIN_A_PTR = 0x4690, /* u16: current segment of the edge chain walked forwards */
    PF_POINTS_END = 0x4692,
    PF_POINTS = 0x4694,  /* (x, y) words in polygon order, FFFF after the last */
    PF_CHAIN_B = 0x46E4, /* points from the top going backwards, FFFF terminated */
    PF_CHAIN_A = 0x470C, /* points from the top going forwards, FFFF terminated */
    PF_SPAN_COUNT = 0x4734,
    PF_SPAN_PTR = 0x4736,
    PF_SPANS = 0x4738, /* per scanline: (larger x, smaller x) */
    PF_TOP_Y = 0x4A58,
    PF_LEFT_MASKS = 0x4A5A,  /* u8[8]: FF 7F 3F ... 01 */
    PF_RIGHT_MASKS = 0x4A62, /* u8[8]: 80 C0 E0 ... FF */
    PF_DONE = 0x4A6A,
    PF_HEIGHT = 0x4B5E,
    PF_B_REMAINDER = 0x4B60,
    PF_A_REMAINDER = 0x4B62,
    PF_B_QUOTIENT = 0x4B64,
    PF_A_QUOTIENT = 0x4B66,
    PF_B_STEP = 0x4B68, /* u16: address of the routine that steps chain B one scanline */
    PF_A_STEP = 0x4B6A,
    PF_DITHER_PAIR = 0x4B6C, /* u16: the two colours of a dithered fill, swapped every row */
    PF_ROW_OFFSETS = 0x1252, /* u16[200]: y * 40 */
    PF_PAGE_OFFSET = 0x1234,
    PF_BOTTOM_ROW = 0x11C6,
};

/* The four step routines of each chain, by their original addresses. "Small" steps move at
 * most one pixel per scanline; "big" steps first add a whole number of pixels. */
enum {
    B_BIG_LEFT = 0x7C,
    B_SMALL_LEFT = 0x80,
    B_BIG_RIGHT = 0x9C,
    B_SMALL_RIGHT = 0xA0,
    A_BIG_LEFT = 0x8C,
    A_SMALL_LEFT = 0x90,
    A_BIG_RIGHT = 0xAC,
    A_SMALL_RIGHT = 0xB0,
};

/* orig 11BC:01AD   in SI = address of the face's vertex count
 * Copies the polygon's screen points to PF_POINTS, finds the topmost one and splits the
 * outline into two chains going down from it. Returns 0, or 0xFFFF if the polygon cannot be
 * filled this way (fewer than two points, or the outline does not form two monotonic chains). */
static uint32_t polygon_setup_registers(uint8_t *ds, uint16_t count_at)
{
    uint16_t si = count_at, di = PF_POINTS, top = 0, min_y = 0x3E8;
    uint16_t count = DS_U16(ds, si);
    si = (uint16_t)(si + 2);
    DS_U16(ds, PF_COUNT) = count;
    if (count == 0)
        return (0x3E8u << 16) | 0xFFFF;
    for (uint16_t i = 0; i < count; i++) {
        uint16_t p = (uint16_t)(DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR) + DS_U16(ds, si));
        si = (uint16_t)(si + 2);
        DS_U16(ds, di) = DS_U16(ds, p);
        uint16_t y = DS_U16(ds, (uint16_t)(p + 2));
        DS_U16(ds, (uint16_t)(di + 2)) = y;
        di = (uint16_t)(di + 4);
        if (y < min_y) {
            min_y = y;
            top = di;
        }
    }
    DS_U16(ds, PF_POINTS_END) = di;
    DS_U16(ds, di) = 0xFFFF;
    uint8_t limit = (uint8_t)count, steps;
    DS_U16(ds, PF_COUNT_X2) = (uint16_t)(count * 2);
    if ((uint16_t)(count * 2) < 3)
        return ((uint32_t)(uint16_t)(count * 2) << 16) | 0xFFFF;
    top = (uint16_t)(top - 4);

    uint16_t x = 0, y = 0; /* CX and DX: the last point put into the chain */

    /* chain A: forwards through the point list while y does not decrease */
    di = PF_CHAIN_A;
    y = 0;
    steps = 0;
    si = top;
    for (;;) {
        uint16_t py = DS_U16(ds, (uint16_t)(si + 2));
        if (y == py) { /* horizontal step: keep the larger x */
            if (x < DS_U16(ds, si)) {
                di = (uint16_t)(di - 4);
                x = DS_U16(ds, si);
                y = py;
                DS_U16(ds, di) = x;
                DS_U16(ds, (uint16_t)(di + 2)) = y;
                di = (uint16_t)(di + 4);
            }
            si = (uint16_t)(si + 4);
        } else if (y > py) {
            break;
        } else {
            x = DS_U16(ds, si);
            y = py;
            DS_U16(ds, di) = x;
            DS_U16(ds, (uint16_t)(di + 2)) = y;
            di = (uint16_t)(di + 4);
            si = (uint16_t)(si + 4);
        }
        if (limit < steps)
            return ((uint32_t)y << 16) | 0xFFFF;
        steps++;
        if (si == DS_U16(ds, PF_POINTS_END))
            si = PF_POINTS;
    }
    DS_U16(ds, di) = 0xFFFF;

    /* chain B: backwards, keeping the smaller x on horizontal steps */
    di = PF_CHAIN_B;
    y = 0;
    steps = 0;
    si = top;
    for (;;) {
        uint16_t py = DS_U16(ds, (uint16_t)(si + 2));
        if (y == py) {
            if (x >= DS_U16(ds, si)) {
                di = (uint16_t)(di - 4);
                x = DS_U16(ds, si);
                y = py;
                DS_U16(ds, di) = x;
                DS_U16(ds, (uint16_t)(di + 2)) = y;
                di = (uint16_t)(di + 4);
            }
            si = (uint16_t)(si - 4);
        } else if (y > py) {
            break;
        } else {
            x = DS_U16(ds, si);
            y = py;
            DS_U16(ds, di) = x;
            DS_U16(ds, (uint16_t)(di + 2)) = y;
            di = (uint16_t)(di + 4);
            si = (uint16_t)(si - 4);
        }
        if (limit < steps)
            return ((uint32_t)y << 16) | 0xFFFF;
        steps++;
        if (si < PF_POINTS)
            si = (uint16_t)(DS_U16(ds, PF_POINTS_END) - 4);
    }
    DS_U16(ds, di) = 0xFFFF;
    DS_U16(ds, PF_CHAIN_B_PTR) = PF_CHAIN_B;
    DS_U16(ds, PF_CHAIN_A_PTR) = PF_CHAIN_A;
    return (uint32_t)y << 16;
}

uint16_t polygon_setup(uint8_t *ds, uint16_t count_at)
{
    return (uint16_t)polygon_setup_registers(ds, count_at);
}

/* Registers of the scanline loop. */
typedef struct {
    uint16_t xb, err_b, mod_b; /* SI, AX, DX */
    uint16_t xa, err_a, mod_a; /* DI, BX, BP */
    uint8_t rows_b, rows_a;    /* CH, CL */
} Walk;

/* orig 11BC:00BC   start the next segment of chain B that has some height */
static void chain_b_next(uint8_t *ds, Walk *w)
{
    uint16_t p = DS_U16(ds, PF_CHAIN_B_PTR);
    for (;;) {
        if (DS_U16(ds, (uint16_t)(p + 4)) == 0xFFFF) {
            DS_U8(ds, PF_DONE) = 1;
            return;
        }
        w->rows_b = (uint8_t)(DS_U8(ds, (uint16_t)(p + 6)) - DS_U8(ds, (uint16_t)(p + 2)));
        p = (uint16_t)(p + 4);
        if (w->rows_b != 0)
            break;
    }
    DS_U16(ds, PF_CHAIN_B_PTR) = p;
    int16_t run = (int16_t)(DS_U16(ds, p) - DS_U16(ds, (uint16_t)(p - 4)));
    uint16_t mag;
    if (run >= 0) {
        mag = (uint16_t)run;
        DS_U16(ds, PF_B_STEP) = (mag < 0x100 && (uint8_t)mag < w->rows_b) ? B_SMALL_RIGHT : B_BIG_RIGHT;
    } else {
        mag = (uint16_t)-run;
        DS_U16(ds, PF_B_STEP) = (mag < 0x100 && (uint8_t)mag < w->rows_b) ? B_SMALL_LEFT : B_BIG_LEFT;
    }
    DS_U16(ds, PF_HEIGHT) = w->rows_b;
    DS_U16(ds, PF_B_REMAINDER) = (uint16_t)(mag % w->rows_b);
    DS_U16(ds, PF_B_QUOTIENT) = (uint16_t)(mag / w->rows_b);
    w->mod_b = w->rows_b;
    w->err_b = 0;
}

/* orig 11BC:0136   the same for chain A */
static void chain_a_next(uint8_t *ds, Walk *w)
{
    uint16_t p = DS_U16(ds, PF_CHAIN_A_PTR);
    for (;;) {
        if (DS_U16(ds, (uint16_t)(p + 4)) == 0xFFFF) {
            DS_U8(ds, PF_DONE) = 1;
            return;
        }
        w->rows_a = (uint8_t)(DS_U8(ds, (uint16_t)(p + 6)) - DS_U8(ds, (uint16_t)(p + 2)));
        p = (uint16_t)(p + 4);
        if (w->rows_a != 0)
            break;
    }
    DS_U16(ds, PF_CHAIN_A_PTR) = p;
    int16_t run = (int16_t)(DS_U16(ds, p) - DS_U16(ds, (uint16_t)(p - 4)));
    uint16_t mag;
    if (run >= 0) {
        mag = (uint16_t)run;
        DS_U16(ds, PF_A_STEP) = (mag < 0x100 && (uint8_t)mag < w->rows_a) ? A_SMALL_RIGHT : A_BIG_RIGHT;
    } else {
        mag = (uint16_t)-run;
        DS_U16(ds, PF_A_STEP) = (mag < 0x100 && (uint8_t)mag < w->rows_a) ? A_SMALL_LEFT : A_BIG_LEFT;
    }
    DS_U16(ds, PF_HEIGHT) = w->rows_a;
    DS_U16(ds, PF_A_REMAINDER) = (uint16_t)(mag % w->rows_a);
    DS_U16(ds, PF_A_QUOTIENT) = (uint16_t)(mag / w->rows_a);
    w->mod_a = w->rows_a;
    w->err_a = 0;
}

/* orig 11BC:007C..00BB   advance each chain by one scanline */
static void chain_b_step(const uint8_t *ds, Walk *w)
{
    uint16_t kind = DS_U16(ds, PF_B_STEP);
    int right = (kind == B_BIG_RIGHT || kind == B_SMALL_RIGHT);
    if (kind == B_BIG_RIGHT)
        w->xb = (uint16_t)(w->xb + DS_U16(ds, PF_B_QUOTIENT));
    else if (kind == B_BIG_LEFT)
        w->xb = (uint16_t)(w->xb - DS_U16(ds, PF_B_QUOTIENT));
    w->err_b = (uint16_t)(w->err_b + DS_U16(ds, PF_B_REMAINDER));
    if (w->err_b >= w->mod_b) {
        w->err_b = (uint16_t)(w->err_b - w->mod_b);
        w->xb = (uint16_t)(right ? w->xb + 1 : w->xb - 1);
    }
}

static void chain_a_step(const uint8_t *ds, Walk *w)
{
    uint16_t kind = DS_U16(ds, PF_A_STEP);
    int right = (kind == A_BIG_RIGHT || kind == A_SMALL_RIGHT);
    if (kind == A_BIG_RIGHT)
        w->xa = (uint16_t)(w->xa + DS_U16(ds, PF_A_QUOTIENT));
    else if (kind == A_BIG_LEFT)
        w->xa = (uint16_t)(w->xa - DS_U16(ds, PF_A_QUOTIENT));
    w->err_a = (uint16_t)(w->err_a + DS_U16(ds, PF_A_REMAINDER));
    if (w->err_a >= w->mod_a) {
        w->err_a = (uint16_t)(w->err_a - w->mod_a);
        w->xa = (uint16_t)(right ? w->xa + 1 : w->xa - 1);
    }
}

/* orig 11BC:02D8   append one scanline's span: (larger x, smaller x) */
static void span_store(uint8_t *ds, const Walk *w)
{
    uint16_t at = DS_U16(ds, PF_SPAN_PTR);
    if (w->xa < w->xb) {
        DS_U16(ds, at) = w->xb;
        DS_U16(ds, (uint16_t)(at + 2)) = w->xa;
    } else {
        DS_U16(ds, at) = w->xa;
        DS_U16(ds, (uint16_t)(at + 2)) = w->xb;
    }
    DS_U16(ds, PF_SPAN_PTR) = (uint16_t)(at + 4);
    DS_U16(ds, PF_SPAN_COUNT)++;
}

/* Read a byte of the screen and write it straight back: with a bit mask set, this is how
 * the original changes some of the byte's pixels and keeps the rest (MOV AL,ES:[DI] / STOSB). */
static void touch(uint8_t *planes, uint16_t addr)
{
    ega_store(planes, addr, ega_load(planes, addr));
}

/* orig 11BC:0305 (with 03B6, 03D0)   fill the span list with one colour: set/reset holds the
 * colour, the bit mask selects the pixels. The plane mask is set to all four; the write
 * mode and function are left as they were. */
static void fill_solid(uint8_t *ds, uint8_t *planes)
{
    ega_seq_mask(planes, 0x0F);
    ega_gc(planes, 1, 0x0F);
    ega_gc(planes, 0, DS_U8(ds, PF_FILL_COLOUR));
    ega_gc_select(planes, 8);

    uint16_t bottom = (uint16_t)(DS_U16(ds, PF_TOP_Y) + DS_U16(ds, PF_SPAN_COUNT));
    uint16_t limit = (uint16_t)(DS_U16(ds, PF_BOTTOM_ROW) + 8);
    if (bottom > limit) {
        DS_U16(ds, PF_SPAN_COUNT) = (uint16_t)(DS_U16(ds, PF_SPAN_COUNT) - (bottom - limit));
        if ((int16_t)DS_U16(ds, PF_SPAN_COUNT) <= 0)
            return; /* the registers stay as set above */
    }
    uint16_t row =
        (uint16_t)(DS_U16(ds, (uint16_t)(PF_ROW_OFFSETS + 2 * DS_U16(ds, PF_TOP_Y))) + DS_U16(ds, PF_PAGE_OFFSET));
    uint16_t at = PF_SPANS;
    for (uint16_t n = DS_U16(ds, PF_SPAN_COUNT); n; n--) {
        uint16_t right = DS_U16(ds, at), left = DS_U16(ds, (uint16_t)(at + 2));
        uint16_t addr = (uint16_t)(row + (left >> 3));
        uint16_t bytes = (uint16_t)((right >> 3) - (left >> 3));
        uint8_t lmask = DS_U8(ds, (uint16_t)(PF_LEFT_MASKS + (left & 7)));
        uint8_t rmask = DS_U8(ds, (uint16_t)(PF_RIGHT_MASKS + (right & 7)));
        if (bytes == 0) {
            ega_gc_data(planes, (uint8_t)(lmask & rmask));
            touch(planes, addr);
        } else {
            ega_gc_data(planes, lmask);
            touch(planes, addr);
            addr++;
            if (--bytes != 0) {
                ega_gc_data(planes, 0xFF);
                for (; bytes; bytes--) { /* REP STOS of FF, no reads */
                    ega_store(planes, addr, 0xFF);
                    addr++;
                }
            }
            ega_gc_data(planes, rmask);
            touch(planes, addr);
        }
        at = (uint16_t)(at + 4);
        row = (uint16_t)(row + 40);
    }
    ega_gc_data(planes, 0xFF);
    ega_gc(planes, 1, 0);
}

/* The two writes that put the dither pair into the pixels of one byte selected by `mask`. */
static void dither_byte(uint8_t *planes, uint16_t addr, uint8_t mask, uint8_t odd, uint8_t even)
{
    ega_gc_data(planes, (uint8_t)(mask & 0x55));
    ega_load(planes, addr);
    ega_store(planes, addr, odd);
    ega_gc_data(planes, (uint8_t)(mask & 0xAA));
    ega_load(planes, addr);
    ega_store(planes, addr, even);
}

/* orig 11BC:04B4   `bytes` bytes of one value. The latches are loaded once, from the first
 * byte or two, not for every byte. */
static void fill_run(uint8_t *planes, uint16_t addr, uint16_t bytes, uint8_t value)
{
    if (bytes & 1) {
        ega_load(planes, addr);
        ega_store(planes, addr, value);
        addr++;
    }
    bytes >>= 1;
    if (bytes == 0)
        return;
    ega_load(planes, addr);
    ega_load(planes, (uint16_t)(addr + 1));
    for (bytes = (uint16_t)(bytes * 2); bytes; bytes--) {
        ega_store(planes, addr, value);
        addr++;
    }
}

/* orig 11BC:03D9 (with 04C8, 04DB)   fill the span list with a two-colour checkerboard, in
 * write mode 2 (the byte written is a colour). The whole bytes of a span are done in two
 * passes, odd pixels then even pixels. The pair is swapped for every row.
 * (Unlike the solid fill, the original does not clip this one at the bottom row.) */
static void fill_dither(uint8_t *ds, uint8_t *planes)
{
    ega_seq_mask(planes, 0x0F);
    ega_gc(planes, 5, 2);
    ega_gc_select(planes, 8);

    uint16_t row =
        (uint16_t)(DS_U16(ds, (uint16_t)(PF_ROW_OFFSETS + 2 * DS_U16(ds, PF_TOP_Y))) + DS_U16(ds, PF_PAGE_OFFSET));
    uint16_t at = PF_SPANS;
    uint16_t n = DS_U16(ds, PF_SPAN_COUNT);
    do { /* LOOP: a count of 0 means 65536 */
        uint16_t pair = DS_U16(ds, PF_DITHER_PAIR);
        pair = (uint16_t)((pair << 8) | (pair >> 8));
        DS_U16(ds, PF_DITHER_PAIR) = pair;
        uint8_t odd = (uint8_t)pair, even = (uint8_t)(pair >> 8);

        uint16_t right = DS_U16(ds, at), left = DS_U16(ds, (uint16_t)(at + 2));
        uint16_t addr = (uint16_t)(row + (left >> 3));
        uint16_t bytes = (uint16_t)((right >> 3) - (left >> 3));
        uint8_t lmask = DS_U8(ds, (uint16_t)(PF_LEFT_MASKS + (left & 7)));
        uint8_t rmask = DS_U8(ds, (uint16_t)(PF_RIGHT_MASKS + (right & 7)));
        if (bytes == 0) {
            dither_byte(planes, addr, (uint8_t)(lmask & rmask), odd, even);
        } else {
            dither_byte(planes, addr, lmask, odd, even);
            addr++;
            if (--bytes != 0) {
                ega_gc_data(planes, 0x55);
                fill_run(planes, addr, bytes, odd);
                ega_gc_data(planes, 0xAA);
                fill_run(planes, addr, bytes, even);
                addr = (uint16_t)(addr + bytes);
            }
            dither_byte(planes, addr, rmask, odd, even);
        }
        at = (uint16_t)(at + 4);
        row = (uint16_t)(row + 40);
    } while (--n);
    ega_gc_data(planes, 0xFF);
    ega_gc(planes, 5, 0);
}

/* orig 11BC:0294   an outline with no height (or a single point) is drawn as one horizontal
 * line from its smallest to its largest x, on the row of its first point. */
static uint16_t degenerate_line(uint8_t *ds, uint8_t *planes)
{
    uint16_t lo = 0xFA00, hi = 0, si = PF_POINTS;
    uint16_t n = DS_U16(ds, PF_COUNT);
    do {
        uint16_t x = DS_U16(ds, si);
        if (hi <= x)
            hi = x;
        if (lo >= x)
            lo = x;
        si = (uint16_t)(si + 4);
    } while (--n);
    uint16_t y = DS_U16(ds, PF_POINTS + 2);
    DS_U16(ds, DS_PEN_Y) = y;
    DS_U16(ds, DS_PEN_X) = lo;
    return line_to_registers(ds, planes, hi, y) >> 16;
}

/* orig 11BC:0000 (far)   in SI = address of the face's vertex count; colour in DS:468C
 *
 * Fills one polygon on the EGA screen (`planes` = 4 x 65536 bytes, plane 0 first).
 * Returns 0 if it was filled, -1 if the outline was degenerate and a horizontal line was
 * drawn instead (the original returns AX = FFFF then, which stops the caller drawing an
 * outline).
 */
uint32_t polygon_face_registers(uint8_t *ds, uint8_t *planes, uint16_t count_at, int fill)
{
    if (!fill)
        return polygon_setup_registers(ds, count_at);
    DS_U8(ds, PF_DONE) = 0;
    if (polygon_setup(ds, count_at) == 0xFFFF) {
        /* A dithered colour is reduced to the second colour of its pair for the line. */
        if (DS_U8(ds, PF_FILL_COLOUR) >= 0x10)
            DS_U8(ds, PF_FILL_COLOUR) =
                DS_U8(ds, (uint16_t)(DS_DITHER_PAIRS + 2 * (uint8_t)(DS_U8(ds, PF_FILL_COLOUR) - 0x10)));
        return ((uint32_t)degenerate_line(ds, planes) << 16) | 0xFFFF;
    }

    Walk w;
    memset(&w, 0, sizeof w);
    uint16_t b = DS_U16(ds, PF_CHAIN_B_PTR);
    w.xb = DS_U16(ds, b);
    DS_U16(ds, PF_TOP_Y) = DS_U16(ds, (uint16_t)(b + 2));
    w.xa = DS_U16(ds, DS_U16(ds, PF_CHAIN_A_PTR));
    chain_b_next(ds, &w);
    chain_a_next(ds, &w);
    DS_U16(ds, PF_SPAN_PTR) = PF_SPANS;
    DS_U16(ds, PF_SPAN_COUNT) = 0;
    span_store(ds, &w);
    do {
        chain_b_step(ds, &w);
        chain_a_step(ds, &w);
        span_store(ds, &w);
        if (--w.rows_b == 0)
            chain_b_next(ds, &w);
        if (--w.rows_a == 0)
            chain_a_next(ds, &w);
    } while (DS_U8(ds, PF_DONE) == 0);

    if (DS_U8(ds, PF_FILL_COLOUR) >= 0x10) {
        /* orig 11BC:04E4 */
        DS_U16(ds, PF_DITHER_PAIR) =
            DS_U16(ds, (uint16_t)(DS_DITHER_PAIRS + 2 * (uint8_t)(DS_U8(ds, PF_FILL_COLOUR) - 0x10)));
        fill_dither(ds, planes);
    } else {
        fill_solid(ds, planes);
    }
    return 0x03CE0000u;
}

int fill_polygon(uint8_t *ds, uint8_t *planes, uint16_t count_at)
{
    return (int16_t)polygon_face_registers(ds, planes, count_at, 1);
}
