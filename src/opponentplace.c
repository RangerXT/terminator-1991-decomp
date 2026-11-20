/* Encounter placement after fast travel: BBF1/BC02, C35F and DC7B. */
#include "term.h"

static void placement_pen(uint8_t *ds, uint16_t heading)
{
    uint16_t player = DS_U16(ds, DS_PLAYER), index = heading * 2;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, player) + mul_hi(2000, DS_I16(ds, 0x4188 + index));
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, player + 4) + mul_hi(2000, DS_I16(ds, 0x4288 + index));
}

/* Convert wrapped signed local deltas to the player's two 32-bit world axes.
 * DC7B unusually uses the companion's local Z when computing its Z delta. */
static void placement_world(uint8_t *ds, uint16_t actor, uint16_t x, uint16_t z, int companion)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    int16_t dx = (uint16_t)(x - DS_U16(ds, player));
    int16_t dz = (uint16_t)(DS_U16(ds, (companion ? actor : player) + 4) - z);
    uint32_t wx = DS_U16(ds, player + 34) | ((uint32_t)DS_U16(ds, player + 36) << 16);
    uint32_t wz = DS_U16(ds, player + 42) | ((uint32_t)DS_U16(ds, player + 44) << 16);
    wx += (int32_t)dx;
    wz += (int32_t)dz;
    DS_U16(ds, actor + 34) = wx;
    DS_U16(ds, actor + 36) = wx >> 16;
    DS_U16(ds, actor + 42) = wz;
    DS_U16(ds, actor + 44) = wz >> 16;
}

static void place_opponent(Game *g, uint16_t heading)
{
    uint8_t *ds = g->ds;
    placement_pen(ds, heading);
    if (figure_select_position(ds, 0, 1))
        return;
    uint16_t x = DS_U16(ds, DS_POINT_X), z = DS_U16(ds, DS_POINT_Z), actor = DS_U16(ds, DS_VEHICLE);
    DS_U16(ds, DS_OPPONENT_X) = x;
    DS_U16(ds, DS_OPPONENT_Z) = z;
    placement_world(ds, actor, x, z, 0);
    DS_U8(ds, 0x5A25) = 255;
    position_normalize(g, actor);
}

/* BBF1: this entry clears the selected-weapon flag, even when selection fails. */
void opponent_place_ahead(Game *g)
{
    DS_U8(g->ds, 0x0359) = 0;
    place_opponent(g, DS_U16(g->ds, DS_U16(g->ds, DS_PLAYER) + 6));
}

/* C35F: the side/offset depends on heading parity and one random word. Unlike
 * BBF1, this entry retains 0359 and writes DE58 before any possible failure. */
void opponent_place_flank(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t heading = DS_U16(ds, DS_U16(ds, DS_PLAYER) + 6);
    int16_t offset = random_word(ds) >= 0xA000 ? 128 : 200;
    if (heading & 1)
        offset = -offset;
    heading = (heading + offset) & 511;
    DS_U16(ds, 0xDE58) = heading;
    place_opponent(g, heading);
}

/* DC7B ignores A840's carry: failed selection still uses its resulting/stale
 * B662/B666 words. Low remaining health skips all placement state changes. */
void opponent_place_companion(Game *g)
{
    uint8_t *ds = g->ds;
    if ((uint16_t)(DS_U16(ds, 0x0558) - DS_U16(ds, 0x0556)) < 8)
        return;
    placement_pen(ds, (DS_U16(ds, 0xDE58) + 256) & 511);
    figure_select_position(ds, 0, 1);
    uint16_t x = DS_U16(ds, DS_POINT_X), z = DS_U16(ds, DS_POINT_Z);
    DS_U16(ds, DS_COMPANION_X) = x;
    DS_U16(ds, DS_COMPANION_Z) = z;
    placement_world(ds, 0x053C, x, z, 1);
    position_normalize_companion(ds);
    DS_U8(ds, DS_COMPANION_ACTIVE) = 255;
    DS_U8(ds, 0x034C) = 0;
}
