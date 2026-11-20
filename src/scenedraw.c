/* 06FF: rasterize a scene, or the temporary loss-of-vision display. */
#include "term.h"

/* A3D7: stable ascending order by signed depth. Preserve the game's swap slot. */
void sort_targets_by_depth(uint8_t *ds)
{
    for (int16_t pass = DS_I16(ds, 0xB64E); pass > 1; --pass) {
        uint16_t left = 0xB18E;
        for (int16_t n = 1; n < pass; ++n, left += 18) {
            uint16_t right = left + 18;
            if (DS_I16(ds, right + 4) >= DS_I16(ds, left + 4))
                continue;
            for (unsigned k = 0; k < 18; k += 2)
                DS_U16(ds, 0xB17C + k) = DS_U16(ds, left + k);
            for (unsigned k = 0; k < 18; k += 2)
                DS_U16(ds, left + k) = DS_U16(ds, right + k);
            for (unsigned k = 0; k < 18; k += 2)
                DS_U16(ds, right + k) = DS_U16(ds, 0xB17C + k);
        }
    }
}

/* 186C: use bytes of loaded code as the repeating video-noise pattern. */
static void scene_noise(Game *g)
{
    uint8_t *ds = g->ds, *p = g->planes;
    uint16_t code = g->ds_seg - 0x5C27, src = DS_U16(ds, 0x1224), at = 0x0141 + DS_U16(ds, DS_DRAW_PAGE);
    uint16_t rows = DS_U16(ds, DS_VIEW_HEIGHT);
    if (src >= 0x4000)
        src = 0;
    ega_seq_mask(p, 15);
    ega_gc(p, 0, 15);
    ega_gc(p, 1, 15);
    ega_gc_select(p, 8);
    (void)ega_load(p, 0x7FFE);
    do {
        for (unsigned col = 0; col < 38; ++col) {
            uint8_t data = *far_ptr(g, code, src++);
            ega_gc_data(p, data);
            ega_store(p, at++, data);
        }
        at += 2;
    } while (--rows);
    ega_gc_data(p, 255);
    ega_gc(p, 1, 0);
    DS_U16(ds, 0x1224) = src;
}

static int scene_obscured(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_SCREEN_NOISE))
        --DS_U16(ds, DS_SCREEN_NOISE);
    if (DS_U16(ds, DS_PLAYER) != 0x0508) {
        DS_U8(ds, 0x154C) = 0;
        draw_view_fill(g);
        DS_U8(ds, 0x154C) = 9;
    } else {
        if (!(DS_U8(ds, 0x0521) & 128) && !DS_U8(ds, 0xAA83))
            event_push(EV_SOUND, 15, DS_U8(ds, 0x80E9));
        scene_noise(g);
    }
    for (unsigned i = 0; i < 2; ++i) {
        if (host->call(g, 0x0D8D, 0, 0, host->user) || host->call(g, 0x0DAA, 0, 0, host->user))
            return -1;
    }
    return 0;
}

int draw_scene(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    if (DS_U16(ds, DS_SCREEN_NOISE) || (DS_U8(ds, DS_U16(ds, DS_PLAYER) + 25) & 128))
        return host && host->call ? scene_obscured(g, host) : -1;
    uint16_t ground = DS_U16(ds, DS_GROUND_COUNT);
    if (ground) {
        DS_U8(ds, DS_GROUND_PASS) = 1;
        int status = draw_object_list(g, 0x2836, ground);
        if (status)
            return status;
        player_sample_warning(g);
        figure_spawn_grid_block(g);
    }
    DS_U8(ds, DS_GROUND_PASS) = 0;
    uint16_t count = DS_U16(ds, DS_DRAW_COUNT);
    if (count) {
        int status = draw_object_list(g, DS_U16(ds, DS_DRAW_LIST), count);
        if (status)
            return status;
        sort_targets_by_depth(ds);
    }
    DS_U8(ds, DS_FORCE_REDO) = 0;
    return 0;
}

/* Main loop 01DC through 01EE. The overhead map and 3D view use the
 * same resident city, figures, object lists and video state throughout. */
int scene_render_city(Game *g, const VehicleServices *host)
{
    const ImageIO *files = host ? host->images : NULL;
    const MapResources *display = host ? host->display : NULL;
    if (DS_U8(g->ds, DS_LINK_GAME) || DS_U8(g->ds, DS_FACILITY_SCREEN))
        return -1;
    if (update_visible_cells(g, files) || player_pre_draw_collision(g, host))
        return -1;
    draw_frame_background(g);
    if (scene_update_world(g, display) || build_frame_draw_list(g) || map_page_update(g))
        return -1;
    return draw_scene(g, display);
}
