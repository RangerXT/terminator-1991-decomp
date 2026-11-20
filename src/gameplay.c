#include "term.h"

int gameplay_update_controls_dx(Game *g, const GameplayServices *host, uint16_t shop_entry_sp, uint32_t *dx)
{
    uint8_t *ds = g->ds;
    if (!host || DS_U8(ds, DS_LINK_GAME) || DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    const VehicleServices *vehicle = host->vehicle;
    const ImageIO *files = vehicle ? vehicle->images : NULL;
    const MapResources *display = vehicle ? vehicle->display : NULL;
    if (gameplay_update_opening(g, host->text, host->keys) < 0
        || gameplay_check_losses(g, host->movie, host->sound) < 0)
        return -1;
    player_recover_pose(ds);
    player_look_keys(ds);
    if (weapon_hotkeys(g, DS_U16(ds, DS_PLAYER), host->hud) < 0)
        return -1;
    player_companion_indicator(g);
    if (!DS_U8(ds, DS_RELOAD_COUNTDOWN)) {
        if (vehicle_interaction_native(g, vehicle) < 0 || shop_interaction_native(g, host->shop, shop_entry_sp) < 0
            || pickup_interaction_native(g, host->menu, files) < 0)
            return -1;
    }
    if (DS_U8(ds, DS_JOYSTICK)) {
        uint16_t horizontal, vertical;
        uint8_t released;
        if (!host->joystick || host->joystick(&horizontal, &vertical, &released, host->joystick_user))
            return -1;
        joystick_apply(ds, horizontal, vertical, released);
    }
    if (camera_key_step(g, display, files) < 0 || world_step(g, host->world, vehicle) < 0
        || player_control_step_dx(g, vehicle, host->stream, dx) < 0)
        return -1;
    weapon_collect_targets(ds);
    if (dx && DS_U8(ds, 0x115D) && DS_U16(ds, 0x1194)) {
        uint16_t last = 0x041A + 4 * (DS_U16(ds, 0x1194) - 1);
        *dx = DS_U16(ds, DS_U16(ds, last + 2) + 4);
    }
    return 0;
}

int gameplay_update_controls(Game *g, const GameplayServices *host, uint16_t shop_entry_sp)
{
    return gameplay_update_controls_dx(g, host, shop_entry_sp, NULL);
}

int gameplay_update_projectiles(Game *g, uint16_t incoming_dx)
{
    if (DS_U8(g->ds, DS_LINK_GAME))
        return -1;
    uint16_t dx = weapon_visual_step_dx(g->ds, incoming_dx);
    return weapon_charge_projectile_step(g, 0, dx);
}
