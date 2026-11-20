/* Weapon hotkeys/reloading (11BC:1D03..1E94), with native UI and inventory. */
#include "term.h"

int weapon_refresh_selection(Game *g, const HudServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t record = 0x570 + 6 * (uint8_t)(DS_U16(ds, DS_WEAPON) - 1);
    uint8_t flags = DS_U8(ds, record + 1);
    DS_U8(ds, 0x1150) = flags & 1;
    DS_U8(ds, 0x0366) = flags & 2;
    return hud_init_optics(g, host);
}

int weapon_deselect_slot(Game *g, uint16_t slot, const HudServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_WEAPON_SLOT) == slot)
        DS_U16(ds, DS_WEAPON_SLOT) = 0;
    if (DS_U16(ds, DS_WEAPON) == slot) {
        uint16_t other = DS_U16(ds, DS_WEAPON_SLOT);
        if (other) {
            DS_U16(ds, DS_WEAPON) = other;
            DS_U16(ds, DS_WEAPON_SLOT) = 0;
            if (weapon_refresh_selection(g, host) < 0)
                return -1;
            hud_weapon_selection(g, other, 12);
        } else
            DS_U16(ds, DS_WEAPON) = 0;
    }
    if (weapon_refresh_selection(g, host) < 0)
        return -1;
    hud_weapon_selection(g, slot, 9);
    return 0;
}

/* AL can become the main DS segment byte after recolouring the old primary. */
int weapon_select_slot(Game *g, uint16_t actor, uint16_t slot, uint8_t al, const HudServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t other = DS_U16(ds, DS_WEAPON_SLOT), primary = DS_U16(ds, DS_WEAPON);
    if (other && other != slot && primary != slot)
        hud_weapon_selection(g, other, 9);
    if (primary && primary != slot) {
        DS_U16(ds, DS_WEAPON_SLOT) = primary;
        hud_weapon_selection(g, primary, 14);
        al = DS_U8(ds, DS_CAMERA_MODE) == 2 ? 0 : (uint8_t)g->ds_seg;
    }
    DS_U16(ds, DS_WEAPON) = slot;
    DS_U8(ds, actor + 16) = al;
    if (weapon_refresh_selection(g, host) < 0)
        return -1;
    hud_weapon_selection(g, slot, 12);
    return 0;
}

static int reload(Game *g, uint16_t slot, uint16_t *si)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_WARNING_COUNTDOWN))
        return 0;
    uint16_t record = 0x570 + 6 * (uint8_t)(slot - 1);
    uint16_t kind = DS_U8(ds, 0x80AF + DS_U8(ds, record));
    if (!DS_U8(ds, 0x1138 + kind))
        return 0;
    *si = inventory_remove_state(ds, DS_U8(ds, 0x80E2 + kind), *si);
    DS_U8(ds, 0x1138 + kind)--;
    DS_U8(ds, record + 3) = DS_U8(ds, record + 4);
    if (DS_U8(ds, DS_RELOAD_COUNTDOWN)) {
        DS_U8(ds, DS_RELOAD_COUNTDOWN) += 20;
        return 0;
    }
    DS_U8(ds, DS_RELOAD_COUNTDOWN) = 20;
    uint16_t a = DS_U16(ds, DS_PAGE_SHOWN);
    DS_U16(ds, DS_PAGE_SHOWN) = DS_U16(ds, DS_PAGE_DRAWN);
    DS_U16(ds, DS_PAGE_DRAWN) = a;
    int status = textbox_draw_nonmodal_state(g, 0x0AD7, 20, 4, 13, 3, si);
    a = DS_U16(ds, DS_PAGE_SHOWN);
    DS_U16(ds, DS_PAGE_SHOWN) = DS_U16(ds, DS_PAGE_DRAWN);
    DS_U16(ds, DS_PAGE_DRAWN) = a;
    return status;
}

int weapon_reload_slot(Game *g, uint16_t slot)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t si = 0;
    return reload(g, slot, &si);
}

/* SI is deliberately carried between iterations: inventory compaction and the
 * reload textbox can replace it. Preserve that observable source behavior. */
int weapon_hotkeys(Game *g, uint16_t actor, const HudServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t si = actor;
    for (uint16_t slot = 8; slot; --slot) {
        uint8_t mask = 1u << (slot - 1);
        if (!DS_U8(ds, 0x5C13 + slot) || !(DS_U8(ds, si + 15) & mask))
            continue;
        if (DS_U8(ds, KEY_DOWN(SC_CTRL))) {
            if (weapon_deselect_slot(g, slot, host) < 0)
                return -1;
            DS_U8(ds, 0x115D) = 0;
        } else {
            if (!DS_U8(ds, KEY_DOWN(SC_ALT))) {
                if (weapon_select_slot(g, si, slot, mask, host) < 0)
                    return -1;
                DS_U8(ds, 0x115D) = 0;
                if (DS_U8(ds, 0x570 + 6 * (uint8_t)(slot - 1) + 3))
                    continue;
            }
            if (reload(g, slot, &si) < 0)
                return -1;
        }
    }
    return 0;
}

/* 0998: modifier-key look direction, priority up/down/right/left. */
void player_look_keys(uint8_t *ds)
{
    if (!(DS_U16(ds, DS_FRAME_COUNTER) & 1) || !DS_U8(ds, KEY_DOWN(SC_CTRL)))
        return;
    uint16_t actor = DS_U16(ds, DS_PLAYER), heading = DS_U16(ds, actor + 8);
    if (DS_U8(ds, KEY_DOWN(SC_UP)))
        heading = 0;
    else if (DS_U8(ds, KEY_DOWN(SC_DOWN)))
        heading = 256;
    else if (DS_U8(ds, KEY_DOWN(SC_RIGHT)))
        heading = (heading + 64) & 511;
    else if (DS_U8(ds, KEY_DOWN(SC_LEFT)))
        heading = (heading - 64) & 511;
    else
        return;
    DS_U8(ds, DS_FORCE_REDO) = 255;
    DS_U16(ds, actor + 8) = heading;
}
