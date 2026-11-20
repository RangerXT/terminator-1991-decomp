/* What is behind the 3D scene: flat ground colour, the scrolling horizon picture, the sun. */
#include "term.h"

enum {
    BG_PLAYER = 0x03A0,
    BG_ALT_SEG = 0x0208, /* u16: 0, or segment of another horizon picture */
    BG_ALT_OFFSET = 0x00A5,
    BG_CAMERA_MODE = 0x11CA,
    BG_PAGE = 0x1234, /* u16: offset of the page being drawn in video memory */
    BG_GROUND_COLOUR = 0x1533,
    BG_SUN_COLUMN = 0x154D,
    BG_SUN_BITMAP = 0x155E, /* 11 rows of 2 bytes: a 13-pixel disc */
    BG_OFF_HORIZON = 0x91B4,
    BG_SEG_HORIZON = 0x91B6, /* u16: segment holding HORIZON.IMG */
};

int horizon_load(Game *g, const ImageIO *files)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, BG_ALT_SEG))
        return 0;
    return file_load(g, files, 0x153F, DS_U16(ds, BG_SEG_HORIZON), DS_U16(ds, BG_OFF_HORIZON)) == UINT32_MAX ? -1 : 0;
}

/* orig 0000:159D   the part of the view below the horizon, in one colour (DS:1533):
 * 51 rows from y = 60, x = 8..311 (52 rows from y = 140 in the other camera mode). */
void draw_ground_fill(uint8_t *ds, uint8_t *planes)
{
    uint8_t colour = DS_U8(ds, BG_GROUND_COLOUR);
    uint16_t di = (uint16_t)(0x961 + DS_U16(ds, BG_PAGE));
    uint16_t rows = 0x33;
    /* this routine sets every register it depends on */
    ega_seq_mask(planes, 0x0F);
    ega_gc(planes, 8, 0xFF);
    ega_gc(planes, 1, 0x0F);
    ega_gc(planes, 3, 0);
    ega_gc(planes, 5, 0);
    ega_gc(planes, 0, colour);
    if (DS_U8(ds, BG_CAMERA_MODE) != 0) {
        di = (uint16_t)(0x15E1 + DS_U16(ds, BG_PAGE));
        rows = 0x34;
    }
    do {
        ega_store(planes, di, 0); /* STOSB, 18 x STOSW, STOSB of AX = colour:00 */
        di++;
        for (int i = 0; i < 18; i++) {
            ega_store(planes, di, 0);
            ega_store(planes, (uint16_t)(di + 1), colour);
            di = (uint16_t)(di + 2);
        }
        ega_store(planes, di, 0);
        di = (uint16_t)(di + 3);
    } while (--rows);
    ega_gc(planes, 1, 0);
}

/* orig 0000:1707   in SI = first source byte, CX = bytes per row, BP = destination column
 * Copies `count` byte columns of the 53-row horizon picture, plane by plane. The picture is
 * 64 bytes (512 pixels) wide and stored as four planes one after the other.
 * It leaves the plane mask on plane 3 alone, and writes with whatever write mode, bit mask
 * and set/reset the card was left in (draw_ground_fill has just set them suitably). */
static void horizon_strip(Game *g, uint16_t si, uint16_t count, uint16_t column)
{
    uint8_t *ds = g->ds;
    uint16_t di = (uint16_t)((DS_U8(ds, BG_CAMERA_MODE) ? 0xDC1 : 0x141) + column + DS_U16(ds, BG_PAGE));
    uint16_t seg = DS_U16(ds, BG_SEG_HORIZON);
    if (DS_U16(ds, BG_ALT_SEG) != 0) {
        si = (uint16_t)(si + DS_U16(ds, BG_ALT_OFFSET));
        seg = DS_U16(ds, BG_ALT_SEG);
    }
    for (int plane = 0; plane < 4; plane++) {
        uint16_t row_di = di;
        ega_seq_mask(g->planes, (uint8_t)(1 << plane));
        for (int row = 0; row < 0x35; row++) {
            for (uint16_t i = 0; i < count; i++)
                ega_store(g->planes, (uint16_t)(row_di + i), *far_ptr(g, seg, (uint16_t)(si + i)));
            row_di = (uint16_t)(row_di + 0x28);
            si = (uint16_t)(si + 0x40);
        }
    }
}

/* orig 0000:16BE (with 1707, 1925, 196B)
 *
 * The sky: 53 rows from y = 8, 38 bytes wide, taken from the horizon picture starting at
 * byte column (heading / 2) mod 64 and wrapping round. One byte column is 8 pixels, so the
 * picture slides 8 pixels for every 2 heading units and repeats four times round the
 * circle. In the first of those four quarters a yellow sun (colour 14, an 11-row bitmap) is
 * drawn at y = 15, at byte column 2 + 33 - (heading / 2), when that is on screen.
 */
void draw_horizon(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, BG_SUN_COLUMN) = 0;
    uint16_t ax = (uint16_t)(DS_U16(ds, (uint16_t)(DS_U16(ds, BG_PLAYER) + 6)) >> 1);
    uint8_t quarter, column;
    if (ax / 0x40 > 0xFF) { /* DIV overflow: the game's handler skips the instruction */
        quarter = (uint8_t)ax;
        column = (uint8_t)(ax >> 8);
    } else {
        quarter = (uint8_t)(ax / 0x40);
        column = (uint8_t)(ax % 0x40);
    }
    if (quarter == 0)
        DS_U8(ds, BG_SUN_COLUMN) = column;

    uint16_t first = (uint16_t)(0x40 - column);
    if (first >= 0x26) {
        horizon_strip(g, column, 0x26, 0);
    } else {
        horizon_strip(g, column, first, 0);
        horizon_strip(g, 0, (uint16_t)(0x26 - first), first);
    }

    if (DS_U8(ds, BG_SUN_COLUMN) == 0)
        return;
    int8_t at = (int8_t)(0x21 - DS_U8(ds, BG_SUN_COLUMN));
    if (at < 0 || (uint8_t)at >= 0x26)
        return;
    uint16_t di = (uint16_t)(at + 0x25A + DS_U16(ds, BG_PAGE));
    uint16_t bits = BG_SUN_BITMAP;
    ega_seq_mask(g->planes, 0x0F);
    ega_gc(g->planes, 1, 0x0F);
    ega_gc(g->planes, 0, 0x0E);
    ega_gc_select(g->planes, 8);
    for (int row = 0; row < 11; row++) {
        for (int i = 0; i < 2; i++) {
            ega_gc_data(g->planes, DS_U8(ds, (uint16_t)(bits + i)));
            ega_store(g->planes, (uint16_t)(di + i), ega_load(g->planes, (uint16_t)(di + i)));
        }
        bits = (uint16_t)(bits + 2);
        di = (uint16_t)(di + 0x28);
    }
    ega_gc_data(g->planes, 0xFF);
    ega_gc(g->planes, 1, 0);
}

/* orig 0000:06DE   the background of a frame: ground colour, then sky and sun */
void draw_background(Game *g)
{
    draw_ground_fill(g->ds, g->planes);
    draw_horizon(g);
}

/* 0B97: fill the complete viewport with colour 154C, retaining card state. */
void draw_view_fill(Game *g)
{
    uint8_t *ds = g->ds, *p = g->planes;
    uint16_t at = 0x0141 + DS_U16(ds, DS_DRAW_PAGE);
    unsigned rows = DS_U8(ds, DS_CAMERA_MODE) ? 90 : 102;
    ega_seq_mask(p, 15);
    ega_gc(p, 8, 255);
    ega_gc(p, 1, 15);
    ega_gc(p, 0, DS_U8(ds, 0x154C));
    ega_gc(p, 3, 0);
    ega_gc(p, 5, 0);
    for (unsigned row = 0; row < rows; ++row, at += 40)
        for (unsigned col = 0; col < 38; ++col)
            ega_store(p, (uint16_t)(at + col), 0);
    ega_gc(p, 1, 0);
}

/* 06C3: skip drawing while the original schedules a blank or noisy view. */
void draw_frame_background(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_SCREEN_NOISE) || (DS_U8(ds, DS_U16(ds, DS_PLAYER) + 25) & 128))
        return;
    if (DS_U8(ds, DS_CAMERA_MODE) == 2)
        draw_view_fill(g);
    draw_background(g);
}
