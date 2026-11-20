/* Binocular/scope mask loading, initialization and the per-frame toggle. */
#include "term.h"

/* orig 766A. Host loads the file into the far buffer at DS:91C0/91C2. */
int hud_load_optics(Game *g, const HudServices *host)
{
    uint16_t file = DS_U8(g->ds, 0x1150) ? 0x8155 : 0x814B;
    if (!host || !host->call)
        return -1;
    return host->call(g, HS_LOAD_FILE, file, host->user) == UINT32_MAX ? -1 : 0;
}

/* orig 7683. The scoped mode also recentres the sight and clears its angular offsets. */
int hud_init_optics(Game *g, const HudServices *host)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x1150)) {
        DS_U8(ds, DS_ZOOM_2) = 0;
        return 0;
    }
    DS_U8(ds, DS_ZOOM_2) = 255;
    if (hud_load_optics(g, host) < 0)
        return -1;
    DS_U16(ds, DS_SIGHT_X) = (uint16_t)(DS_U16(ds, DS_VIEW_CENTRE_X) - 1);
    DS_U16(ds, DS_SIGHT_Y) = DS_U16(ds, DS_VIEW_CENTRE_Y);
    DS_U16(ds, 0x118A) = DS_U16(ds, 0x118C) = 0;
    return 0;
}

/* orig 76B4. Refresh flag and a fresh key can reload; a held key only redraws. */
int hud_draw_optics_dx(Game *g, const HudServices *host, uint16_t *dx)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x8161)) {
        if (!DS_U8(ds, KEY_DOWN(SC_B)))
            DS_U8(ds, 0x812A) = 0;
        else if (!DS_U8(ds, 0x812A)) {
            DS_U8(ds, 0x812A) = 255;
            if (!DS_U8(ds, 0xAAA0))
                return 0;
            DS_U8(ds, DS_ZOOM_2) = (uint8_t)~DS_U8(ds, DS_ZOOM_2);
            goto refresh;
        }
    } else {
    refresh:
        DS_U8(ds, 0x8161) = 0;
        if (!DS_U8(ds, DS_ZOOM_2))
            return 0;
        if (hud_load_optics(g, host) < 0)
            return -1;
        if (dx)
            *dx = DS_U16(ds, DS_LOAD_BUFFER);
    }
    if (!DS_U8(ds, DS_ZOOM_2) || (!DS_U8(ds, 0xAAA0) && !DS_U8(ds, 0x1150)))
        return 0;
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    DS_U8(far_ptr(g, code, 0x1B41), 0) = 0;
    screen_blit_mask(g, DS_U16(ds, 0x91C2), (uint16_t)(DS_U16(ds, DS_LOAD_BUFFER) + 16),
                     (uint16_t)(0x0141 + DS_U16(ds, DS_DRAW_PAGE)), 38, 102, 0, DS_U16(far_ptr(g, code, 0x1B42), 0));
    DS_U8(far_ptr(g, code, 0x1B41), 0) = 4;
    if (dx)
        *dx = 0x03CE;
    return 0;
}

int hud_draw_optics(Game *g, const HudServices *host)
{
    return hud_draw_optics_dx(g, host, NULL);
}
