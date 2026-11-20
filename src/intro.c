/* The start-up screen (segment 57C5, called once from 0000:04E8 before the main menu): on the
 * 640x200 screen, lines of text are typed in the scalable font into a one-bit buffer (far
 * segment DS:DE20) with a blinking cursor, and copied to the screen in white over a wireframe
 * logo that slides in from both sides and then zooms in with perspective. A key ends it.
 * Helpers outside the segment: 0000:1769 (buffer to screen), 0000:17C0 (clear the area),
 * 11BC:2925 (one character into the buffer).
 */
#include "term.h"

enum {
    IN_LINE = 0xDE0E,        /* u8: text line the cursor is on */
    IN_PAGE_START = 0xDE0F,  /* u8: at the start of a page of text */
    IN_SECOND_PAGE = 0xDE10, /* u8: the pause after a page has its second half */
    IN_PERSPECTIVE = 0xDE11, /* u8: the logo is zooming (projected) */
    IN_ODD_CHAR = 0xDE12,    /* u8: toggles per character; a frame every second one */
    IN_CHAR = 0xDE14,        /* u16: index into the text */
    IN_COUNTDOWN = 0xDE16,   /* u16: frames of the pause after a page */
    IN_CURSOR_ROWS = 0xDE18, /* u16[]: buffer offset of each text line's cursor */
    IN_BUFFER = 0xDE20,      /* seg: the one-bit text buffer, 80 bytes a row */
    IN_FIRST_X = 0xDE22,     /* u16: first point of the polyline being drawn */
    IN_FIRST_Y = 0xDE24,
    IN_SHIFT_X = 0xDE26,     /* i16: added to every point's x */
    IN_CENTRE_X = 0xDE28,    /* i16: centre of the perspective */
    IN_CENTRE_Y = 0xDE2A,
    IN_ZOOM_STEP = 0xDE2C,   /* u16: added to the divisor each frame of the zoom */
    IN_CLIP_TRIES = 0xDE30,  /* u16 */
    IN_CLIP_CODES = 0xDE32,  /* u16: every outcode of the last clip, OR-ed */
    IN_LEFT_SHIFT = 0xBE8E,  /* i16: the logo halves' offsets while they slide in */
    IN_RIGHT_SHIFT = 0xBE90,
    IN_DIVISOR = 0xBE92,     /* i16: perspective divisor */
    IN_POLYLINES = 0xBE94,   /* u16 count, then per polyline: points, point indices */
    IN_POINTS = 0x50B2,      /* i16 x, y per point, built from C1DE / C334 */
    IN_TEXT = 0xDBB6,
    TX_X = 0xADD6,           /* u16: pixel column of the next character */
    TX_Y = 0xADD8,           /* u16: pixel row of the text line */
    TX_STRIDE = 0xADDA,      /* u16: bytes a row in the buffer */
};

static int pages(Game *g, const MapResources *host, uint16_t which)
{
    return !host || !host->call || host->call(g, MS_SELECT_PAGES, which, 0, host->user) ? -1 : 0;
}

/* orig 57C5:020C   the logo's points, scaled by 16 (y moved up by 645h) */
static void prepare_points(uint8_t *ds)
{
    for (uint16_t i = 0; i < 0xAB; ++i) {
        DS_U16(ds, (uint16_t)(IN_POINTS + i * 4)) = (uint16_t)(DS_U16(ds, (uint16_t)(0xC1DE + i * 2)) << 4);
        DS_U16(ds, (uint16_t)(IN_POINTS + i * 4 + 2)) =
            (uint16_t)((DS_U16(ds, (uint16_t)(0xC334 + i * 2)) << 4) - 0x645);
    }
}

/* orig 57C5:01E3   clear the first `words` words of the text buffer */
static void clear_buffer(Game *g, uint16_t words)
{
    uint8_t *buffer = far_ptr(g, DS_U16(g->ds, IN_BUFFER), 0);
    for (uint16_t at = 0; words; --words, at = (uint16_t)(at + 2))
        buffer[at] = buffer[(uint16_t)(at + 1)] = 0;
}

/* orig 57C5:01F0   the cursor of text line `line`: 16 pixels by 11 rows, set (FFFF) or cleared */
static void cursor(Game *g, uint8_t line, uint16_t value)
{
    uint8_t *ds = g->ds, *buffer = far_ptr(g, DS_U16(ds, IN_BUFFER), 0);
    uint16_t at = DS_U16(ds, (uint16_t)(IN_CURSOR_ROWS + (uint8_t)(line + line)));
    for (unsigned row = 0; row < 11; ++row, at = (uint16_t)(at + 0x50)) {
        buffer[at] = (uint8_t)value;
        buffer[(uint16_t)(at + 1)] = (uint8_t)(value >> 8);
    }
}

/* orig 11BC:2925   one character of the scaled font into the buffer at TX_X, TX_Y */
static void buffer_char(Game *g, uint8_t ch)
{
    uint8_t *ds = g->ds, *buffer = far_ptr(g, DS_U16(ds, IN_BUFFER), 0);
    uint16_t at = (uint16_t)(DS_U16(ds, TX_Y) * DS_U16(ds, TX_STRIDE) + (DS_U16(ds, TX_X) >> 3));
    uint8_t shift = (uint8_t)(DS_U16(ds, TX_X) & 7);
    DS_U8(ds, 0xADE0) = shift;
    uint8_t index = (uint8_t)(ch - 0x20);
    if (!index) {
        DS_U16(ds, TX_X) = (uint16_t)(DS_U16(ds, TX_X) + DS_U8(ds, 0xAE03));
        return;
    }
    uint16_t source = (uint16_t)(DS_U16(ds, 0xADFE) + DS_U8(ds, (uint16_t)(0xAE05 + index)) * DS_U8(ds, 0xADFA));
    DS_U16(ds, TX_X) = (uint16_t)(DS_U16(ds, TX_X) + DS_U8(ds, (uint16_t)(0xAE64 + index)));
    const uint8_t *font = far_ptr(g, DS_U16(ds, 0xAE00), 0);
    uint16_t rows = DS_U8(ds, 0xADF6);
    do { /* LOOP */
        uint16_t to = at;
        uint8_t bytes = DS_U8(ds, 0xADE2);
        do { /* DEC BL / JNZ */
            uint16_t bits = font[source++];
            bits = (uint16_t)((bits >> shift) | (bits << ((16 - shift) & 15)));
            buffer[to] |= (uint8_t)bits;
            buffer[(uint16_t)(to + 1)] |= (uint8_t)(bits >> 8);
            to++;
        } while (--bytes);
        at = (uint16_t)(at + DS_U16(ds, TX_STRIDE));
    } while (--rows);
}

/* orig 0000:1769   rows x width bytes of the buffer onto the drawing page at `to`, its set
 * bits in `colour` */
static void buffer_to_screen(Game *g, uint8_t colour, uint16_t to, uint16_t rows, uint16_t width)
{
    uint8_t *ds = g->ds, *p = g->planes;
    ega_gc(p, 0, colour);
    ega_gc(p, 1, 0x0F);
    ega_gc_select(p, 8);
    to = (uint16_t)(to + DS_U16(ds, DS_DRAW_PAGE));
    const uint8_t *source = far_ptr(g, DS_U8(ds, 0x154B) ? DS_U16(ds, 0x1226) : DS_U16(ds, IN_BUFFER), 0);
    uint16_t from = DS_U8(ds, 0x1535) ? DS_U16(ds, 0x150E) : 0;
    uint16_t skip = (uint16_t)(0x50 - width);
    do { /* LOOP */
        uint16_t n = width;
        do { /* LOOP */
            ega_gc_data(p, source[from++]);
            ega_store(p, to, ega_load(p, to));
            to++;
        } while (--n);
        to = (uint16_t)(to + skip);
        from = (uint16_t)(from + skip);
    } while (--rows);
}

/* orig 0000:17C0   clear the drawing page from row 10 on (14,480 bytes) */
static void clear_area(Game *g)
{
    uint8_t *p = g->planes;
    ega_gc(p, 1, 0x0F);
    ega_gc(p, 0, 0);
    ega_gc(p, 8, 0xFF);
    uint16_t at = (uint16_t)(DS_U16(g->ds, DS_DRAW_PAGE) + 0x320);
    for (unsigned i = 0; i < 0x1C48; ++i) { /* REP STOSW of AX = FF08, left from the OUT */
        ega_store(p, at++, 0x08);
        ega_store(p, at++, 0xFF);
    }
    ega_gc(p, 1, 0);
}

/* orig 57C5:02EF / 030A   with the zoom on, (v - centre) * 256 / divisor + centre. Returns 1
 * when the IDIV overflows: the divide-error handler (0000:0407) then skips two bytes of the
 * four-byte IDIV WORD PTR [BE92], so the CPU goes on inside it with XCHG AX,DX / MOV SI,0603h /
 * SUB DH,BL (02EF) or SUB BL,DH (030A): the result is the dividend's high word, the caller's
 * polyline pointer SI becomes 0603h, and 030A takes the high byte of the dividend's low word
 * from BL. */
static int project(const uint8_t *ds, uint16_t v, uint16_t centre, uint16_t *out, uint8_t *low_high)
{
    if (!DS_U8(ds, IN_PERSPECTIVE)) {
        *out = v;
        return 0;
    }
    int32_t dividend = (int32_t)(int16_t)(uint16_t)(v - DS_U16(ds, centre)) * 256;
    int16_t divisor = DS_I16(ds, IN_DIVISOR);
    int32_t q = divisor ? dividend / divisor : 0;
    if (!divisor || q > 32767 || q < -32768) {
        *out = (uint16_t)((uint32_t)dividend >> 16);
        *low_high = (uint8_t)((uint32_t)dividend >> 8);
        return 1;
    }
    *out = (uint16_t)((uint16_t)q + DS_U16(ds, centre));
    return 0;
}

/* orig 57C5:0459   Cohen-Sutherland outcode against the view window, also OR-ed into DE32 */
static uint16_t outcode(uint8_t *ds, int16_t x, int16_t y)
{
    uint16_t code = 0;
    if (y < DS_I16(ds, DS_VIEW_TOP))
        code |= 8;
    else if (y > DS_I16(ds, DS_VIEW_BOTTOM))
        code |= 4;
    if (x > DS_I16(ds, DS_VIEW_RIGHT))
        code |= 2;
    else if (x < DS_I16(ds, DS_VIEW_LEFT))
        code |= 1;
    DS_U16(ds, IN_CLIP_CODES) |= code;
    return code;
}

/* orig 57C5:0488   move (x, y) onto the edge its outcode names, along the line to (x1, y1) */
static void clip_point(const uint8_t *ds, uint16_t code, uint16_t *x, uint16_t *y, uint16_t x1, uint16_t y1)
{
    if (code & 0x0C) { /* top or bottom */
        uint16_t edge = DS_U16(ds, code & 8 ? DS_VIEW_TOP : DS_VIEW_BOTTOM);
        int32_t product = (int32_t)(int16_t)(uint16_t)(x1 - *x) * (int16_t)(uint16_t)(edge - *y);
        uint16_t divisor = (uint16_t)(y1 - *y);
        if (!divisor)
            divisor = y1;
        *x = (uint16_t)(idiv_or_skip(product, (int16_t)divisor) + *x);
        *y = edge;
    } else { /* right (2) or left */
        uint16_t edge = DS_U16(ds, code & 2 ? DS_VIEW_RIGHT : DS_VIEW_LEFT);
        int32_t product = (int32_t)(int16_t)(uint16_t)(edge - *x) * (int16_t)(uint16_t)(y1 - *y);
        uint16_t divisor = (uint16_t)(x1 - *x);
        if (!divisor)
            divisor = x1;
        *y = (uint16_t)(idiv_or_skip(product, (int16_t)divisor) + *y);
        *x = edge;
    }
}

/* orig 57C5:03F0   clip the line (ax, bx) - (cx, dx) to the view window; 1 when nothing is
 * left (the original's carry). Vertical and horizontal lines are only cut to the window. */
static int clip_line(uint8_t *ds, uint16_t *ax, uint16_t *bx, uint16_t *cx, uint16_t *dx)
{
    DS_U16(ds, IN_CLIP_TRIES) = 4;
    DS_U16(ds, IN_CLIP_CODES) = 0;
    int16_t left = DS_I16(ds, DS_VIEW_LEFT), right = DS_I16(ds, DS_VIEW_RIGHT), top = DS_I16(ds, DS_VIEW_TOP),
            bottom = DS_I16(ds, DS_VIEW_BOTTOM);
    if (*ax == *cx) { /* 034A */
        int swapped = (int16_t)*bx >= (int16_t)*dx;
        uint16_t low = swapped ? *dx : *bx, high = swapped ? *bx : *dx;
        if ((int16_t)*ax < left || (int16_t)*ax > right || (int16_t)high < top || (int16_t)low > bottom)
            return 1;
        if ((int16_t)low < top)
            low = (uint16_t)top;
        if ((int16_t)high > bottom)
            high = (uint16_t)bottom;
        *bx = swapped ? high : low;
        *dx = swapped ? low : high;
        return 0;
    }
    if (*bx == *dx) { /* 03A6 */
        int swapped = (int16_t)*ax >= (int16_t)*cx;
        uint16_t low = swapped ? *cx : *ax, high = swapped ? *ax : *cx;
        if ((int16_t)*bx < top || (int16_t)*bx > bottom || (int16_t)low > right || (int16_t)high < left)
            return 1;
        if ((int16_t)low < left)
            low = (uint16_t)left;
        if ((int16_t)high > right)
            high = (uint16_t)right;
        *ax = swapped ? high : low;
        *cx = swapped ? low : high;
        return 0;
    }
    for (;;) {
        uint16_t first = outcode(ds, (int16_t)*ax, (int16_t)*bx), second = outcode(ds, (int16_t)*cx, (int16_t)*dx);
        if (first & second)
            return 1;
        if (!(first | second))
            return 0;
        if (!first) { /* 044A: the far end, without using up a try */
            clip_point(ds, second, cx, dx, *ax, *bx);
            continue;
        }
        clip_point(ds, first, ax, bx, *cx, *dx);
        if (!--DS_U16(ds, IN_CLIP_TRIES))
            return 1;
    }
}

/* orig 57C5:0325   a clipped 640-wide line from the pen to (x, y); the pen ends at (x, y) */
static void clipped_line(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y)
{
    uint16_t ax = x, bx = y, cx = DS_U16(ds, DS_PEN_X), dx = DS_U16(ds, DS_PEN_Y);
    if (!clip_line(ds, &ax, &bx, &cx, &dx)) {
        DS_U16(ds, DS_PEN_X) = cx;
        DS_U16(ds, DS_PEN_Y) = dx;
        line_to_wide(ds, planes, ax, bx);
    }
    DS_U16(ds, DS_PEN_Y) = y;
    DS_U16(ds, DS_PEN_X) = x;
}

/* orig 57C5:0282   the logo's closed polylines in colour 1, shifted by DE26 */
static void draw_logo(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_FILL_COLOUR) = 1;
    uint16_t at = IN_POLYLINES, lines = DS_U16(ds, at), x, y;
    uint8_t low_high;
    at += 2;
    do { /* LOOP */
        uint16_t n = (uint16_t)(DS_U16(ds, at) - 1), point = (uint16_t)(IN_POINTS + DS_U16(ds, (uint16_t)(at + 2)) * 4);
        at = (uint16_t)(at + 4);
        if (project(ds, (uint16_t)(DS_U16(ds, point) + DS_U16(ds, IN_SHIFT_X)), IN_CENTRE_X, &x, &low_high))
            at = 0x0603;
        DS_U16(ds, IN_FIRST_X) = DS_U16(ds, DS_PEN_X) = x;
        if (project(ds, DS_U16(ds, (uint16_t)(point + 2)), IN_CENTRE_Y, &y, &low_high))
            at = 0x0603;
        DS_U16(ds, IN_FIRST_Y) = DS_U16(ds, DS_PEN_Y) = y;
        do { /* LOOP */
            point = (uint16_t)(IN_POINTS + DS_U16(ds, at) * 4);
            at = (uint16_t)(at + 2);
            if (project(ds, (uint16_t)(DS_U16(ds, point) + DS_U16(ds, IN_SHIFT_X)), IN_CENTRE_X, &x, &low_high))
                at = 0x0603;
            if (project(ds, DS_U16(ds, (uint16_t)(point + 2)), IN_CENTRE_Y, &y, &low_high)) {
                at = 0x0603;
                x = (uint16_t)((x & 0xFF00) | (uint8_t)(x - low_high)); /* x was in BX: SUB BL,DH */
            }
            clipped_line(ds, g->planes, x, y);
        } while (--n);
        clipped_line(ds, g->planes, DS_U16(ds, IN_FIRST_X), DS_U16(ds, IN_FIRST_Y));
    } while (--lines);
}

/* orig 57C5:0236   one frame of the logo: the two halves slide towards each other, then the
 * whole logo zooms */
static void logo_step(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_I16(ds, IN_LEFT_SHIFT) > DS_I16(ds, IN_RIGHT_SHIFT)) {
        DS_U16(ds, IN_SHIFT_X) = DS_U16(ds, IN_LEFT_SHIFT);
        draw_logo(g);
        DS_U16(ds, IN_LEFT_SHIFT) = (uint16_t)(DS_U16(ds, IN_LEFT_SHIFT) - 2);
        DS_U16(ds, IN_SHIFT_X) = DS_U16(ds, IN_RIGHT_SHIFT);
        draw_logo(g);
        DS_U16(ds, IN_RIGHT_SHIFT) = (uint16_t)(DS_U16(ds, IN_RIGHT_SHIFT) + 2);
        return;
    }
    DS_U8(ds, IN_PERSPECTIVE) = 1;
    DS_U16(ds, IN_DIVISOR) = (uint16_t)(DS_U16(ds, IN_DIVISOR) + DS_U16(ds, IN_ZOOM_STEP));
    DS_U16(ds, IN_SHIFT_X) = 0xF764;
    DS_U16(ds, IN_LEFT_SHIFT) = 0xF500;
    DS_U16(ds, IN_RIGHT_SHIFT) = 0xF501;
    draw_logo(g);
}

/* orig 57C5:01BF */
static int present(Game *g, const MapResources *host)
{
    DS_U16(g->ds, DS_SCREEN_STRIDE) = 0x50;
    DS_U16(g->ds, 0x1228) = 0x50;
    return scene_present(g, host);
}

/* one frame with the text: the logo, the buffer in white, show, clear; 1 when a key ended
 * the screen (57C5:01D1 checks the low byte of the key count) */
static int frame(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    logo_step(g);
    uint16_t rows = (uint16_t)(DS_U16(ds, TX_Y) + 13);
    if (rows > 0x34)
        rows = 0x34;
    buffer_to_screen(g, 0x0F, 0x1C2A, rows, 0x32);
    if (present(g, host) < 0)
        return -1;
    clear_area(g);
    if (DS_U8(ds, DS_KEYBUF_COUNT)) {
        map_clear_key_buffer(ds);
        return 1;
    }
    return 0;
}

/* orig 57C5:00F7   type one page of the text, a frame every second character. 0 at the end
 * of the page (a NUL), 1 at the end of the text (FF), 2 when a key ended the screen. */
static int type_page(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, IN_LINE) = 0;
    DS_U16(ds, TX_Y) = 0;
    DS_U16(ds, TX_X) = 0x12;
    DS_U8(ds, IN_PAGE_START) = 1;
    for (;;) {
        int start = DS_U8(ds, IN_PAGE_START) != 0;
        if (!start)
            start = ++DS_U16(ds, IN_CHAR) == 1;
        uint16_t at = (uint16_t)(IN_TEXT + DS_U16(ds, IN_CHAR));
        if (start) { /* 0120 */
            if (DS_U8(ds, (uint16_t)(at - 2)) == 0xFF || DS_U8(ds, (uint16_t)(at - 1)) == 0xFF)
                return 1;
            DS_U8(ds, IN_PAGE_START) = 0;
            cursor(g, DS_U8(ds, IN_LINE), 0xFFFF);
        } else {
            uint8_t ch = DS_U8(ds, (uint16_t)(at - 2));
            if (!ch)
                return 0;
            if (ch == 0xFF)
                return 1;
            if (ch == 0x0A) {
                cursor(g, DS_U8(ds, IN_LINE), 0);
                DS_U8(ds, IN_LINE)++;
                cursor(g, DS_U8(ds, IN_LINE), 0xFFFF);
                DS_U16(ds, TX_Y) = (uint16_t)(DS_U16(ds, TX_Y) + 0x0D);
                DS_U16(ds, TX_X) = 0x12;
            } else {
                buffer_char(g, ch);
                if (DS_U8(ds, IN_ODD_CHAR) ^= 1)
                    continue;
            }
        }
        int status = frame(g, host);
        if (status)
            return status < 0 ? -1 : 2;
    }
}

/* orig 57C5:000E   entry_sp: the stack pointer on entry, which the original keeps in DS:DE2E
 * to return straight from a key */
int intro_screen(Game *g, uint16_t entry_sp, const MapResources *resources, const ImageIO *images)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0xDE2E) = entry_sp;
    if (font_load(g, images, 0x7A49) < 0)
        return -1;
    set_view_window(ds, 0);
    if (pages(g, resources, 2) < 0)
        return -1;
    font_scale(g, 0x0C0C, 0x0C0C, 0x46, DS_U16(ds, 0xADE6), DS_U16(ds, 0xADFE));
    prepare_points(ds);
    DS_U16(ds, IN_CHAR) = 0;
    clear_buffer(g, DS_U16(ds, (uint16_t)(0x1252 + (uint16_t)((DS_U16(ds, TX_Y) + 13) * 2))));
    for (;;) {
        int typed = type_page(g, resources);
        if (typed < 0)
            return -1;
        if (typed == 2)
            return 0;
        if (typed == 1)
            break;
        DS_U16(ds, IN_COUNTDOWN) = 0x1E;
        for (;;) {
            int status = frame(g, resources);
            if (status)
                return status < 0 ? -1 : 0;
            if (--DS_U16(ds, IN_COUNTDOWN)) {
                if (DS_U16(ds, IN_COUNTDOWN) < 8 && !DS_U8(ds, IN_SECOND_PAGE))
                    cursor(g, DS_U8(ds, IN_LINE), (uint16_t)((DS_U16(ds, IN_COUNTDOWN) & 1) - 1));
                continue;
            }
            if (DS_U8(ds, IN_SECOND_PAGE)) {
                DS_U8(ds, IN_SECOND_PAGE) = 0;
                break; /* the next page */
            }
            DS_U8(ds, IN_SECOND_PAGE) = 1;
            DS_U16(ds, IN_COUNTDOWN) = 0x0A;
            clear_buffer(g, 0x8C0);
        }
    }
    for (uint16_t n = 100; n; --n) { /* 00D8: the logo alone */
        logo_step(g);
        if (present(g, resources) < 0)
            return -1;
        clear_area(g);
        DS_U16(ds, IN_ZOOM_STEP)++;
    }
    set_view_window(ds, 12);
    return 0;
}

/* orig 57C5:053C   (at start-up) the text buffer is the collision segment */
void intro_set_buffer(uint8_t *ds)
{
    DS_U16(ds, IN_BUFFER) = DS_U16(ds, 0x91B2);
}
