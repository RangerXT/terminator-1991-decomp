/* Camera reset 7946/7A28 for modes 0/1/2; normal HUD and resources are native. */
#include "term.h"

static int resource(Game *g, const MapResources *host, uint16_t op, uint16_t a)
{
    return host->call(g, op, a, 0, host->user) ? -1 : 0;
}

/* 0C0E/0C47: clear three play pages in the current fill colour. */
void camera_clear_pages(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
    for (unsigned i = 0; i < 3; ++i) {
        DS_U16(ds, DS_DRAW_PAGE) = i * 0x2000;
        ega_seq_mask(g->planes, 15);
        ega_gc(g->planes, 8, 255);
        ega_gc(g->planes, 1, 15);
        uint8_t colour = DS_U8(ds, 0x123B);
        ega_gc(g->planes, 0, colour);
        uint16_t at = i * 0x2000, words = DS_U16(ds, DS_SCREEN_STRIDE) == 80 ? 0x36B0 : 0x0FA0;
        for (uint32_t j = 0; j < words; ++j) {
            ega_store(g->planes, at++, 0);
            ega_store(g->planes, at++, colour);
        }
        ega_gc(g->planes, 1, 0);
    }
    DS_U16(ds, DS_DRAW_PAGE) = page;
}

/* 7989: common frame image, three-page copy and collision rebuild. */
int camera_full_image(Game *g, const MapResources *host, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    if ((!io || !io->call) && (!host || !host->call))
        return -1;
    uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
    DS_U16(ds, DS_DRAW_PAGE) = 0;
    if (io ? image_load_screen(g, io, 0x915A) : resource(g, host, MS_LOAD_IMAGE, 0x915A))
        return -1;
    screen_copy_rect(g, 0, 0x2000, 40, 200);
    screen_copy_rect(g, 0, 0x4000, 40, 200);
    DS_U16(ds, DS_DRAW_PAGE) = page;
    collision_map_build(g);
    return 0;
}

static int reset(Game *g, const MapResources *host, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    if (!host || !host->call || (!DS_U8(ds, DS_CAMERA_MODE) && (!io || !io->call)))
        return -1;
    DS_U8(ds, 0x5CE3) = DS_U8(ds, 0xC54A) = 0;
    if (resource(g, host, MS_VIDEO_MODE, 13))
        return -1;
    DS_U8(ds, 0xC4AB) = 0;
    DS_U16(ds, 0xC4C4) = 0xC4C6;
    DS_U16(ds, 0xC546) = 0;
    DS_U8(ds, 0xAE04) = 0;
    if (resource(g, host, MS_SELECT_PAGES, 2))
        return -1;
    if (resource(g, host, MS_DEFAULT_PALETTE, 0))
        return -1;
    DS_U8(ds, DS_PALETTE_RELOAD) = 255;
    camera_clear_pages(g);
    if (!DS_U8(ds, DS_CAMERA_MODE)) {
        hud_choose_panel(ds);
        if (hud_init_normal(g, io))
            return -1;
        DS_U16(ds, DS_VIEW_HEIGHT) = 103;
        DS_U16(ds, 0x11C8) = 100;
        DS_U16(ds, DS_SIGHT_Y) = 60;
        if (DS_I16(ds, DS_SIGHT_Y) < 18)
            DS_U16(ds, DS_SIGHT_Y) = 18;
        set_view_window(ds, 12);
        return 0;
    }
    if (camera_full_image(g, host, io) < 0)
        return -1;
    set_view_window(ds, 6);
    return 0;
}

int camera_reset_full_view(Game *g, const MapResources *host)
{
    if (!DS_U8(g->ds, DS_CAMERA_MODE))
        return -1;
    return reset(g, host, NULL);
}

int camera_reset(Game *g, const MapResources *host, const ImageIO *images)
{
    return reset(g, host, images);
}

/* 794A: full-height key entry, preserving its lighter platform-reset contract. */
int camera_full_height(Game *g, const MapResources *host, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    if (!host || !host->call)
        return -1;
    DS_U8(ds, DS_FORCE_REDO) = 255;
    if (resource(g, host, MS_DEFAULT_PALETTE, 0))
        return -1;
    DS_U8(ds, DS_PALETTE_RELOAD) = 255;
    camera_clear_pages(g);
    DS_U8(ds, DS_CAMERA_MODE) = 2;
    set_view_window(ds, 6);
    DS_U16(ds, DS_VIEW_HEIGHT) = 184;
    DS_U16(ds, 0x11C8) = 180;
    DS_U16(ds, DS_SIGHT_Y) = 140;
    return camera_full_image(g, host, io);
}

/* 79C3: held camera key plus modifier, with idempotent same-mode branches. */
int camera_key_step(Game *g, const MapResources *host, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, KEY_DOWN(SC_F9)))
        return 0;
    if (DS_U8(ds, KEY_DOWN(SC_RSHIFT))) {
        if (DS_U8(ds, DS_CAMERA_MODE) == 2)
            return 0;
        DS_U8(ds, DS_CAMERA_MODE) = 2;
        return camera_full_height(g, host, io);
    }
    if (!DS_U8(ds, DS_CAMERA_MODE))
        return 0;
    DS_U8(ds, DS_CAMERA_MODE) = 0;
    return camera_reset(g, host, io);
}
