/* World-clock and off-screen companion/vehicle wandering (B9D2..BB2A). */
#include "term.h"

/* BA60 uses signed word comparisons on each half, including low F000/8000.
 * Preserve those tests rather than replacing them with a conventional 32-bit clamp. */
void world_clamp_actor(uint8_t *ds, uint16_t actor)
{
    for (unsigned axis = 0; axis < 2; ++axis) {
        uint16_t at = actor + (axis ? 42 : 34), lo = DS_U16(ds, at), hi = DS_U16(ds, at + 2), limit = axis ? 1 : 2;
        if ((int16_t)hi < 0 || (!hi && (int16_t)lo < 4096)) {
            lo = 4096;
            hi = 0;
        }
        if ((int16_t)hi > (int16_t)limit || (hi == limit && (int16_t)lo > (int16_t)0xF000)) {
            lo = 0xF000;
            hi = limit;
        }
        DS_U16(ds, at) = lo;
        DS_U16(ds, at + 2) = hi;
    }
}

/* DEB5: unsigned DIV faults retain AX/DX under the source's skip handler. */
void position_normalize_companion(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    for (unsigned axis = 0; axis < 2; ++axis) {
        uint16_t at = 0x53C + (axis ? 42 : 34), lo = DS_U16(ds, at), hi = DS_U16(ds, at + 2);
        uint32_t value = lo | ((uint32_t)hi << 16);
        uint16_t cell = hi < 1024 ? (uint16_t)(value / 1024) : lo, rem = hi < 1024 ? (uint16_t)(value % 1024) : hi;
        DS_U16(ds, 0x53C + (axis ? 32 : 30)) = cell;
        uint16_t local = axis ? (uint16_t)(1024 - rem) : rem;
        DS_U16(ds, 0x53C + (axis ? 4 : 0)) = local;
        uint16_t delta = (uint16_t)(DS_U16(ds, player + (axis ? 32 : 30)) - cell) * 1024;
        DS_U16(ds, axis ? 0xE3EE : 0xE3EC) = axis ? (uint16_t)(local + delta) : (uint16_t)(local - delta);
    }
}

/* BB03: move the out-of-range second actor along with record 04D4. */
void world_follow_companion(uint8_t *ds)
{
    if (DS_U8(ds, DS_COMPANION_ACTIVE) || DS_U16(ds, DS_VEHICLE) != 0x04D4)
        return;
    for (unsigned i = 0; i < 6; ++i)
        DS_U16(ds, 0x055E + i * 2) = DS_U16(ds, 0x04F6 + i * 2);
    uint32_t x = DS_U16(ds, 0x055E) | ((uint32_t)DS_U16(ds, 0x0560) << 16);
    x += 50;
    DS_U16(ds, 0x055E) = x;
    DS_U16(ds, 0x0560) = x >> 16;
    position_normalize_companion(ds);
}

static void move(Game *g, uint16_t heading, int16_t distance)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_VEHICLE), index = heading * 2;
    int16_t dx = mul_hi(distance, DS_I16(ds, 0x4188 + index)),
            dz = (uint16_t)-mul_hi(distance, DS_I16(ds, 0x4288 + index));
    for (unsigned axis = 0; axis < 2; ++axis) {
        uint16_t at = actor + (axis ? 42 : 34);
        uint32_t value = DS_U16(ds, at) | ((uint32_t)DS_U16(ds, at + 2) << 16);
        value += (int32_t)(axis ? dz : dx);
        DS_U16(ds, at) = value;
        DS_U16(ds, at + 2) = value >> 16;
    }
    world_clamp_actor(ds, actor);
    DS_U8(ds, 0x5A25) = 255;
    position_normalize(g, actor);
    world_follow_companion(ds);
}

/* BA1C: a random heading supplied by the caller; serial mode is a source no-op. */
void world_wander_vehicle(Game *g, uint16_t random)
{
    if (!DS_U8(g->ds, DS_LINK_GAME))
        move(g, random & 511, 4096);
}

/* BAB7: directed move, reversed and enlarged outside the target-query path. */
void world_displace_vehicle(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t heading = DS_U16(ds, 0xDE50);
    int16_t distance = 0x1800;
    if (!DS_U8(ds, 0x7A18)) {
        heading = (heading + 256) & 511;
        distance = 0x2000;
    }
    move(g, heading, distance);
}

void world_clock_step(Game *g)
{
    uint8_t *ds = g->ds;
    if (++DS_U8(ds, 0xDE37) >= 6) {
        DS_U8(ds, 0xDE37) = 0;
        if (++DS_U8(ds, 0x0348) >= 60) {
            DS_U8(ds, 0x0348) = 0;
            DS_U16(ds, 0x1174)++;
            if (!DS_U8(ds, DS_OPPONENT_ACTIVE)) {
                uint16_t r = random_word(ds);
                if (r & 1)
                    world_wander_vehicle(g, r);
            }
        }
    }
    if (DS_U8(ds, 0x034E) && DS_U16(ds, 0x04D2))
        DS_U16(ds, 0x04D2)--;
}
