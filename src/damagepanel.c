/* The damage panel ("Physical status" in the player menu; also opened by the hospital):
 * 0000:5F06 and its helpers 603E..6960, 5776:0000 and 11BC:1A84 / 1AC8 / 1B7F.
 *
 * It shows the damage of the four body parts (head, torso, arms, legs: actor bytes +11..+14,
 * their maximum +15..+18), the cost of treating the selected ones, two heart-rate traces
 * (the player, and the companion or the other actor) and a turning wireframe body with the
 * damaged parts in red. H, T, A, L select parts; Enter treats them, one point at a time,
 * while the world goes on (an opponent can interrupt); Esc leaves. A VGA installation
 * (DS:ADD0) draws it in mode 13h, otherwise in the EGA mode 0Dh pages.
 */
#include "term.h"

enum {
    DP_INTERRUPTED = 0x7BD4,   /* u8: healing was interrupted; the panel stops treating */
    DP_TRACE_STEP = 0x7BD6,    /* i16[2]: the traces' vertical step now (one per trace) */
    DP_TRACE_ADVANCE = 0x7BDA, /* i16[2]: their horizontal advance */
    DP_TRACE_PERIOD = 0x7BDE,  /* u16[2] at 7BDE (other) and 7BE0 (player): heartbeat lengths */
    DP_TRACE_EGA = 0x7BE8,     /* u16[2]: EGA trace positions */
    DP_TRACE_VGA = 0x7BEC,     /* u16[2]: VGA trace positions */
    DP_TRACE_COUNT = 0x7B8E,   /* u8[2]: frames left of the current half beat */
    DP_COST = 0x7D08,          /* u16[4]: treatment cost of each selected part (5 per point) */
    DP_TREAT = 0x7D10,         /* u16: Enter was pressed */
    DP_SELECTED = 0x7D00,      /* u16[4]: H, T, A, L toggles */
    DP_BOXES = 0x7D12,         /* u16[4]: pointers to the 16-byte selection-box records */
    DP_DIGITS = 0x7B90,        /* u8[3]: the number being drawn, one digit per byte */
    DP_FONT = 0x7C30,          /* the digit glyphs: 8 rows, 12 bytes apart */
    DP_BODY = 0x7EB6,          /* 70 points (x, y, z) of the wireframe */
    DP_BODY_2D = 0x50B2,       /* the turned points (x, y) */
    DP_BODY_LINES = 0x7D32,    /* 97 lines, two 1-based point numbers each */
    DP_BODY_X = 0x7D24,        /* screen centre of the body */
    DP_BODY_Y = 0x7D26,
    DP_ANGLE = 0x7BE4,     /* the body's turn, also shown as a number */
    DP_READOUT_1 = 0x7BE2, /* two decorative read-outs */
    DP_READOUT_2 = 0x7BE6,
    DP_FRAME = 0x7D30,          /* u16: frame count 0-63 */
    DP_HOSPITAL = 0xA87A,       /* u8: treated in the hospital (half the time) */
    DP_TEXT_IN_BATTLE = 0x0536, /* "You are unable to concentrate on healing yourself..." */
    DP_TEXT_NOT_DONE = 0x0685,  /* "Your healing was not completed. There is danger nearby..." */
};

static int vga(const uint8_t *ds)
{
    return DS_U8(ds, DS_FACILITY_SCREEN) != 0;
}

static int resource(Game *g, const DamagePanelServices *host, uint16_t op, uint16_t a)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, 0, r->user) ? -1 : 0;
}

/* The VGA panel's routines write A000:offset. Until the switch to mode 13h (the BIOS mode at
 * 0:449) the card is still in the EGA mode and those writes go to the planes, as they do in
 * the original when the panel draws its numbers before switching. */
static int mode13(const Game *g)
{
    return g->mem[0x449] == 0x13;
}

static uint8_t vga_read(Game *g, const DamagePanelServices *host, uint16_t at)
{
    if (mode13(g))
        return host->screen ? host->screen[at] : 0;
    return ega_load(g->planes, at);
}

static void vga_write(Game *g, const DamagePanelServices *host, uint16_t at, uint8_t value)
{
    if (!mode13(g))
        ega_store(g->planes, at, value);
    else if (host->screen)
        host->screen[at] = value;
}

/* 0000:5032 shows the VGA message box (11BC:2BCC) while a facility screen is up */
static int message(Game *g, const DamagePanelServices *host, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                   uint16_t height)
{
    if (vga(g->ds))
        return textbox_vga_draw(g, host->screen, text, x, y, width, height, host->text);
    return textbox_draw(g, text, x, y, width, height, host->text);
}

static int retrace(Game *g, const DamagePanelServices *host, uint8_t high)
{
    const MapPlatform *p = host->platform;
    return !p || !p->wait || p->wait(g, high, p->user) ? -1 : 0;
}

/* orig 11BC:1AC8   three digits in the VGA screen at the EGA offset di (row di / 40,
 * column di % 40 in 8-pixel steps) */
static void vga_digits(Game *g, const DamagePanelServices *host, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint8_t row = (uint8_t)(di / 0x28), column = (uint8_t)(di % 0x28); /* DIV CL */
    uint16_t at = (uint16_t)(row * 320 + column * 8);
    uint8_t colour = DS_U8(ds, DS_FILL_COLOUR);
    for (unsigned d = 0; d < 3; ++d) {
        uint16_t glyph = (uint16_t)(DP_FONT + DS_U8(ds, (uint16_t)(DP_DIGITS + d))), to = at;
        for (unsigned r = 0; r < 8; ++r) {
            uint8_t bits = DS_U8(ds, glyph);
            glyph = (uint16_t)(glyph + 12);
            for (unsigned b = 0; b < 8; ++b, bits <<= 1)
                vga_write(g, host, to++, bits & 0x80 ? colour : 0);
            to = (uint16_t)(to + 0x138);
        }
        at = (uint16_t)(at + 8);
    }
}

/* orig 0000:6710   value in three decimal digits (the lowest three) at screen offset di,
 * in DS:468C's colour on black */
static void draw_number(Game *g, const DamagePanelServices *host, uint16_t value, uint16_t di)
{
    uint8_t *ds = g->ds, *p = g->planes;
    for (int d = 2; d >= 0; --d) {
        DS_U8(ds, (uint16_t)(DP_DIGITS + d)) = (uint8_t)(value % 10);
        value /= 10;
    }
    if (vga(ds)) {
        vga_digits(g, host, di);
        return;
    }
    ega_seq_mask(p, 15);
    ega_gc(p, 1, 15);
    for (unsigned d = 0; d < 3; ++d) {
        uint16_t glyph = (uint16_t)(DP_FONT + DS_U8(ds, (uint16_t)(DP_DIGITS + d))), at = (uint16_t)(di + d);
        for (unsigned r = 0; r < 8; ++r) {
            uint8_t bits = DS_U8(ds, glyph);
            glyph = (uint16_t)(glyph + 12);
            ega_gc(p, 8, bits);
            ega_gc(p, 0, DS_U8(ds, DS_FILL_COLOUR));
            ega_store(p, at, ega_load(p, at));
            ega_gc(p, 8, (uint8_t)~bits);
            ega_gc(p, 0, 0);
            ega_store(p, at, ega_load(p, at));
            at = (uint16_t)(at + 0x28);
        }
    }
    ega_gc(p, 8, 0xFF);
    ega_gc(p, 1, 0);
}

/* orig 0000:6321   the health of the actor at DS:actor in 117ths: (max - damage) * 117 / max */
static uint16_t health(uint8_t *ds, uint16_t actor)
{
    uint16_t max = DS_U16(ds, (uint16_t)(actor + 0x1C));
    uint32_t product = (uint32_t)(uint16_t)(max - DS_U16(ds, (uint16_t)(actor + 0x1A))) * 0x75;
    return max ? (uint16_t)(product / max) : 0;
}

/* orig 0000:6274 */
static void init_traces(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, DP_TRACE_STEP) = DS_U16(ds, DP_TRACE_STEP + 2) = 0;
    uint16_t advance = vga(ds) ? 0xFEC0 : 0xFFD8; /* one row up */
    DS_U16(ds, DP_TRACE_ADVANCE) = DS_U16(ds, DP_TRACE_ADVANCE + 2) = advance;
    DS_U16(ds, DP_TRACE_EGA) = 0x14CA;
    DS_U16(ds, DP_TRACE_EGA + 2) = 0x14CB;
    DS_U16(ds, DP_TRACE_VGA) = 0xA654;
    DS_U16(ds, DP_TRACE_VGA + 2) = 0xA65B;
    uint16_t value = health(ds, 0x0508);
    DS_U16(ds, DP_TRACE_PERIOD + 2) = value;
    DS_U8(ds, DP_TRACE_COUNT) = (uint8_t)value;
    value = health(ds, DS_U8(ds, 0x1152) ? 0x053C : 0x04D4);
    DS_U16(ds, DP_TRACE_PERIOD) = value;
    DS_U8(ds, DP_TRACE_COUNT + 1) = (uint8_t)value;
}

/* orig 0000:6564   the four costs */
static void draw_costs(Game *g, const DamagePanelServices *host)
{
    uint16_t at = 0x0889;
    for (unsigned i = 0; i < 4; ++i, at = (uint16_t)(at + 0x168))
        draw_number(g, host, DS_U16(g->ds, (uint16_t)(DP_COST + 2 * i)), at);
}

/* orig 0000:657E   the total cost and the total damage; the column is copied to page 2 */
static void draw_totals(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_FILL_COLOUR) = 11;
    uint16_t cost = 0;
    for (unsigned i = 0; i < 4; ++i)
        cost = (uint16_t)(cost + DS_U16(ds, (uint16_t)(DP_COST + 2 * i)));
    draw_number(g, host, cost, 0x0E29);
    DS_U8(ds, DS_FILL_COLOUR) = 12;
    uint16_t player = DS_U16(ds, DS_PLAYER), damage = 0;
    for (unsigned i = 0; i < 4; ++i)
        damage = (uint16_t)(damage + DS_U8(ds, (uint16_t)(player + 0x11 + i)));
    draw_number(g, host, damage, 0x0F91);
    screen_copy_rect(g, 0x0889, 0x4889, 3, 0x36);
}

/* orig 0000:652A   each part's damage and what is left of it */
static void draw_parts(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_FILL_COLOUR) = 15;
    uint16_t part = (uint16_t)(DS_U16(ds, DS_PLAYER) + 0x11);
    for (unsigned i = 0; i < 4; ++i, ++part) {
        uint16_t at = DS_U16(ds, (uint16_t)(0x7D1C + 2 * i));
        uint8_t damage = DS_U8(ds, part);
        draw_number(g, host, damage, at);
        draw_number(g, host, (uint16_t)(DS_U8(ds, (uint16_t)(part + 4)) - damage), (uint16_t)(at + 0x168));
    }
}

/* orig 0000:6209   the cost of part i: 5 per point of damage */
static void part_cost(uint8_t *ds, uint16_t part)
{
    uint8_t damage = DS_U8(ds, (uint16_t)(DS_U16(ds, DS_PLAYER) + 0x11 + part));
    DS_U16(ds, (uint16_t)(DP_COST + 2 * part)) = (uint16_t)(5 * damage);
}

/* orig 0000:61C2   take a selection box away: restore it from page 1 on pages 0 and 2, and
 * the part's cost goes to 0 */
static void box_clear(Game *g, const DamagePanelServices *host, uint16_t box)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, (uint16_t)(box + 8)) = 0;
    uint16_t width = DS_U16(ds, (uint16_t)(box + 0x0C)), at = DS_U16(ds, (uint16_t)(box + 0x0A));
    screen_copy_rect(g, (uint16_t)(at + 0x2000), at, width, 0x0D);
    screen_copy_rect(g, (uint16_t)(at + 0x2000), (uint16_t)(at + 0x4000), width, 0x0D);
    DS_U16(ds, (uint16_t)(DP_COST + 2 * DS_U16(ds, (uint16_t)(box + 0x0E)))) = 0;
    draw_costs(g, host);
    draw_totals(g, host);
}

/* orig 0000:603E   all five boxes away (the fifth is the treat button: its index clears
 * DS:7D10), no part selected */
static void boxes_clear(Game *g, const DamagePanelServices *host)
{
    for (uint16_t box = 0x7C98; box <= 0x7CD8; box = (uint16_t)(box + 0x10))
        box_clear(g, host, box);
    for (unsigned i = 0; i < 4; ++i)
        DS_U16(g->ds, (uint16_t)(DP_SELECTED + 2 * i)) = 0;
}

/* orig 5776:0000   clear plane 3 in the rectangle x0..x1 (pixels), rows y0..y1, at page
 * offset base: the EGA selection box (plane 3 holds its colour) */
static void ega_box(Game *g, uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1, uint16_t base)
{
    uint8_t *ds = g->ds, *p = g->planes;
    uint16_t rows = (uint16_t)(y1 - y0 + 1);
    uint16_t at = (uint16_t)(DS_U16(ds, (uint16_t)(0x1252 + 2 * y0)) + base + (x0 >> 3));
    ega_seq_mask(p, 8);
    ega_gc(p, 1, 1);
    ega_gc(p, 0, 1);
    ega_gc(p, 8, (uint8_t)(0xFF >> (x0 & 7)));
    for (uint16_t r = 0, to = at; r < rows; ++r, to = (uint16_t)(to + 0x28))
        ega_store(p, to, (uint8_t)(ega_load(p, to) & 0));
    ega_gc_data(p, 0xFF);
    uint16_t first = (uint16_t)((x0 + 7) & 0xFFF8), last = (uint16_t)(x1 & 0xFFF8);
    at = (uint16_t)(at + 1);
    if (last != first) {
        uint16_t bytes = (uint16_t)((uint16_t)(last - first) >> 3);
        for (uint16_t r = 0, to = at; r < rows; ++r, to = (uint16_t)(to + 0x28))
            for (uint16_t b = 0; b < bytes; ++b)
                ega_store(p, (uint16_t)(to + b), 0);
        at = (uint16_t)(at + bytes);
    }
    ega_gc_data(p, (uint8_t)(0xFF00u >> (x1 & 7)));
    for (uint16_t r = 0, to = at; r < rows; ++r, to = (uint16_t)(to + 0x28))
        ega_store(p, to, (uint8_t)(ega_load(p, to) & 0));
    ega_gc_data(p, 0xFF);
    /* MOV AX,1 / OUT DX,AX with DX still at 3CF: the bit mask becomes 1 (3D0 takes the 0),
     * and the set/reset enable stays 1 */
    ega_gc_data(p, 0x01);
    ega_seq_mask(p, 15);
}

/* orig 0000:6176   toggle part i's box (EGA) */
static void box_toggle(Game *g, const DamagePanelServices *host, uint16_t part)
{
    uint8_t *ds = g->ds;
    uint16_t box = DS_U16(ds, (uint16_t)(DP_BOXES + 2 * part));
    if (DS_U16(ds, (uint16_t)(box + 8))) {
        box_clear(g, host, box);
        return;
    }
    DS_U16(ds, (uint16_t)(box + 8)) = 0xFFFF;
    uint16_t x0 = DS_U16(ds, box), y0 = DS_U16(ds, (uint16_t)(box + 2));
    uint16_t x1 = (uint16_t)(DS_U16(ds, (uint16_t)(box + 4)) + 1), y1 = DS_U16(ds, (uint16_t)(box + 6));
    ega_box(g, x0, y0, x1, y1, 0);
    ega_box(g, x0, y0, x1, y1, 0x4000);
    part_cost(ds, DS_U16(ds, (uint16_t)(box + 0x0E)));
    draw_costs(g, host);
    draw_totals(g, host);
}

/* orig 11BC:1A84   VGA: part i's box on (set bit 7 of its pixels) or off (clear it) */
static void vga_box(Game *g, const DamagePanelServices *host, uint16_t part, int on)
{
    uint8_t *ds = g->ds;
    uint16_t record = (uint16_t)(0x7CE8 + 3 * part), at = DS_U16(ds, record);
    uint16_t width = DS_U16(ds, (uint16_t)(record + 2)), rows = DS_U16(ds, (uint16_t)(record + 4));
    for (uint16_t r = 0; r < rows; ++r, at = (uint16_t)(at + 0x140))
        for (uint16_t x = 0; x < width; ++x) {
            uint16_t to = (uint16_t)(at + x);
            uint8_t value = vga_read(g, host, to);
            vga_write(g, host, to, on ? (uint8_t)(value | 0x80) : (uint8_t)(value & 0x7F));
        }
}

/* orig 0000:621D (EGA) / 11BC:1B7F (VGA)   one step of heart-rate trace i (0 or 2) */
static void trace_step(Game *g, const DamagePanelServices *host, uint16_t i)
{
    uint8_t *ds = g->ds;
    uint8_t colour = DS_U16(ds, (uint16_t)(DP_TRACE_STEP + i)) ? 0 : DS_U8(ds, DS_FILL_COLOUR);
    if (vga(ds)) {
        uint16_t at = (uint16_t)(DS_U16(ds, (uint16_t)(DP_TRACE_VGA + i)) + DS_U16(ds, (uint16_t)(DP_TRACE_STEP + i)));
        vga_write(g, host, i ? (uint16_t)(at - 2) : at, colour);
        DS_U16(ds, (uint16_t)(DP_TRACE_VGA + i)) = (uint16_t)(at + DS_U16(ds, (uint16_t)(DP_TRACE_ADVANCE + i)));
        return;
    }
    uint8_t *p = g->planes;
    uint16_t at = (uint16_t)(DS_U16(ds, (uint16_t)(DP_TRACE_EGA + i)) + DS_U16(ds, (uint16_t)(DP_TRACE_STEP + i)));
    ega_gc(p, 0, colour);
    ega_gc(p, 1, 15);
    uint8_t mask = i ? 0x60 : 0x18;
    ega_gc(p, 8, mask);
    ega_store(p, at, (uint8_t)(ega_load(p, at) | mask));
    DS_U16(ds, (uint16_t)(DP_TRACE_EGA + i)) = (uint16_t)(at + DS_U16(ds, (uint16_t)(DP_TRACE_ADVANCE + i)));
    ega_gc(p, 8, 0xFF);
    ega_gc(p, 1, 0);
}

/* orig 0000:6330   both traces; at the end of each half beat the trace turns around */
static void traces(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    static const uint8_t colours[2] = {12, 14};
    static const uint16_t periods[2] = {DP_TRACE_PERIOD + 2, DP_TRACE_PERIOD};
    for (uint16_t t = 0; t < 2; ++t) {
        uint16_t i = (uint16_t)(2 * t);
        DS_U8(ds, DS_FILL_COLOUR) = colours[t];
        if (!--DS_U8(ds, (uint16_t)(DP_TRACE_COUNT + t))) {
            DS_U8(ds, (uint16_t)(DP_TRACE_COUNT + t)) = DS_U8(ds, periods[t]);
            uint16_t step = DS_U16(ds, (uint16_t)(DP_TRACE_STEP + i));
            uint16_t advance = DS_U16(ds, (uint16_t)(DP_TRACE_ADVANCE + i));
            DS_U16(ds, (uint16_t)(DP_TRACE_STEP + i)) = (uint16_t)-advance;
            DS_U16(ds, (uint16_t)(DP_TRACE_ADVANCE + i)) = (uint16_t)-step;
        }
        trace_step(g, host, i);
    }
}

/* orig 0000:62E6   the traces' beat follows the health again after healing */
static void retime_traces(uint8_t *ds)
{
    static const uint16_t actors[2] = {0x0508, 0x04D4};
    for (uint16_t t = 0; t < 2; ++t) {
        uint16_t period = t ? DP_TRACE_PERIOD : DP_TRACE_PERIOD + 2, old = DS_U16(ds, period);
        uint16_t value = health(ds, actors[t]);
        DS_U16(ds, period) = value;
        if (!DS_U16(ds, (uint16_t)(DP_TRACE_STEP + 2 * t)))
            DS_U8(ds, (uint16_t)(DP_TRACE_COUNT + t)) =
                (uint8_t)(DS_U8(ds, (uint16_t)(DP_TRACE_COUNT + t)) + (uint8_t)(value - old));
    }
}

/* orig 0000:6849   the colour of body line n (0-96): red when its part is damaged */
static void line_colour(uint8_t *ds, uint16_t n)
{
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    uint16_t part = n < 0x0C ? 0x11 : n < 0x21 ? 0x12 : n < 0x41 ? 0x14 : 0x13;
    uint8_t colour = DS_U8(ds, (uint16_t)(actor + part)) ? 4 : 15;
    DS_U8(ds, DS_FILL_COLOUR) = colour;
    DS_U8(ds, DS_TEXT_COLOUR) = colour;
}

/* orig 0000:6793   the turning wireframe body */
static void draw_body(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t from = DP_BODY, to = DP_BODY_2D, angle = DS_U16(ds, DP_ANGLE);
    for (unsigned i = 0; i < 0x46; ++i, from = (uint16_t)(from + 6), to = (uint16_t)(to + 4)) {
        int16_t x = DS_I16(ds, from), z = DS_I16(ds, (uint16_t)(from + 4));
        rotate_xz(ds, &x, &z, angle);
        DS_U16(ds, to) = (uint16_t)x;
        DS_U16(ds, (uint16_t)(to + 2)) = DS_U16(ds, (uint16_t)(from + 2));
    }
    DS_U16(ds, DP_FRAME) = (uint16_t)((DS_U16(ds, DP_FRAME) + 1) & 0x3F);
    uint16_t value = DS_U16(ds, (uint16_t)(DP_BODY_2D + 4 * DS_U16(ds, DP_FRAME)));
    DS_U16(ds, DP_READOUT_1) = value;
    if (value & 1)
        DS_U16(ds, DP_READOUT_2) = DS_U16(ds, DP_BODY_2D);
    uint16_t line = DP_BODY_LINES;
    for (uint16_t n = 0; n < 0x61; ++n, line = (uint16_t)(line + 4)) {
        line_colour(ds, n);
        uint16_t a = (uint16_t)(DP_BODY_2D + 4 * (uint16_t)(DS_U16(ds, line) - 1));
        uint16_t b = (uint16_t)(DP_BODY_2D + 4 * (uint16_t)(DS_U16(ds, (uint16_t)(line + 2)) - 1));
        DS_U16(ds, DS_PEN_X) = (uint16_t)((DS_I16(ds, a) >> 1) + DS_U16(ds, DP_BODY_X));
        DS_U16(ds, DS_PEN_Y) = (uint16_t)((DS_I16(ds, (uint16_t)(a + 2)) >> 1) + DS_U16(ds, DP_BODY_Y));
        uint16_t x = (uint16_t)((DS_I16(ds, b) >> 1) + DS_U16(ds, DP_BODY_X));
        uint16_t y = (uint16_t)((DS_I16(ds, (uint16_t)(b + 2)) >> 1) + DS_U16(ds, DP_BODY_Y));
        if (vga(ds)) {
            if (host->screen)
                screen_vga_line_to(ds, host->screen, x, y);
        } else
            line_to(ds, g->planes, x, y);
    }
}

/* orig 0000:66CA   decorative read-outs: pointer position, two body values and the turn,
 * which advances 4 per frame */
static void draw_readouts(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    uint8_t colour = DS_U8(ds, DS_FILL_COLOUR);
    DS_U8(ds, DS_FILL_COLOUR) = 7;
    draw_number(g, host, DS_U16(ds, DS_POINTER_X), 0x1329);
    draw_number(g, host, DS_U16(ds, DS_POINTER_Y), 0x1491);
    draw_number(g, host, DS_U16(ds, DP_READOUT_1), 0x0220);
    draw_number(g, host, DS_U16(ds, DP_ANGLE), 0x0388);
    draw_number(g, host, DS_U16(ds, DP_READOUT_2), 0x04F0);
    DS_U16(ds, DP_ANGLE) = (uint16_t)((DS_U16(ds, DP_ANGLE) + 4) & 0x1FF);
    DS_U8(ds, DS_FILL_COLOUR) = colour;
}

/* orig 0000:6085   one frame of animation */
static int animate(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    if (vga(ds)) {
        DS_U8(ds, 0xAE04)++;
        if (retrace(g, host, 0) < 0 || retrace(g, host, 1) < 0)
            return -1;
        if (host->screen)
            scene_vga_overlay_restore(g, host->screen);
        draw_body(g, host);
        draw_readouts(g, host);
        traces(g, host);
        DS_U8(ds, DS_FILL_COLOUR) = 14;
        return 0;
    }
    draw_readouts(g, host);
    traces(g, host);
    DS_U16(ds, DS_DRAW_PAGE) = 0x6000;
    DS_U8(ds, DS_FILL_COLOUR) = 15;
    screen_copy_rect(g, 0x43C4, 0x63C4, 0x0D, 0x64);
    DS_U16(ds, DP_BODY_X) = 0x64;
    DS_U16(ds, DP_BODY_Y) = 0x46;
    draw_body(g, host);
    DS_U16(ds, DS_DRAW_PAGE) = 0;
    screen_copy_rect(g, 0x63C4, 0x03C4, 0x0D, 0x64);
    return 0;
}

/* orig 0000:6884   a typed key: Enter treats, H/T/A/L toggle head, torso, arms, legs */
static void key(Game *g, const DamagePanelServices *host, uint8_t ch)
{
    uint8_t *ds = g->ds;
    if (ch == 0x0D) {
        DS_U16(ds, DP_TREAT) = 1;
        return;
    }
    static const char parts[4] = {'H', 'T', 'A', 'L'};
    uint16_t part = 4;
    for (uint16_t i = 0; i < 4; ++i)
        if ((ch & 0xDF) == parts[i])
            part = i;
    if (part == 4)
        return;
    uint16_t on = DS_U16(ds, (uint16_t)(DP_SELECTED + 2 * part)) ^ 1;
    DS_U16(ds, (uint16_t)(DP_SELECTED + 2 * part)) = on;
    if (!vga(ds))
        box_toggle(g, host, part);
    else {
        vga_box(g, host, (uint16_t)(2 * part), (uint8_t)on);
        for (unsigned i = 0; i < 4; ++i)
            DS_U16(ds, (uint16_t)(DP_COST + 2 * i)) = 0;
        for (uint16_t i = 0; i < 4; ++i)
            if (DS_U16(ds, (uint16_t)(DP_SELECTED + 2 * i)))
                part_cost(ds, i);
    }
    draw_costs(g, host);
    draw_totals(g, host);
}

/* orig 0000:64E3   the actor's "badly hurt" bits at +19 go off for parts healed enough */
static void update_wound_bits(uint8_t *ds, uint16_t actor)
{
    uint16_t part = (uint16_t)(actor + 0x11);
    uint8_t *flags = &DS_U8(ds, (uint16_t)(actor + 0x19));
    if ((DS_U8(ds, (uint16_t)(part + 4)) >> 1) >= DS_U8(ds, part))
        *flags &= 0x7F;
    part = (uint16_t)(part + 2);
    if (DS_U8(ds, (uint16_t)(part + 4)) != DS_U8(ds, part))
        *flags &= 0xF7;
    if ((DS_U8(ds, (uint16_t)(part + 4)) >> 1) >= DS_U8(ds, part))
        *flags &= 0xBF;
    part = (uint16_t)(part + 1);
    if (DS_U8(ds, (uint16_t)(part + 4)) != DS_U8(ds, part))
        *flags &= 0xEF;
    if ((DS_U8(ds, (uint16_t)(part + 4)) >> 1) >= DS_U8(ds, part))
        *flags &= 0xDF;
}

/* orig 0000:6671   heal one point of the next selected, damaged part from part on; returns
 * that part (the next point starts there) or -1 */
static int heal_point(Game *g, const DamagePanelServices *host, uint16_t part)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER), base = (uint16_t)(player + 0x11);
    for (;;) {
        if (player == 0x04D4 && DS_U16(ds, 0x0556))
            DS_U16(ds, 0x0556)--;
        uint16_t cost = (uint16_t)(DP_COST + 2 * part);
        if (DS_U16(ds, cost) && DS_U8(ds, (uint16_t)(base + part)))
            break;
        part = (uint16_t)((part + 1) & 3);
    }
    DS_U16(ds, (uint16_t)(DP_COST + 2 * part)) = (uint16_t)(DS_U16(ds, (uint16_t)(DP_COST + 2 * part)) - 5);
    DS_U8(ds, (uint16_t)(base + part))--;
    DS_U16(ds, (uint16_t)(player + 0x1A))--;
    draw_parts(g, host);
    draw_totals(g, host);
    draw_costs(g, host);
    const MenuPlatform *menu = host->menu;
    uint16_t ticks = player == 0x04D4 ? 0x14 : 0x0A;
    return !menu || !menu->call || menu->call(g, MM_WAIT, ticks, 0, menu->user) ? -1 : (int)part;
}

/* The CX that 0000:9407 (inventory_count_required) leaves behind: unchanged when the
 * actor's required-item list (DS:AAD2 for Reese, AAE2 otherwise) is empty; otherwise what
 * its last search left, 19 less the slot the item was found in, or 0. The healing code
 * keeps using CX after the call, so its 600-tick base survives only an empty list. */
static uint16_t required_items_cx(uint8_t *ds, uint16_t cx)
{
    uint16_t at = DS_U16(ds, DS_PLAYER) == 0x04D4 ? 0xAAD2 : 0xAAE2;
    while (DS_U8(ds, at)) {
        uint8_t id = DS_U8(ds, at++);
        cx = 0x13;
        for (uint16_t item = 0x05B0; cx && DS_U8(ds, (uint16_t)(item + 2)) != id; item = (uint16_t)(item + 6))
            cx--;
    }
    return cx;
}

/* orig 0000:65D0   treat the selected parts: per point the world runs 600 ticks (300 in the
 * hospital) - in practice what inventory_count_required leaves in CX, see above - less 12
 * per required item carried and the difficulty's allowance (50 at least), then one point
 * heals. An opponent showing up stops it ("Your healing was not
 * completed"; DS:7BD4 then blocks further treatment); in the VGA panel the original then
 * applies 64E3 to SI = 1E20, the overlay-save argument left in SI, which C keeps. */
static int treat(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER), points = 0;
    for (unsigned i = 0; i < 4; ++i)
        if (DS_U16(ds, (uint16_t)(DP_COST + 2 * i)))
            points = (uint16_t)(points + DS_U8(ds, (uint16_t)(player + 0x11 + i)));
    for (uint16_t i = 0, part = 0; i < points; ++i) {
        uint16_t ticks = 0x258;
        if (DS_U8(ds, DP_HOSPITAL))
            ticks >>= 1;
        inventory_count_required(ds);
        ticks = required_items_cx(ds, ticks);
        ticks = (uint16_t)(ticks - (uint16_t)(DS_U16(ds, 0xAB02) * 12));
        ticks = (uint16_t)(ticks - DS_U16(ds, (uint16_t)(0x7D2A + 2 * DS_U16(ds, DS_DIFFICULTY))));
        if ((int16_t)ticks < 0)
            ticks = 0x32;
        uint32_t result = travel_simulate_world(g, host->travel, host->opponents, host->vehicle, (uint16_t)(ticks + 1));
        if (result == UINT32_MAX)
            return -1;
        if (result & 0x10000) {
            DS_U8(ds, DP_INTERRUPTED) = 0xFF;
            if (message(g, host, DP_TEXT_NOT_DONE, 0x0A, 8, 0x16, 7) < 0)
                return -1;
            if (vga(ds)) {
                if (host->screen)
                    scene_vga_overlay_save(g, host->screen, 0x1E20, 0x68, 0x64);
                update_wound_bits(ds, 0x1E20);
            }
            return 1;
        }
        int healed = heal_point(g, host, part);
        if (healed < 0)
            return -1;
        part = (uint16_t)healed;
    }
    if (points)
        update_wound_bits(ds, DS_U16(ds, DS_PLAYER));
    return 0;
}

/* orig 0000:5F06 */
int damage_panel(Game *g, const DamagePanelServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    DS_U8(ds, DP_INTERRUPTED) = 0;
    DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    init_traces(g);
    for (unsigned i = 0; i < 5; ++i)
        DS_U16(ds, (uint16_t)(DP_COST + 2 * i)) = 0;
    boxes_clear(g, host);
    if (resource(g, host, MS_SELECT_PAGES, 0) < 0)
        return -1;
    if (vga(ds)) {
        if (resource(g, host, MS_VIDEO_MODE, 0x13) < 0 || !host->screen
            || image_vga_load(g, host->images, 0x7BC9, host->screen, host->palette) < 0)
            return -1;
        scene_vga_overlay_save(g, host->screen, 0x1E20, 0x68, 0x64);
    } else if (image_load_screen(g, host->images, 0x7BBE) < 0)
        return -1;
    draw_parts(g, host);
    draw_costs(g, host);
    draw_totals(g, host);
    for (uint16_t page = 0x2000; page <= 0x6000; page = (uint16_t)(page + 0x2000))
        screen_copy_rect(g, 0, page, 0x28, 0xC8);
    for (;;) {
        uint16_t any = 0;
        for (unsigned i = 0; i < 4; ++i)
            any |= DS_U16(ds, (uint16_t)(DP_COST + 2 * i));
        if (any && !DS_U8(ds, DP_INTERRUPTED) && DS_U16(ds, DP_TREAT)) {
            if (DS_U8(ds, DS_IN_BATTLE)) {
                if (message(g, host, DP_TEXT_IN_BATTLE, 0x0A, 0x0A, 0x1A, 6) < 0)
                    return -1;
                break;
            }
            if (treat(g, host) < 0)
                return -1;
            DS_U16(ds, DP_TREAT) = 0; /* also after an interruption */
            retime_traces(ds);
            if (vga(ds))
                for (uint16_t part = 0; part < 8; part = (uint16_t)(part + 2))
                    vga_box(g, host, part, 0);
            else {
                boxes_clear(g, host);
                screen_copy_rect(g, 0x0889, 0x4889, 3, 0xAA);
            }
            map_clear_key_buffer(ds);
        }
        /* orig 0000:615C: a typed key, then a frame */
        uint8_t ch = keyboard_read_available(g);
        if (ch) {
            uint16_t selected = 0;
            for (unsigned i = 0; i < 4; ++i)
                selected |= DS_U16(ds, (uint16_t)(DP_COST + 2 * i));
            if (ch != 0x0D || selected)
                key(g, host, ch);
        }
        if (animate(g, host) < 0 || retrace(g, host, 1) < 0)
            return -1;
        if (DS_U8(ds, KEY_DOWN(SC_ESC)))
            break;
    }
    if (resource(g, host, MS_VIDEO_MODE, 0x0D) < 0)
        return -1;
    DS_U8(ds, DS_FACILITY_SCREEN) = 0;
    return camera_reset(g, host->resources, host->images);
    /* 151B:032B does nothing outside a link game */
}
