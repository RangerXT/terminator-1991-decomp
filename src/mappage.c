/* The picture of the surroundings seen from above, kept ready on its own video page. */
#include "term.h"

enum {
    MP_GROUND_LIST = 0x2836,
    MP_GROUND_COUNT = 0x91D8,
    MP_CAMERA_MODE = 0x11CA,
    MP_PAGE = 0x1234,
    MP_MAP_HEIGHT = 0x59E0,    /* i16: camera height used in map view */
    MP_LISTS_REBUILT = 0x5CD8, /* u8: set when the visible-object and ground lists were rebuilt */
    MP_MAP_VIEW = 0x7AB6,
    MP_VIEW_SETS = 0x9198, /* per view: pointer to a window (4 words), centre x, centre y */
    MP_SAVE_PTR = 0xE16C,  /* far pointer to a buffer the ground list is parked in */
    MP_MAP_PAGE = 0x6000,
};

/* orig 0000:7A92   in AX = which view (6 = full-height view, 0x0C = the normal 3D view,
 * 0x12 = the map). Sets the view window and the optical centre from the table at DS:9198. */
void set_view_window(uint8_t *ds, uint16_t which)
{
    uint16_t from = DS_U16(ds, (uint16_t)(which + MP_VIEW_SETS));
    for (int i = 0; i < 8; i += 2)
        DS_U16(ds, (uint16_t)(DS_VIEW_LEFT + i)) = DS_U16(ds, (uint16_t)(from + i));
    DS_U16(ds, DS_VIEW_CENTRE_X) = DS_U16(ds, (uint16_t)(which + MP_VIEW_SETS + 2));
    DS_U16(ds, DS_VIEW_CENTRE_Y) = DS_U16(ds, (uint16_t)(which + MP_VIEW_SETS + 4));
}

/* orig 0000:7A83   back to the view that goes with the camera mode */
static void restore_view_window(uint8_t *ds)
{
    set_view_window(ds, DS_U8(ds, MP_CAMERA_MODE) == 0 ? 0x0C : 6);
}

/* orig 0000:CF33   in BP = camera height
 * Draws the ground list as seen from straight above: a rotation matrix for looking down
 * (angles 382, 0, 0), map view switched on, and the ordinary draw_object_list.
 * Returns what draw_object_list returns. */
int draw_map_view(Game *g, uint16_t height)
{
    uint8_t *ds = g->ds;
    int status = 0;
    DS_U16(ds, DS_VIEW_CENTRE_Y) = (uint16_t)(DS_U16(ds, DS_VIEW_CENTRE_Y) + 8);
    DS_U16(ds, MP_MAP_HEIGHT) = height;
    matrix_from_angles(ds, 0x17E, 0, 0);
    DS_U8(ds, MP_MAP_VIEW) = 0xFF;
    if (DS_U16(ds, MP_GROUND_COUNT) != 0) {
        DS_U8(ds, DS_GROUND_PASS) = 1;
        status = draw_object_list(g, MP_GROUND_LIST, DS_U16(ds, MP_GROUND_COUNT));
        if (status != 0)
            return status;
    }
    DS_U8(ds, DS_GROUND_PASS) = 0;
    DS_U8(ds, MP_MAP_VIEW) = 0;
    DS_U16(ds, DS_VIEW_CENTRE_Y) = (uint16_t)(DS_U16(ds, DS_VIEW_CENTRE_Y) - 8);
    return 0;
}

/* orig 0000:CE12 (with 5E1E, CEED, 5E48)
 *
 * Runs every frame, but only does anything in a frame where the lists have just been
 * rebuilt: it then redraws the map page (video offset 6000) - cleared to colour 2, then
 * the ground list in map view from a height of 12000 - so that the map is ready to show.
 * The ground list is parked in a buffer meanwhile and put back afterwards, because drawing
 * it sets the "off screen" flags in its records; those flags are cleared for the map.
 *
 * Returns 0, or the status of draw_object_list if that stopped.
 */
int map_page_update(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, MP_LISTS_REBUILT))
        return 0;
    DS_U8(ds, MP_LISTS_REBUILT) = 0;

    /* orig 0000:5E1E */
    uint16_t count = DS_U16(ds, MP_GROUND_COUNT);
    uint16_t save_off = DS_U16(ds, MP_SAVE_PTR), save_seg = DS_U16(ds, MP_SAVE_PTR + 2);
    if (count != 0) {
        uint16_t bytes = (uint16_t)(12 * (uint8_t)count);
        for (uint16_t i = 0; i < bytes; i++)
            *far_ptr(g, save_seg, (uint16_t)(save_off + i)) = DS_U8(ds, (uint16_t)(MP_GROUND_LIST + i));
        uint16_t rec = MP_GROUND_LIST;
        for (uint16_t n = count; n; n--, rec = (uint16_t)(rec + 12))
            DS_U16(ds, (uint16_t)(rec + 6)) &= 0xFFF7;
    }

    /* orig 0000:CEED */
    set_view_window(ds, 0x12);
    uint16_t saved_page = DS_U16(ds, MP_PAGE);
    DS_U16(ds, MP_PAGE) = MP_MAP_PAGE;
    ega_seq_mask(g->planes, 0x0F);
    ega_gc(g->planes, 1, 0x0F);
    ega_gc(g->planes, 0, 2);
    ega_gc(g->planes, 8, 0xFF);
    uint16_t di = MP_MAP_PAGE;
    for (uint16_t n = 0xDE8; n; n--) { /* REP STOSW of AX = FF08 */
        ega_store(g->planes, di, 0x08);
        ega_store(g->planes, (uint16_t)(di + 1), 0xFF);
        di = (uint16_t)(di + 2);
    }
    ega_gc(g->planes, 1, 0);
    int status = draw_map_view(g, 0x2EE0);
    if (status != 0)
        return status;
    DS_U16(ds, MP_PAGE) = saved_page;
    restore_view_window(ds);

    restore_view_window(ds);

    /* orig 0000:5E48 */
    uint8_t low = DS_U8(ds, MP_GROUND_COUNT);
    if (low != 0) {
        uint16_t bytes = (uint16_t)(12 * low);
        save_off = DS_U16(ds, MP_SAVE_PTR);
        save_seg = DS_U16(ds, MP_SAVE_PTR + 2);
        for (uint16_t i = 0; i < bytes; i++)
            DS_U8(ds, (uint16_t)(MP_GROUND_LIST + i)) = *far_ptr(g, save_seg, (uint16_t)(save_off + i));
    }
    return 0;
}
