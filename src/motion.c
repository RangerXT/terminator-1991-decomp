/* Collision steering and the nearby vehicle's pursuit movement. */
#include "term.h"

static void steering_target(uint8_t *ds, uint16_t x, uint16_t z, uint16_t heading)
{
    uint16_t index = heading * 2;
    int16_t distance = (uint16_t)(DS_U16(ds, 0xB820) * 32);
    DS_U16(ds, DS_POINT_X) = x + mul_hi(distance, DS_I16(ds, 0x4188 + index));
    DS_U16(ds, DS_POINT_Z) = z + mul_hi(distance, DS_I16(ds, 0x4288 + index));
}

/* AA81: initial query, straight look-ahead, then alternating +/- offsets. */
int collision_steer(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0xB82E) = 0;
    uint16_t x = DS_U16(ds, DS_PEN_X), z = DS_U16(ds, DS_PROBE_Z);
    uint8_t blocked = collision_line_blocker(g);
    if ((int8_t)DS_U8(ds, 0x8681) < 0)
        return 1;
    if (!blocked)
        goto found;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    steering_target(ds, x, z, DS_U16(ds, 0xB824));
    if (!collision_line_blocker(g))
        goto found;
    for (;;) {
        DS_U16(ds, 0xB82E) += 32;
        /* AB73 discards the saved words with ADD SP, leaving carry clear on
         * the ordinary non-wrapping DOS stack despite exhausted steering. */
        if (DS_I16(ds, 0xB82E) > 256)
            return 0;
        DS_U8(ds, 0x7A18) = 0;
        do {
            DS_U16(ds, DS_PEN_X) = x;
            DS_U16(ds, DS_PROBE_Z) = z;
            steering_target(ds, x, z, (DS_U16(ds, 0xB824) + DS_U16(ds, 0xB82E)) & 511);
            if (!collision_line_blocker(g))
                goto found;
            DS_U16(ds, 0xB82E) = -DS_U16(ds, 0xB82E);
            DS_U8(ds, 0x7A18) ^= 1;
        } while (DS_U8(ds, 0x7A18));
    }
found:
    DS_U16(ds, 0xB824) = (DS_U16(ds, 0xB824) + DS_U16(ds, 0xB82E)) & 511;
    return 0;
}

/* B755: choose a nearby destination, or stop the vehicle while the latch is set. */
uint8_t vehicle_choose_destination(uint8_t *ds)
{
    if (DS_U8(ds, 0x034F)) {
        DS_U16(ds, DS_U16(ds, DS_VEHICLE) + 10) = 0;
        return 0;
    }
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, DS_OPPONENT_X);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, DS_OPPONENT_Z);
    uint8_t carry = figure_select_position(ds, 0, DS_U8(ds, 0x0349));
    DS_U16(ds, 0x04BC) = DS_U16(ds, DS_POINT_X);
    DS_U16(ds, 0x04BE) = DS_U16(ds, DS_POINT_Z);
    return carry;
}

/* B6AA: destination selection, steering, heading/speed and normalized motion. */
void vehicle_follow_route(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_OPPONENT_ACTIVE))
        return;
    DS_U8(ds, 0x034D) = 255;
    uint16_t x = DS_U16(ds, DS_OPPONENT_X), z = DS_U16(ds, DS_OPPONENT_Z), tx = DS_U16(ds, 0x04BC),
             tz = DS_U16(ds, 0x04BE);
    DS_U16(ds, DS_POINT_X) = tx;
    DS_U16(ds, DS_POINT_Z) = tz;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    DS_U16(ds, 0xDE56) = approx_distance(x, z, tx, tz);
    if (DS_U16(ds, 0xDE56) < 100 && DS_U8(ds, 0x034D) && vehicle_choose_destination(ds))
        return;
    DS_U16(ds, 0xB824) = angle_between(ds, x, z, tx, tz);
    uint16_t actor = DS_U16(ds, DS_VEHICLE);
    DS_U16(ds, 0xB820) = DS_U16(ds, actor + 10);
    collision_steer(g);
    actor = DS_U16(ds, DS_VEHICLE);
    DS_U16(ds, actor + 6) = DS_U16(ds, 0xB824);
    if (DS_U16(ds, 0xDE56) >= 300)
        DS_U16(ds, actor + 10) = 10;
    uint16_t index = DS_U16(ds, actor + 6) * 2;
    int16_t speed = (uint16_t)(DS_U16(ds, actor + 10) * 2);
    int16_t dx = mul_hi(speed, DS_I16(ds, 0x4188 + index)), dz = (uint16_t)-mul_hi(speed, DS_I16(ds, 0x4288 + index));
    for (unsigned axis = 0; axis < 2; ++axis) {
        uint16_t at = actor + (axis ? 42 : 34);
        uint32_t value = DS_U16(ds, at) | ((uint32_t)DS_U16(ds, at + 2) << 16);
        value += (int32_t)(axis ? dz : dx);
        DS_U16(ds, at) = value;
        DS_U16(ds, at + 2) = value >> 16;
    }
    DS_U8(ds, 0x5A25) = 255;
    position_normalize(g, actor);
}

/* B790: delay scaling retains the original 16-bit SHL count behavior. */
void world_update_delay(uint8_t *ds)
{
    DS_U16(ds, 0x04D2) += DS_U16(ds, 0x11C0);
    uint16_t shift = DS_U16(ds, 0x1174) >> 1;
    do {
        shift >>= 1;
    } while (shift & 0xFF00);
    uint16_t amount = (uint16_t)(1u << (shift & 31));
    DS_U16(ds, 0x04D2) -= amount;
    if (DS_I16(ds, 0x04D2) < 0)
        DS_U16(ds, 0x04D2) = DS_U16(ds, 0x11C0);
}
