/* Single-player A07B weapon/damage path. Optional serial mode is not yet translated. */
#include "term.h"

int weapon_scan_damage(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    DS_U8(ds, 0xB69F) = 200;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, 0xB65E) = DS_U16(ds, 0x118C) & 511;
    DS_U16(ds, 0xB660) = (DS_U16(ds, player + 6) + DS_U16(ds, player + 8) + DS_U16(ds, 0x118A)) & 511;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, player);
    DS_U16(ds, DS_PEN_Y) = DS_U16(ds, player + 2);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, player + 4);
    uint16_t weapon = 0x0570 + 6 * (uint8_t)(DS_U8(ds, DS_WEAPON) - 1);
    DS_I16(ds, 0xB66A) = (int8_t)DS_U8(ds, weapon + 5);
    weapon_visual_insert(ds, DS_U16(ds, DS_PEN_X), DS_U16(ds, DS_PEN_Y) - 2, DS_U16(ds, DS_PROBE_Z),
                         DS_U16(ds, 0xB660));
    uint16_t count = DS_U16(ds, 0xB64E);
    for (uint16_t i = 0, target = 0xB18E; i < count; ++i, target += 18) {
        DS_U16(ds, DS_POINT_X) = DS_U16(ds, DS_PEN_X);
        DS_U16(ds, 0xB664) = DS_U16(ds, DS_PEN_Y);
        DS_U16(ds, DS_POINT_Z) = DS_U16(ds, DS_PROBE_Z);
        DS_U16(ds, 0xB668) = DS_U16(ds, target + 4);
        uint16_t pitch = DS_U16(ds, 0xB65E) * 2, heading = DS_U16(ds, 0xB660) * 2;
        int16_t distance = DS_I16(ds, 0xB668);
        DS_U16(ds, 0xB664) += mul_hi(distance, DS_I16(ds, 0x4188 + pitch));
        DS_U16(ds, DS_POINT_X) += mul_hi(distance, DS_I16(ds, 0x4188 + heading));
        DS_U16(ds, DS_POINT_Z) += mul_hi(distance, DS_I16(ds, 0x4288 + heading));
        if (!hud_target_contains_sight(ds, target) || collision_line_blocker(g))
            continue;
        DS_U16(ds, 0x037C)++;
        uint16_t record = DS_U16(ds, target), damage = DS_U16(ds, 0xB66A);
        uint16_t flags = DS_U16(ds, record + 6), actor = 0;
        if (flags & 4) {
            actor = 0x053C;
            DS_U8(ds, 0x034C) = 255;
        } else if (flags & 32) {
            actor = DS_U16(ds, DS_VEHICLE);
            DS_U8(ds, 0x034B) = 255;
        }
        if (actor) {
            if (DS_U8(ds, actor + 14) & 1) {
                DS_U16(ds, actor + 26) += damage;
                if (actor == 0x0508 && !(DS_U8(ds, actor + 25) & 4) && DS_U16(ds, actor + 26) >= 100) {
                    DS_U8(ds, actor + 50) += 3;
                    DS_U8(ds, actor + 25) |= 4;
                }
            } else {
                DS_U16(ds, actor + 48) -= damage;
                if (DS_I16(ds, actor + 48) < 0) {
                    uint16_t source = DS_U16(ds, 0xDE4C);
                    DS_U16(ds, source + 10) = 30;
                    explosion_damage_native(g, source);
                }
            }
            return 0;
        }
        if (DS_U16(ds, record + 8) == DS_U16(ds, 0x9A64)) {
            DS_U16(ds, 0x0B0E) = 0;
            explosion_damage_native(g, 0xAAF2);
            return 0;
        }
        DS_U16(ds, record + 10) -= damage;
        if (DS_I16(ds, record + 10) >= 0)
            return 0;
        DS_U8(ds, 0xB512) = 255;
        DS_U16(ds, 0x0386)++;
        if (flags & 0x4000) {
            uint16_t figure = 0x0B30 + ((uint8_t)DS_U16(ds, record + 8) >> 1) * 22;
            uint8_t kind = DS_U8(ds, figure);
            uint16_t family = kind & 2 ? 0 : kind & 4 ? 4 : 7;
            figure_feedback(g, family);
            DS_U8(ds, DS_U16(ds, DS_PLAYER) + 50) += (kind & 14) ? 3 : 5;
            figure_remove_complete(g, record);
        } else {
            explosion_damage_native(g, record);
            figure_remove_complete(g, record);
            DS_U16(ds, 0x0388)++;
        }
        return 0;
    }
    return 0;
}

static void firing_cleanup(uint8_t *ds)
{
    if (DS_U8(ds, 0x1160)) {
        DS_U8(ds, 0x1160) = 0;
        DS_U8(ds, 0xAA94) = 0;
    }
}

/* 6F70: firing can request more armed figures. Preserve DX for later records. */
static void firing_alert(Game *g, uint16_t *cx, uint16_t *dx)
{
    uint8_t *ds = g->ds;
    if (random_word(ds) < 10000)
        return;
    uint16_t player = DS_U16(ds, DS_PLAYER), amount = DS_U8(ds, player + 50);
    if (amount >= 8)
        amount = 8;
    amount = (uint16_t)(amount + 2 + DS_U16(ds, DS_DIFFICULTY));
    if (!amount)
        amount++;
    *dx = figure_spawn_dx(g, amount, 0, *dx);
    *cx = 0;
}

/* 6DBA: shot resolution also entered by the charged projectile's impact path. */
void weapon_resolve_shot(Game *g, uint16_t kind, uint16_t cx, uint16_t dx)
{
    uint8_t *ds = g->ds;
    uint16_t sound = (uint16_t)(int16_t)(int8_t)DS_U8(ds, 0x80DA + kind);
    if (DS_I16(ds, DS_FIGURE_COUNT) <= DS_I16(ds, 0x119C))
        firing_alert(g, &cx, &dx);
    if (sound == 4) {
        if (!DS_U8(ds, 0x1160)) {
            DS_U8(ds, 0x80E9) = 255;
            DS_U16(ds, 0x80EC) = sound;
            event_push(EV_SOUND, sound, 255);
            DS_U8(ds, 0x80E9) = 0;
            DS_U8(ds, 0x1160) = DS_U8(ds, 0xAA94) = 255;
            DS_U8(ds, 0x80EA) = 4;
            DS_U8(ds, 0x80EB) = 1;
        }
        if (!--DS_U8(ds, 0x80EB)) {
            DS_U8(ds, 0x7A18) = 0;
            weapon_scan_damage(g);
            DS_U8(ds, 0x80EB) = 5;
        }
        return;
    }
    DS_U8(ds, 0x80EA) = 4;
    if (!DS_U8(ds, 0x0366)) {
        DS_U16(ds, 0x80EC) = sound;
        event_push(EV_SOUND, (uint8_t)sound, 0);
    }
    if (DS_U8(ds, 0x115D)) {
        uint16_t player = DS_U16(ds, DS_PLAYER), mode = 0;
        uint16_t heading = (DS_U16(ds, player + 6) + DS_U16(ds, player + 8)) & 511;
        if (DS_U8(ds, 0x0364) == 12) {
            uint16_t target = DS_U16(ds, DS_TARGET_RECORD);
            cx = DS_U16(ds, target);
            dx = DS_U16(ds, target + 4);
            if (target)
                mode = 1;
        }
        weapon_projectile_create(ds, DS_U16(ds, player), DS_U16(ds, player + 4), cx, dx, heading, mode);
    } else if (kind == 3) {
        for (unsigned i = 0; i < 3; ++i)
            DS_U16(ds, 0x8114 + i * 2) = DS_U16(ds, 0x0367 + i * 2);
        DS_U16(ds, 0x811A) = 0;
        DS_U16(ds, 0x811C) = DS_U16(ds, 0x80EE);
        DS_U16(ds, 0x811E) = 51;
        explosion_damage_native(g, 0x8114);
        DS_U16(ds, 0x036D) = 0;
    } else {
        DS_U8(ds, 0x7A18) = 0;
        weapon_scan_damage(g);
    }
    firing_cleanup(ds);
}

/* 6D49. DX is the incoming real-mode register: its otherwise unused value can
 * be stored in a projectile record. Serial mode rejects before changing memory. */
int weapon_fire(Game *g, uint16_t dx)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    if (DS_U8(ds, DS_RELOAD_COUNTDOWN))
        goto cleanup;
    if (DS_U16(ds, 0x04D0)) {
        weapon_charge_step(g);
        return 0;
    }
    uint16_t cx = DS_U16(ds, DS_WEAPON) - 1;
    uint16_t weapon = 0x0570 + (uint8_t)cx * 6;
    if (!DS_U8(ds, weapon + 3)) {
        if (DS_U16(ds, DS_PLAYER) == 0x0508 && (DS_U8(ds, KEY_DOWN(SC_TAB)) || DS_U8(ds, KEY_DOWN(SC_ENTER))))
            event_push(EV_SOUND, 13, 0);
        goto cleanup;
    }
    if (!(DS_U8(ds, KEY_DOWN(SC_TAB)) || DS_U8(ds, KEY_DOWN(SC_ENTER))))
        goto cleanup;
    if (!DS_U8(ds, 0x1160) && DS_U8(ds, 0xAA83))
        goto cleanup;
    if (!DS_U8(ds, 0x0361) && --DS_U8(ds, 0x80EA))
        goto cleanup;
    DS_U8(ds, weapon + 3)--;
    DS_U16(ds, 0x0378)++;
    uint16_t kind = (uint16_t)(int16_t)(int8_t)DS_U8(ds, weapon);
    if (kind == 3) {
        weapon_charge_step(g);
        return 0;
    }
    weapon_resolve_shot(g, kind, cx, dx);
    return 0;
cleanup:
    firing_cleanup(ds);
    return 0;
}

/* Complete 6B54: numbers, firing, autoaim and sight composition. */
int weapon_frame(Game *g, uint16_t incoming_dx)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, player + 25) & 8)
        return 0;
    uint16_t dx = (!(DS_U8(ds, player + 14) & 2) && DS_U8(ds, DS_CAMERA_MODE) != 2) ? 0x03CE : incoming_dx;
    weapon_draw_numbers(g, player);
    if (!DS_U16(ds, DS_WEAPON))
        return 0;
    if (weapon_fire(g, dx))
        return -1;
    weapon_draw_sights(g);
    return 0;
}
