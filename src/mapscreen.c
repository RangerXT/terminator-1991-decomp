/* Interactive map coordinates and the small information panel. */
#include "term.h"

/* orig D2BE..D2F3: destination coordinates before position normalization and cell IO. */
void map_write_destination_position(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint32_t x = (uint32_t)DS_U16(ds, 0xE26A) * 1024 + DS_U16(ds, 0xE26E);
    uint32_t z = (uint32_t)(uint16_t)(DS_U16(ds, 0xE26C) + 1) * 1024 - DS_U16(ds, 0xE270);
    DS_U16(ds, player + 0x22) = (uint16_t)x;
    DS_U16(ds, player + 0x24) = (uint16_t)(x >> 16);
    DS_U16(ds, player + 0x2A) = (uint16_t)z;
    DS_U16(ds, player + 0x2C) = (uint16_t)(z >> 16);
}

/* orig 0000:CB4B: update the six decimal homing fields, then draw their text. */
void map_draw_homing(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!DS_U8(ds, DS_HOMING) || DS_U8(ds, DS_CAMERA_MODE) || !(DS_U8(ds, player + 14) & 1))
        return;
    map_destination_measure(ds);
    for (unsigned i = 0; i < 6; ++i)
        for (unsigned j = 0; j < 6; ++j)
            DS_U8(ds, 0xE1FD + 17 * i + j) = ' ';
    for (unsigned i = 0; i < 6; ++i) {
        uint16_t value = DS_U16(ds, 0xE26A + 2 * i);
        uint8_t digits[5];
        unsigned n = 0;
        do {
            digits[n++] = (uint8_t)('0' + value % 10);
            value /= 10;
        } while (value);
        uint16_t at = (uint16_t)(0xE1FD + 17 * i);
        while (n)
            DS_U8(ds, at++) = digits[--n];
        DS_U8(ds, at) = ' ';
    }
    map_draw_info(g, 0xE1F3);
}

/* orig 0000:CC46..CC6E. Selection priority before the retrace/escape wait.
 * Returns 'F', 'H', or zero. Zero leaves timing and Escape handling to the caller. */
uint8_t map_requested_action(uint8_t *ds)
{
    uint8_t action = 0;
    if (!DS_U8(ds, DS_LINK_GAME) && DS_U8(ds, KEY_DOWN(SC_F)))
        action = 'F';
    else if (DS_U8(ds, KEY_DOWN(SC_H)))
        action = 'H';
    DS_U8(ds, DS_MAP_ACTION) = action;
    return action;
}

/* orig 11BC:2DBB. Local-map interior and blue cell grid; incoming plane mask,
 * rotate/function register and clear bit mask are deliberately retained. */
void map_draw_grid(Game *g)
{
    uint8_t *ds = g->ds, *p = g->planes;
    ega_gc(p, 1, 15);
    ega_gc(p, 0, 0);
    for (unsigned row = 0; row < 162; ++row)
        for (unsigned col = 0; col < 38; ++col)
            ega_store(p, (uint16_t)(0x141 + row * 40 + col), 0);
    ega_gc(p, 1, 0);
    ega_gc(p, 5, 2);
    uint16_t x = 18;
    do {
        uint16_t dest = 0x142 + (x >> 3);
        ega_gc(p, 8, (uint8_t)(128 >> (x & 7)));
        for (unsigned row = 0; row < 162; ++row) {
            uint16_t at = dest + row * 40;
            ega_load(p, at);
            ega_store(p, at, 1);
        }
        x += 21;
    } while (x < DS_U16(ds, DS_VIEW_RIGHT));
    ega_gc(p, 8, 255);
    for (uint16_t dest = 0x141; dest < 0x1A90; dest += 0x348)
        for (unsigned col = 0; col < 38; ++col)
            ega_store(p, (uint16_t)(dest + col), 1);
    ega_gc(p, 5, 0);
}

/* orig 0000:164E, used by the two-by-two map markers at 445A. */
static void marker_pixel(Game *g, uint16_t x, uint16_t y)
{
    uint8_t *ds = g->ds, *p = g->planes;
    uint16_t dest = DS_U16(ds, 0x1252 + (uint16_t)(y * 2)) + (x >> 3) + DS_U16(ds, DS_DRAW_PAGE);
    ega_gc(p, 8, (uint8_t)(128 >> (x & 7)));
    ega_gc(p, 1, 15);
    ega_gc(p, 0, DS_U8(ds, DS_FILL_COLOUR));
    ega_store(p, dest, ega_load(p, dest));
    ega_gc(p, 1, 0);
    ega_gc(p, 8, 255);
}

/* orig 0000:4476, 4428 and 445A. Project world position into the local map. */
static void draw_marker(Game *g, uint16_t record)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    int16_t x = (int16_t)(DS_U16(ds, record) - DS_U16(ds, player + 30) * 1024);
    int16_t y = (int16_t)((DS_U16(ds, player + 32) + 1) * 1024 - DS_U16(ds, record + 4));
    project_point(ds, &x, &y, 12000);
    uint16_t sx = (uint16_t)(x + DS_U16(ds, DS_VIEW_CENTRE_X));
    uint16_t sy = (uint16_t)(-y + DS_U16(ds, DS_VIEW_CENTRE_Y) + 2);
    if (sx < 8 || sx >= 312 || sy < 8 || sy >= 170)
        return;
    marker_pixel(g, sx, sy);
    marker_pixel(g, sx + 1, sy);
    marker_pixel(g, sx + 1, sy + 1);
    marker_pixel(g, sx, sy + 1);
}

/* orig 0000:4418: category 4 is not drawn; the others use category + 8. */
static void draw_place_marker(Game *g, uint16_t record)
{
    uint8_t kind = DS_U8(g->ds, record + 8);
    if (kind == 4)
        return;
    DS_U8(g->ds, DS_FILL_COLOUR) = (uint8_t)(kind + 8);
    draw_marker(g, record);
}

/* orig 0000:43C6, including the four-record selection at C5AF. */
void map_draw_markers(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t record = 0x5CE4;
    for (uint16_t i = 0; i < DS_U16(ds, DS_SHOP_COUNT); ++i, record += 11)
        draw_place_marker(g, record);
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint32_t dividend = DS_U16(ds, player + 34) | ((uint32_t)DS_U16(ds, player + 36) << 16);
    uint32_t q = dividend / 65535;
    uint16_t group = q <= 65535 ? (uint16_t)q : (uint16_t)dividend;
    record = (uint16_t)(0x854E + group * 44 + (DS_U16(ds, player + 44) ? 132 : 0));
    for (unsigned i = 0; i < 4; ++i, record += 11)
        draw_place_marker(g, record);
    DS_U8(ds, DS_FILL_COLOUR) = 5;
    uint16_t segment = DS_U16(ds, 0x72B8);
    for (uint16_t i = 0; i < DS_U16(ds, DS_VEHICLE_COUNT); ++i) {
        for (unsigned j = 0; j < 8; ++j)
            DS_U8(ds, 0x724E + j) = *far_ptr(g, segment, (uint16_t)(i * 14 + j));
        draw_marker(g, 0x724E);
    }
}

/* Local-map scene after MAP.IMG has been loaded, up to the first pointer-resource load
 * at CE9B. This is the drawing/composition portion CE72..CE9B. */
int map_draw_local_scene(Game *g)
{
    map_draw_grid(g);
    DS_U16(g->ds, DS_FORCE_REDO) = 65535;
    int status = draw_map_view(g, 12000);
    if (status)
        return status;
    map_draw_markers(g);
    uint16_t player = DS_U16(g->ds, DS_PLAYER);
    map_draw_grid_labels(g, (uint16_t)(DS_U16(g->ds, player + 30) - 6), (uint16_t)(DS_U16(g->ds, player + 32) - 3));
    return 0;
}

/* orig 5776:04BC: planar screen-to-screen rectangle, using latch write mode 1.
 * Reads and writes are interleaved, retaining the original overlapping-copy behavior. */
void screen_copy_rect(Game *g, uint16_t src, uint16_t dst, uint16_t width, uint16_t rows)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return;
    ega_seq_mask(p, 15);
    ega_gc(p, 5, 1);
    ega_gc(p, 8, 255);
    unsigned count = rows ? rows : 65536;
    for (unsigned row = 0; row < count; ++row) {
        for (unsigned col = 0; col < width; ++col) {
            uint8_t value = ega_load(p, (uint16_t)(src + col));
            ega_store(p, (uint16_t)(dst + col), value);
        }
        src += DS_U16(ds, DS_SCREEN_STRIDE);
        dst += DS_U16(ds, DS_SCREEN_STRIDE);
    }
    ega_gc(p, 5, 0);
}

/* orig 0000:1492, planar branch. Two mask bytes per row, shifted by x modulo 8.
 * Returns the byte offset for subsequent background restoration; -1 is the
 * untranslated chunky-video branch. This routine does not add page_offset. */
int screen_draw_mask16(Game *g, uint16_t x, uint16_t y, uint16_t rows, uint16_t mask)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t dest = DS_U16(ds, 0x1252 + (uint16_t)(y * 2));
    if (DS_U16(ds, DS_SCREEN_STRIDE) == 80)
        dest *= 2;
    dest += x >> 3;
    uint16_t result = dest;
    unsigned shift = x & 7;
    ega_seq_mask(p, 15);
    ega_gc(p, 5, 0);
    ega_gc(p, 3, 0);
    ega_gc(p, 0, DS_U8(ds, DS_FILL_COLOUR));
    ega_gc(p, 1, 15);
    ega_gc_select(p, 8);
    unsigned count = rows ? rows : 65536;
    for (unsigned row = 0; row < count; ++row) {
        for (unsigned col = 0; col < 2; ++col) {
            uint16_t bits = DS_U8(ds, mask++);
            if (shift)
                bits = (uint16_t)((bits >> shift) | (bits << (16 - shift)));
            ega_gc_data(p, (uint8_t)bits);
            ega_load(p, (uint16_t)(dest + col));
            ega_store(p, (uint16_t)(dest + col), (uint8_t)bits);
            ega_gc_data(p, (uint8_t)(bits >> 8));
            ega_load(p, (uint16_t)(dest + col + 1));
            ega_store(p, (uint16_t)(dest + col + 1), (uint8_t)(bits >> 8));
        }
        dest += DS_U16(ds, DS_SCREEN_STRIDE);
    }
    ega_gc_data(p, 255);
    ega_gc(p, 1, 0);
    return result;
}

/* orig 0000:60FD and 6128: restore the previous pointer, then draw its mask. */
void map_restore_pointer(Game *g)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN))
        return;
    uint16_t dest = DS_U16(g->ds, 0x7C94);
    screen_copy_rect(g, (uint16_t)(dest + DS_U16(g->ds, 0x7D28)), dest, 4, 16);
}

int map_draw_pointer(Game *g)
{
    uint8_t *ds = g->ds;
    int dest = screen_draw_mask16(g, DS_U16(ds, DS_POINTER_X), DS_U16(ds, DS_POINTER_Y), DS_U16(ds, 0x7BF6), 0x7C00);
    if (dest >= 0)
        DS_U16(ds, 0x7C94) = (uint16_t)dest;
    return dest < 0 ? -1 : 0;
}

/* orig 0000:830F. The key state table supplies direction and a four-pixel modifier. */
int map_pointer_step(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t step = DS_U8(ds, KEY_DOWN(SC_RSHIFT)) ? 4 : 1;
    uint16_t x = DS_U16(ds, DS_POINTER_X), y = DS_U16(ds, DS_POINTER_Y);
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
    map_restore_pointer(g);
    return map_draw_pointer(g);
}

/* orig 0000:CC8D. Carry in the original means outside the permitted cell range.
 * A zero horizontal quotient deliberately selects the previous cell, offset 1024. */
int map_local_destination(uint8_t *ds)
{
    uint16_t x = DS_U16(ds, DS_POINTER_X) - 161;
    uint16_t y = DS_U16(ds, DS_POINTER_Y) - 93;
    DS_U16(ds, DS_POINTER_X) = x;
    DS_U16(ds, DS_POINTER_Y) = y;
    int32_t product = (int16_t)x * 49;
    int16_t q = (int16_t)(product / 1024), r = (int16_t)(product % 1024);
    uint16_t offset = r;
    if (q <= 0) {
        --q;
        offset = (uint16_t)(1024 + r);
    }
    DS_U16(ds, 0xE26A) += q;
    DS_U16(ds, 0xE26E) = offset;
    product = (int16_t)y * 49;
    q = (int16_t)(product / 1024);
    r = (int16_t)(product % 1024);
    if (q >= 0) {
        ++q;
        offset = (uint16_t)(1024 - r);
    } else
        offset = (uint16_t)-r;
    DS_U16(ds, 0xE26C) += q;
    DS_U16(ds, 0xE270) = offset;
    return DS_U16(ds, 0xE26A) < 3 || DS_U16(ds, 0xE26A) >= 190 || DS_U16(ds, 0xE26C) < 3 || DS_U16(ds, 0xE26C) >= 126;
}

/* orig 0000:CD05. Full-area map coordinates; the minimum compares are unsigned. */
void map_area_destination(uint8_t *ds)
{
    uint16_t x = DS_U16(ds, DS_POINTER_X), y = DS_U16(ds, DS_POINTER_Y);
    if (x < 8)
        DS_U16(ds, DS_POINTER_X) = x = 8;
    if (y < 8)
        DS_U16(ds, DS_POINTER_Y) = y = 8;
    uint32_t a = (uint32_t)x * 307, b = (uint32_t)y * 374;
    DS_U16(ds, 0xE26A) = (uint16_t)(a / 1024);
    DS_U16(ds, 0xE26E) = (uint16_t)(a % 1024);
    DS_U16(ds, 0xE26C) = (uint16_t)(b / 1024);
    DS_U16(ds, 0xE270) = (uint16_t)(1024 - b % 1024);
}

/* orig 0000:CBA5: distance and bearing in the map's quarter-scale coordinates. */
void map_destination_measure(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint16_t x = (uint16_t)(DS_I16(ds, player) >> 2);
    uint16_t z = (uint16_t)((DS_U16(ds, player + 32) << 8) | (DS_U16(ds, player + 32) >> 8));
    z -= (uint16_t)(DS_I16(ds, player + 4) >> 2);
    uint16_t tx = (uint16_t)(DS_I16(ds, 0xE26E) >> 2);
    uint16_t tz = (uint16_t)((DS_U16(ds, 0xE26C) << 8) | (DS_U16(ds, 0xE26C) >> 8));
    tz -= (uint16_t)(DS_I16(ds, 0xE270) >> 2);
    x = (x & 255) | ((uint16_t)(uint8_t)((x >> 8) + DS_U8(ds, player + 30)) << 8);
    tx = (tx & 255) | ((uint16_t)(uint8_t)((tx >> 8) + DS_U8(ds, 0xE26A)) << 8);
    z = (uint16_t)-z;
    tz = (uint16_t)-tz;
    DS_U16(ds, 0xE274) = heading_degrees(angle_between(ds, x, z, tx, tz));
    DS_U16(ds, 0xE272) = approx_distance(x, z, tx, tz);
}

/* orig 0000:CDE1. Clear the eight-byte-wide, 64-row information panel to colour 8. */
void map_clear_info(Game *g)
{
    uint8_t *p = g->planes;
    uint16_t dest = 0x11B7 + DS_U16(g->ds, DS_DRAW_PAGE);
    ega_seq_mask(p, 15);
    ega_gc(p, 1, 15);
    ega_gc(p, 0, 8);
    for (int row = 0; row < 64; ++row)
        for (int col = 0; col < 8; ++col)
            ega_store(p, (uint16_t)(dest + row * 40 + col), (col & 1) ? 8 : 0);
    ega_gc(p, 1, 0);
}

/* orig 0000:CD4A. NUL-separated lines, terminated by FF after the final NUL.
 * The byte offsets for each line live in the table at DS:E25C. */
void map_draw_info(Game *g, uint16_t text)
{
    map_clear_info(g);
    uint8_t *ds = g->ds;
    uint16_t table = 0xE174, start = text, count = 0;
    for (;;) {
        DS_U16(ds, table) = start;
        table += 2;
        ++count;
        while (DS_U8(ds, text++)) {
        }
        if (DS_U8(ds, text) == 255)
            break;
        start = text;
    }
    for (uint16_t i = 0; i < count; ++i)
        hud_draw_text(g, DS_U16(ds, 0xE174 + 2 * i), DS_U16(ds, 0xE25C + 2 * i));
}
