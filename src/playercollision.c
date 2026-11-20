/* Player collision test, original 11BC:1FCC..21C8. */
#include "term.h"

static uint16_t grid16(uint16_t n)
{
    return (int16_t)(uint16_t)(n + 8) >> 4;
}

/* Return the original carry flag. A blocked vehicle emits sound 2; position
 * rollback and normalization run here rather than through a collision callback. */
uint8_t player_collision_test(Game *g, uint16_t actor)
{
    uint8_t *ds = g->ds;
    static const uint16_t pos[] = {34, 36, 42, 44};
    if (!DS_U8(ds, 0x8683)) {
        if (DS_I16(ds, 0x9120) < 0)
            goto remember;
        unsigned i;
        for (i = 0; i < 4; ++i)
            if (DS_U16(ds, 0x911E + 2 * i) != DS_U16(ds, actor + pos[i]))
                break;
        if (i == 4) {
            DS_U16(ds, 0x9126)++;
            return 0;
        }
    }
    DS_U16(ds, 0x9126) = 0;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, actor);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, actor + 4);
    uint16_t at = collision_grid_address(ds), seg = DS_U16(ds, DS_SEG_COLLISION), slot = 0;
    uint8_t cell = 0;
    for (unsigned i = 0; i < 9; ++i, slot += 2) {
        uint16_t candidate = at + DS_U16(ds, 0x865D + slot);
        cell = *far_ptr(g, seg, candidate);
        if (cell) {
            DS_U16(ds, DS_PEN_X) += (int8_t)DS_U8(ds, 0x866F + slot);
            DS_U16(ds, DS_PROBE_Z) += (int8_t)DS_U8(ds, 0x8670 + slot);
            break;
        }
    }
    if (!cell)
        goto remember_player;
    if (cell & 128)
        goto blocked;
    uint16_t object = (uint8_t)(cell - 1), record = 0x8B3A + object * 12;
    DS_U16(ds, 0x912E) = object;
    DS_U16(ds, DS_GRID_X) = grid16(DS_U16(ds, record));
    DS_U16(ds, DS_GRID_Z) = grid16(DS_U16(ds, record + 4));
    DS_U16(ds, 0x9140) = DS_U16(ds, record + 6);
    DS_U16(ds, DS_STAMP_VALUE) = DS_U16(ds, record + 8);
    seg = DS_U16(ds, 0x91B0);
    uint16_t bitmap = DS_U16(ds, 0x8FEC + (uint16_t)(DS_U16(ds, DS_STAMP_VALUE) * 2));
    bitmap += DS_U16(far_ptr(g, seg, bitmap), 0) + 2;
    DS_U16(ds, DS_STAMP_W) = DS_U16(far_ptr(g, seg, (uint16_t)(bitmap + 8)), 0);
    DS_U16(ds, DS_STAMP_H) = DS_U16(far_ptr(g, seg, (uint16_t)(bitmap + 10)), 0);
    DS_U16(ds, DS_STAMP_X) = DS_U16(ds, DS_GRID_X) - DS_U16(far_ptr(g, seg, (uint16_t)(bitmap + 4)), 0);
    DS_U16(ds, DS_STAMP_Z) = DS_U16(ds, DS_GRID_Z) - DS_U16(far_ptr(g, seg, (uint16_t)(bitmap + 6)), 0);
    uint16_t x = DS_U16(ds, DS_PEN_X) - DS_U16(ds, DS_GRID_X), z = DS_U16(ds, DS_PROBE_Z) - DS_U16(ds, DS_GRID_Z);
    if (DS_U16(ds, 0x9140) & 1) {
        uint16_t swap = x;
        x = z;
        z = swap;
    }
    if (DS_U16(ds, 0x9140) & 2) {
        x = -x;
        z = -z;
    }
    x += DS_U16(ds, DS_GRID_X);
    z += DS_U16(ds, DS_GRID_Z);
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    if (DS_I16(ds, DS_STAMP_X) > (int16_t)x
        || (int16_t)x > (int16_t)(uint16_t)(DS_U16(ds, DS_STAMP_X) + DS_U16(ds, DS_STAMP_W))
        || DS_I16(ds, DS_STAMP_Z) > (int16_t)z
        || (int16_t)z > (int16_t)(uint16_t)(DS_U16(ds, DS_STAMP_Z) + DS_U16(ds, DS_STAMP_H)))
        goto remember_player;
    uint16_t bit = (uint8_t)(z - DS_U16(ds, DS_STAMP_Z)) * (uint8_t)DS_U16(ds, DS_STAMP_W)
                   + (uint16_t)(x - DS_U16(ds, DS_STAMP_X));
    if (!(*far_ptr(g, seg, (uint16_t)(bitmap + 12 + (bit >> 3))) & (128u >> (bit & 7))))
        goto remember_player;
blocked:
    actor = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, actor + 14) & 2)
        event_push(EV_SOUND, 2, 0);
    if (!DS_U8(ds, 0x8683)) {
        for (unsigned i = 0; i < 4; ++i)
            DS_U16(ds, actor + pos[i]) = DS_U16(ds, 0x911E + 2 * i);
        position_normalize(g, actor);
    }
    return 1;
remember_player:
    actor = DS_U16(ds, DS_PLAYER);
remember:
    for (unsigned i = 0; i < 4; ++i)
        DS_U16(ds, 0x911E + 2 * i) = DS_U16(ds, actor + pos[i]);
    return 0;
}

static uint32_t arrival_service(Game *g, uint16_t op, uint16_t arg, void *user)
{
    if (op == TR_COLLISION)
        return (uint32_t)player_collision_test(g, arg) << 16;
    const TravelServices *host = (const TravelServices *)user;
    return host && host->call ? host->call(g, op, arg, host->user) : UINT32_MAX;
}

/* 0641: check the live collision footprint again just before rendering. */
int player_pre_draw_collision(Game *g, const VehicleServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (!player_collision_test(g, actor))
        return 0;
    if (DS_U8(ds, actor + 14) == 1) {
        event_push(EV_SOUND, 10, DS_U8(ds, 0x80E9));
        return 0;
    }
    if (vehicle_transition(g, 1, host))
        return -1;
    actor = DS_U16(ds, DS_PLAYER);
    uint16_t speed = DS_U16(ds, actor + 10);
    if (speed >= 12) {
        for (unsigned k = 0; k < 6; k += 2)
            DS_U16(ds, 0x8114 + k) = DS_U16(ds, actor + k);
        DS_U16(ds, 0x811A) = 0;
        DS_U16(ds, 0x811C) = DS_U16(ds, 0x72CA + DS_U16(ds, 0x72D0));
        DS_U16(ds, 0x811E) = 50;
        explosion_damage_native(g, 0x8114);
    } else {
        uint16_t damage = (uint16_t)((actor == 0x0508 ? 15 : 0) + 4 * DS_U16(ds, DS_DIFFICULTY) + speed) >> 3;
        for (unsigned i = 0; i < 4; ++i)
            player_hit_native(g, damage);
    }
    return 0;
}

/* D265 with native collision. Cell streaming/follow-up remain explicit services. */
int travel_clear_arrival_native(Game *g, const TravelServices *host)
{
    TravelServices adapter = {arrival_service, (void *)host};
    return travel_clear_arrival(g, &adapter);
}
