/* Opponent firing, including native vehicle damage/destruction and exit. */
#include "term.h"

/* BC68. Vehicle targets require resources for a possible destruction/exit chain.
 * A host failure after the shot has begun returns -1 with preceding effects kept. */
int32_t opponent_fire_state(Game *g, uint16_t x, uint16_t z, uint16_t sound, uint16_t threshold,
                            const VehicleServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, actor + 14) & 1) && !host)
        return -1;
    uint16_t heading = angle_between(ds, x, z, DS_I16(ds, actor), DS_I16(ds, actor + 4));
    uint16_t direction = DS_U8(ds, 0xE3E0) ? 0x7B48 : 0x7B64;
    DS_U16(ds, direction) = (heading + 256) & 511;
    DS_U8(ds, DS_U8(ds, 0xE3E0) ? 0x7AC2 : 0x7AC4) = 10;
    DS_U16(ds, 0xB65E) = 65533;
    weapon_visual_insert(ds, x, DS_U16(ds, actor + 2) - 2, z, heading);
    event_push(EV_SOUND, sound & 255, 0);
    uint16_t ax = DS_U16(ds, 0x9126) + DS_U16(ds, 0x1174);
    unsigned shift = (uint16_t)(DS_U16(ds, DS_DIFFICULTY) * 2 + 1) & 31;
    ax = shift < 16 ? ax >> shift : 0;
    uint32_t sum = (uint32_t)threshold + ax;
    if (sum <= 65535) {
        ax = random_word(ds);
        if (ax < (uint16_t)sum)
            goto hit;
        return ax;
    }
hit:
    ax = (ax & 0xFF00) | 1;
    actor = DS_U16(ds, DS_PLAYER);
    DS_U8(ds, 0x7A18) = 0;
    if (!(DS_U8(ds, actor + 14) & 1)) {
        DS_U8(ds, 0x7A18) = 255;
        uint16_t value = random_word(ds), bx = (uint16_t)sum;
        bx = (bx & 0xFF00) | (value >> 8);
        DS_U16(ds, actor + 48) -= (value & 3) + 1;
        if (DS_I16(ds, actor + 48) < 0) {
            debris_start(g, DS_U16(ds, 0xDE4C), DS_U16(ds, 0x72CA));
            player_hit_native_state(g, actor == 0x04D4 ? 10 : 20);
            int32_t exit_bx = vehicle_exit_state(g, host);
            if (exit_bx < 0)
                return -1;
            bx = (uint16_t)exit_bx;
        }
        if ((uint8_t)bx >= 0x50)
            return ax;
    }
    if (DS_U8(ds, 0xAA98)) {
        if (!--DS_U8(ds, actor + 51)) {
            DS_U8(ds, 0xAA98) = 0;
            if (!DS_U8(ds, 0x7A18))
                hud_message(g, 0xB6A2);
            inventory_remove(ds, 15);
        } else if ((ax >> 8) < 245)
            return ax;
    }
    return player_hit_native_state(g, ax & 255);
}

/* Compatibility contract: reject vehicle targets before any effects. */
int32_t opponent_fire_on_foot_state(Game *g, uint16_t x, uint16_t z, uint16_t sound, uint16_t threshold)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return opponent_fire_state(g, x, z, sound, threshold, NULL);
}

/* Status-only compatibility entry; companion AI consumes AX through state above. */
int opponent_fire_on_foot(Game *g, uint16_t x, uint16_t z, uint16_t sound, uint16_t threshold)
{
    return opponent_fire_on_foot_state(g, x, z, sound, threshold) < 0 ? -1 : 0;
}

/* BF1B and C397. New bursts inherit DX; a fresh choice-table build leaves DL=4.
 * Continued bursts instead load DEC8/DECA. Preserve that difference explicitly. */
int opponent_burst(Game *g, uint8_t fast, uint16_t incoming_dx, const VehicleServices *host)
{
    uint8_t *ds = g->ds;
    if (!(DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1) && !host)
        return -1;
    if (DS_U8(ds, 0xAA83))
        return 0;
    if (DS_U8(ds, 0x0356)) {
        if (--DS_U8(ds, 0x0357))
            return 0;
        if (opponent_fire_state(g, DS_U16(ds, DS_OPPONENT_X), DS_U16(ds, DS_OPPONENT_Z), DS_U8(ds, 0x035F),
                                DS_U16(ds, fast ? 0xDECA : 0xDEC8), host)
            < 0)
            return -1;
        DS_U8(ds, 0x0356)--;
        DS_U8(ds, 0x0357) = (random_word(ds) & 7) + 3;
        return 0;
    }
    uint8_t latched = DS_U8(ds, 0x0359);
    opponent_select_choice(g, 0);
    if (!latched)
        incoming_dx = (incoming_dx & 0xFF00) | 4;
    if (!DS_U8(ds, 0x0359) || --DS_U8(ds, 0x0358))
        return 0;
    uint16_t random = random_word(ds);
    uint8_t burst = ((random >> 8) & 7) + 3;
    DS_U8(ds, 0x0358) = (random & 7) + (fast ? 7 : 15);
    DS_U8(ds, 0x0356) = burst;
    DS_U8(ds, 0x0355) -= burst;
    DS_U8(ds, 0x0357) = burst;
    if (opponent_fire_state(g, DS_U16(ds, DS_OPPONENT_X), DS_U16(ds, DS_OPPONENT_Z), DS_U8(ds, 0x035F), incoming_dx,
                            host)
        < 0)
        return -1;
    if ((int8_t)DS_U8(ds, 0x0355) <= 0) {
        uint16_t index = DS_U16(ds, 0xDE46);
        DS_U8(ds, 0x0355) = DS_U8(ds, 0xDE38 + index);
        if (!--DS_U8(ds, 0x0351 + index))
            DS_U8(ds, 0x0359) = 0;
    }
    return 0;
}

int opponent_burst_on_foot(Game *g, uint8_t fast, uint16_t incoming_dx)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return opponent_burst(g, fast, incoming_dx, NULL);
}
