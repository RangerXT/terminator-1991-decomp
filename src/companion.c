/* Companion behavior and motion: DD67/DDBE/DE05, DE46, DD56 modes 0..2. */
#include "term.h"

static void separation_timer(uint8_t *ds)
{
    if (DS_U8(ds, DS_PRACTICE_MODE) || DS_U8(ds, 0x0349))
        return;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint16_t distance = approx_distance(DS_I16(ds, DS_COMPANION_X), DS_I16(ds, DS_COMPANION_Z), DS_I16(ds, player),
                                        DS_I16(ds, player + 4));
    unsigned shift = DS_U16(ds, DS_DIFFICULTY) & 31;
    uint16_t limit = shift >= 16 ? 0 : 10000u >> shift;
    limit -= DS_U8(ds, player + 50);
    if (distance < limit)
        DS_U16(ds, 0x11C2) = 2000;
    else if (!--DS_U16(ds, 0x11C2)) {
        DS_U8(ds, 0x1158) = 255;
        DS_U8(ds, DS_MISSION_OVER) = 1;
    }
}

/* The source table also contains two modal inventory panels, 57E7 and 57D4.
 * Reject those modes before mutation; this entry covers only motion modes 0..2. */
int companion_choose_behavior(uint8_t *ds, uint16_t mode)
{
    if (mode > 2)
        return -1;
    uint16_t player = DS_U16(ds, DS_PLAYER), x = DS_U16(ds, DS_COMPANION_X), z = DS_U16(ds, DS_COMPANION_Z);
    if (!mode) {
        DS_U16(ds, 0x0546) = 0;
        separation_timer(ds);
        return 0;
    }
    if (mode == 1) {
        uint16_t target = DS_U8(ds, DS_OPPONENT_ACTIVE) ? 0xDE52 : player;
        uint16_t tx = DS_U16(ds, target), tz = DS_U16(ds, target + (target == 0xDE52 ? 2 : 4));
        DS_U16(ds, 0x0542) = angle_between(ds, tx, tz, x, z);
        DS_U16(ds, 0x0546) = 15;
        if (!DS_U8(ds, DS_OPPONENT_ACTIVE))
            separation_timer(ds);
        return 0;
    }
    uint16_t distance = approx_distance(x, z, DS_I16(ds, player), DS_I16(ds, player + 4));
    uint16_t speed = distance >= 300 ? DS_U16(ds, player + 10) + 10 : distance < 150 ? 0 : DS_U16(ds, player + 10);
    DS_U16(ds, 0x0546) = speed;
    DS_U16(ds, 0x0542) = angle_between(ds, x, z, DS_I16(ds, player), DS_I16(ds, player + 4));
    return 0;
}

/* DE46: steer using speed*8, then move using speed*2. Collision scratch is kept;
 * the source ignores steering's carry and does not renormalize after this move. */
void companion_move(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t x = DS_U16(ds, DS_COMPANION_X), z = DS_U16(ds, DS_COMPANION_Z), heading = DS_U16(ds, 0x0542),
             speed = DS_U16(ds, 0x0546), index = heading * 2;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, DS_POINT_X) = x;
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, DS_POINT_Z) = z;
    DS_U16(ds, 0xB824) = heading;
    DS_U16(ds, 0xB820) = speed;
    int16_t distance = (uint16_t)(speed * 8);
    DS_U16(ds, DS_POINT_X) += mul_hi(distance, DS_I16(ds, 0x4188 + index));
    DS_U16(ds, DS_POINT_Z) -= mul_hi(distance, DS_I16(ds, 0x4288 + index));
    collision_steer(g);
    heading = DS_U16(ds, 0xB824);
    DS_U16(ds, 0x0542) = heading;
    index = heading * 2;
    distance = (uint16_t)(DS_U16(ds, 0x0546) * 2);
    int16_t dx = mul_hi(distance, DS_I16(ds, 0x4188 + index)), dz = mul_hi(distance, DS_I16(ds, 0x4288 + index));
    uint32_t wx = DS_U16(ds, 0x055E) | ((uint32_t)DS_U16(ds, 0x0560) << 16),
             wz = DS_U16(ds, 0x0566) | ((uint32_t)DS_U16(ds, 0x0568) << 16);
    wx += (int32_t)dx;
    wz -= (int32_t)dz;
    DS_U16(ds, 0x055E) = wx;
    DS_U16(ds, 0x0560) = wx >> 16;
    DS_U16(ds, 0x0566) = wz;
    DS_U16(ds, 0x0568) = wz >> 16;
}

int companion_step(Game *g)
{
    uint16_t mode = DS_U16(g->ds, DS_COMPANION_ORDER);
    if (mode > 2)
        return -1;
    position_normalize_companion(g->ds);
    companion_choose_behavior(g->ds, mode);
    companion_move(g);
    return 0;
}

/* B5B4: initial pursuit thresholds/delay scale with the raw difficulty word. */
void opponent_init_difficulty(uint8_t *ds)
{
    uint16_t add = (uint16_t)(4096 * DS_U16(ds, DS_DIFFICULTY));
    if (DS_U16(ds, DS_PLAYER) != 0x0508)
        DS_U16(ds, 0xDEC8) = add + 0x6000;
    else {
        DS_U16(ds, 0xDECA) = add + 0x9000;
        DS_U16(ds, 0xDECC) = add + 0x7000;
    }
    uint16_t factor = (uint16_t)((4 - DS_U16(ds, DS_DIFFICULTY)) * 2);
    DS_U16(ds, 0x11C0) = DS_U16(ds, 0x04D2) = (uint16_t)(DS_U16(ds, 0x11C0) * factor);
}
