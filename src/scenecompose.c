/* Native composition around the weapon pass in 0000:0758. */
#include "term.h"

/* 0758..07B0: retain DX for guided firing, which can write it to a record. */
int scene_draw_overlays_dx(Game *g, const HudServices *host, uint16_t *dx)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t value = scene_contact_update_dx(ds, dx ? *dx : 0);
    value = hud_draw_indicators_dx(g, value);
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, DS_HOMING) && !DS_U8(ds, DS_CAMERA_MODE) && (DS_U8(ds, actor + 14) & 1)) {
        map_draw_homing(g);
        value = 0x03CE;
    }
    value = scene_timed_effect_dx(g, value);
    int warning = DS_U8(ds, 0x00B9) && !DS_U8(ds, 0x00BA);
    if (hud_draw_optics_dx(g, host, &value) < 0 || scene_warning(g) < 0)
        return -1;
    if (warning)
        value = 0x03CE;
    if (DS_U8(ds, DS_RELOAD_COUNTDOWN)) {
        if (--DS_U8(ds, DS_RELOAD_COUNTDOWN))
            scene_overlay_replay(g);
        else
            scene_overlay_restore(g);
    }
    if (DS_U16(ds, DS_WARNING_COUNTDOWN)) {
        if (!--DS_U16(ds, DS_WARNING_COUNTDOWN))
            DS_U8(ds, DS_PLAYER_DOWN) = 4;
        else {
            scene_overlay_replay(g);
            if (!DS_U8(ds, 0x00B9)) {
                DS_U16(ds, DS_WARNING_COUNTDOWN) = 0;
                scene_overlay_restore(g);
            }
        }
    }
    if (hud_draw_system_dx(g, host, &value) < 0)
        return -1;
    if (dx)
        *dx = value;
    return 0;
}

int scene_draw_overlays(Game *g, const HudServices *host)
{
    return scene_draw_overlays_dx(g, host, NULL);
}

/* 07B3..07D0: vehicle display and numeric/compass instruments, after weapon_frame. */
int scene_draw_instruments(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    if (vehicle_hud_draw(g) < 0)
        return -1;
    hud_draw_counters(g);
    if (DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 2)
        hud_vehicle_remaining(g);
    if (!DS_U8(ds, DS_CAMERA_MODE)) {
        hud_draw_speed(g);
        hud_draw_vehicle_counter(g);
        hud_draw_compass(g);
    }
    return 0;
}

int scene_post_render(Game *g, const HudServices *host, uint16_t dx)
{
    if (DS_U8(g->ds, DS_LINK_GAME) || scene_draw_overlays_dx(g, host, &dx) < 0 || weapon_frame(g, dx) < 0)
        return -1;
    return scene_draw_instruments(g);
}
