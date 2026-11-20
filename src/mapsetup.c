/* Local-map setup, drawing and teardown. Resource/platform operations remain explicit. */
#include "term.h"

static int resource(Game *g, const MapResources *host, uint16_t op, uint16_t a, uint16_t b)
{
    return !host || !host->call || host->call(g, op, a, b, host->user) ? -1 : 0;
}

/* orig 5E1E / 5E48. Save exactly the low-byte count used by the original copy. */
static void ground_save(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t count = DS_U16(ds, DS_GROUND_COUNT);
    if (!count)
        return;
    uint16_t off = DS_U16(ds, 0xE16C), seg = DS_U16(ds, 0xE16E);
    for (unsigned i = 0; i < 12u * (uint8_t)count; ++i)
        *far_ptr(g, seg, (uint16_t)(off + i)) = DS_U8(ds, 0x2836 + i);
    for (unsigned i = 0; i < count; ++i)
        DS_U16(ds, 0x283C + 12 * i) &= 0xFFF7;
}

static void ground_restore(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t off = DS_U16(ds, 0xE16C), seg = DS_U16(ds, 0xE16E);
    for (unsigned i = 0; i < 12u * DS_U8(ds, DS_GROUND_COUNT); ++i)
        DS_U8(ds, 0x2836 + i) = *far_ptr(g, seg, (uint16_t)(off + i));
}

/* orig CE2B. Keep the original stack-restoration order: saved height becomes the
 * two zoom bytes, while the saved zoom bytes become height. This is observable in
 * actual game state; it is not corrected in a faithful translation. */
int map_setup_local(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0x5CD8) = 255;
    ground_save(g);
    uint16_t saved_zoom = DS_U8(ds, DS_ZOOM_1) | ((uint16_t)DS_U8(ds, DS_ZOOM_2) << 8);
    DS_U8(ds, DS_ZOOM_1) = DS_U8(ds, DS_ZOOM_2) = 0;
    set_view_window(ds, 18);
    uint16_t saved_height = DS_U16(ds, DS_VIEW_HEIGHT);
    DS_U16(ds, DS_VIEW_HEIGHT) = 162;
    if (resource(g, host, MS_SELECT_PAGES, 0, 0))
        return -1;
    DS_U16(ds, 0xC4AE) = 18;
    DS_U16(ds, 0x805C) = 4000;
    if (resource(g, host, MS_LOAD_IMAGE, 0x7A41, 0))
        return -1;
    DS_U16(ds, 0xC4AE) = 0;
    if (map_draw_local_scene(g))
        return -1;
    if (resource(g, host, MS_READ_FILE, 0xE1D2, 0x7BF0))
        return -1;
    DS_U8(ds, DS_FILL_COLOUR) = 4;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    int16_t x = DS_I16(ds, player), y = DS_I16(ds, player + 4);
    project_point(ds, &x, &y, 12000);
    uint16_t sx = (uint16_t)(x + DS_U16(ds, DS_VIEW_CENTRE_X) - 7);
    uint16_t sy = (uint16_t)(-y + DS_U16(ds, DS_VIEW_CENTRE_Y) - 5);
    if (screen_draw_mask16(g, sx, sy, 15, 0x7C00) < 0)
        return -1;
    if (resource(g, host, MS_READ_FILE, 0x7BB2, 0x7BF0))
        return -1;
    if (resource(g, host, MS_PALETTE, 0, 0))
        return -1;
    ground_restore(g);
    DS_U8(ds, DS_ZOOM_1) = (uint8_t)saved_height;
    DS_U8(ds, DS_ZOOM_2) = (uint8_t)(saved_height >> 8);
    DS_U16(ds, DS_VIEW_HEIGHT) = saved_zoom;
    return 0;
}

/* orig 3792: memory effects; interrupt enable/disable belongs to the platform. */
void map_clear_key_buffer(uint8_t *ds)
{
    DS_U16(ds, 0x5B6A) = DS_U16(ds, DS_KEYBUF_COUNT) = 0;
    DS_U16(ds, DS_KEYBUF_READ) = DS_U16(ds, 0x5B6C) = 0x5B70;
}

/* orig CBF8..CC43: setup, background copy and initial pointer. */
int map_begin_local(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0x7A18) = 255;
    DS_U16(ds, 0x7D28) = 0x4000;
    if (map_setup_local(g, host))
        return -1;
    screen_copy_rect(g, 0, 0x4000, DS_U16(ds, DS_SCREEN_STRIDE), 200);
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, 0xE26A) = DS_U16(ds, player + 30);
    DS_U16(ds, 0xE26C) = DS_U16(ds, player + 32);
    DS_U16(ds, 0x724C) = 304;
    DS_U16(ds, DS_POINTER_X) = 161;
    DS_U16(ds, DS_POINTER_Y) = 93;
    DS_U8(ds, DS_FILL_COLOUR) = 15;
    if (map_draw_pointer(g))
        return -1;
    map_clear_key_buffer(ds);
    return 0;
}