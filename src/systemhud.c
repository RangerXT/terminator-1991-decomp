/* Bitmap-based system HUD helpers, retaining source timer/key/code-patch effects. */
#include "term.h"

/* orig E5BD. The latch is reset on release; a fresh press toggles zoom once. */
void hud_zoom_key(uint8_t *ds)
{
    if (!DS_U8(ds, KEY_DOWN(SC_Z))) {
        DS_U8(ds, 0xE4FC) = 0;
        return;
    }
    if (DS_U8(ds, 0xE4FC))
        return;
    DS_U8(ds, 0xE4FC) = 255;
    DS_U8(ds, DS_ZOOM_1) = DS_U8(ds, DS_ZOOM_1) ? 0 : 255;
}

/* orig E638. A 12-byte blinking-bitmap record refers to a far-pointer slot at E500. */
void hud_flash_bitmap(Game *g, uint16_t record)
{
    uint8_t *ds = g->ds;
    if (!--DS_U8(ds, record)) {
        DS_U8(ds, record) = DS_U8(ds, record + 1);
        DS_U8(ds, record + 2) ^= 1;
        if (!DS_U8(ds, record + 2))
            return;
    }
    if (!DS_U8(ds, record + 2))
        return;
    uint16_t table = (uint16_t)(0xE500 + (uint16_t)(DS_U16(ds, record + 10) * 4));
    uint16_t source = DS_U16(ds, table), seg = DS_U16(ds, table + 2);
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    uint8_t colour = DS_U8(far_ptr(g, code, 0x1B41), 0);
    uint16_t stride = DS_U16(far_ptr(g, code, 0x1B42), 0);
    screen_blit_mask(g, seg, (uint16_t)(source + 16), (uint16_t)(DS_U16(ds, record + 8) + DS_U16(ds, DS_DRAW_PAGE)),
                     DS_U16(ds, record + 4), DS_U16(ds, record + 6), colour, stride);
}

/* orig E66E. Paint the 63x59 mask and, for an off-centre sight, its connecting line. */
void hud_draw_system_frame(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x1150) || DS_U8(ds, 0x1142))
        return;
    uint16_t dest = DS_U8(ds, DS_CAMERA_MODE) == 2 ? 0x0998 : 0x04E8;
    dest += DS_U16(ds, DS_DRAW_PAGE);
    uint16_t source = DS_U16(ds, 0xE524), seg = DS_U16(ds, 0xE526);
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    uint16_t stride = DS_U16(far_ptr(g, code, 0x1B42), 0);
    DS_U8(far_ptr(g, code, 0x1B41), 0) = 15;
    screen_blit_mask(g, seg, (uint16_t)(source + 16), dest, 8, 59, 15, stride);
    DS_U8(far_ptr(g, code, 0x1B41), 0) = 4;
    uint16_t y = DS_U8(ds, DS_CAMERA_MODE) == 2 ? 90 : 60;
    if (DS_U16(ds, DS_SIGHT_X) == 159 || DS_U16(ds, DS_SIGHT_Y) == y)
        return;
    DS_U16(ds, DS_FILL_COLOUR) = 4;
    DS_U16(ds, DS_PEN_X) = 159;
    DS_U16(ds, DS_PEN_Y) = y;
    line_to(ds, g->planes, DS_U16(ds, DS_SIGHT_X), DS_U16(ds, DS_SIGHT_Y));
}