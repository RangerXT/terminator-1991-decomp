/* Charged and guided projectile flight, native single-player paths. */
#include "term.h"

int weapon_charge_projectile_step(Game *g, uint16_t cx, uint16_t dx)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    if (!DS_U8(ds, 0x0373))
        return 0;
    if (!--DS_U16(ds, 0x0371)) {
        DS_U16(ds, 0x0369) = 0;
        goto impact;
    }
    uint16_t x = DS_U16(ds, 0x0367), z = DS_U16(ds, 0x036B);
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    uint16_t angle = DS_U16(ds, 0x036D) * 2;
    int16_t speed = DS_I16(ds, 0x036F);
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, 0x0367) = x + mul_hi(speed, DS_I16(ds, 0x4188 + angle));
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, 0x036B) = z + mul_hi(speed, DS_I16(ds, 0x4288 + angle));
    uint64_t state = collision_line_blocker_state(g);
    cx = state >> 16;
    dx = state >> 32;
    if (!(uint8_t)state) {
        DS_U16(ds, 0x0369) -= (int8_t)DS_U8(ds, 0x80B7 + DS_U16(ds, 0x0371));
        return 0;
    }
impact:
    DS_U8(ds, 0x0373) = 0;
    weapon_resolve_shot(g, 3, cx, dx);
    return 0;
}

/* DA96, the six-word explosion/render record for a guided projectile. */
static void projectile_record(uint8_t *ds, uint16_t source)
{
    DS_U16(ds, 0xE3D4) = DS_U16(ds, source);
    DS_U16(ds, 0xE3D6) = 30;
    DS_U16(ds, 0xE3D8) = DS_U16(ds, source + 4);
    DS_U16(ds, 0xE3DA) = 0x0800;
    DS_U16(ds, 0xE3DC) = DS_U16(ds, source + 6);
    DS_U16(ds, 0xE3DE) = 100;
}

static int guided_step(Game *g, uint16_t record, const MapResources *host)
{
    uint8_t *ds = g->ds;
    uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
    uint16_t mode = DS_U16(ds, record + 8);
    if (weapon_projectile_outside(x, z) && !mode) {
        DS_U16(ds, DS_GUIDED_COUNT)--;
        DS_U16(ds, record + 16) = 0;
        return 0;
    }
    if (mode) {
        uint16_t target_x, target_z;
        if (mode == 1) {
            uint16_t target = DS_U16(ds, record + 10);
            if (DS_U16(ds, target + 6) & 0x2000) {
                target_x = DS_U16(ds, target);
                target_z = DS_U16(ds, target + 4);
            } else {
                target_x = DS_U16(ds, record + 12);
                target_z = DS_U16(ds, record + 14);
            }
        } else {
            uint16_t player = DS_U16(ds, DS_PLAYER);
            target_x = DS_U16(ds, player);
            target_z = DS_U16(ds, player + 4);
        }
        if (approx_distance(x, z, target_x, target_z) < 300) {
            DS_U16(ds, 0x037E)++;
            goto impact;
        }
        uint16_t angle = angle_between(ds, x, z, target_x, target_z);
        uint32_t turn = weapon_projectile_turn(DS_U16(ds, record + 6), angle);
        if (turn & 0x10000)
            DS_U16(ds, record + 8) = 0;
        else
            DS_U16(ds, record + 6) = turn;
    }
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    uint16_t heading = DS_U16(ds, record + 6) * 2;
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, record) = x + mul_hi(150, DS_I16(ds, 0x4188 + heading));
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, record + 4) = z + mul_hi(100, DS_I16(ds, 0x4288 + heading));
    if (!collision_line_blocker(g))
        return 0;
impact:
    DS_U16(ds, DS_GUIDED_COUNT)--;
    DS_U16(ds, record + 16) = 0;
    projectile_record(ds, record);
    explosion_damage_native(g, 0xE3D4);
    if (DS_U8(ds, DS_CAMERA_MODE) == 1)
        return camera_reset_full_view(g, host);
    return 0;
}

/* D8D2 / D8F2. Camera 1's 7946 reset and serial 151B events remain external. */
int weapon_guided_projectiles_step_host(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME) || (DS_U8(ds, DS_CAMERA_MODE) == 1 && (!host || !host->call)))
        return -1;
    if (!DS_U16(ds, DS_GUIDED_COUNT))
        return 0;
    for (uint16_t i = 0; i < 4; ++i) {
        uint16_t record = 0x10F0 + i * 18;
        if (DS_U16(ds, record + 16) && guided_step(g, record, host))
            return -1;
    }
    return 0;
}

int weapon_guided_projectiles_step(Game *g)
{
    return weapon_guided_projectiles_step_host(g, NULL);
}
