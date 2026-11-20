/* Opponent destination/follow selection and the fast-travel interruption gate. */
#include "term.h"

/* C1CB: return AX | BX<<16 | CX<<32. On a failed complete search, A840 leaves
 * AX=0 and BX at the last right-edge grid cell B7D0; the caller stores them. */
uint64_t opponent_destination_query(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, DS_OPPONENT_X);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, DS_OPPONENT_Z);
    uint8_t carry = figure_select_position(ds, 0, 1);
    if (carry)
        carry = figure_select_position(ds, 65535, 1);
    if (carry)
        return ((uint64_t)0xEA60 << 32) | ((uint64_t)0xB7D0 << 16);
    uint16_t x = DS_U16(ds, DS_POINT_X), z = DS_U16(ds, DS_POINT_Z);
    uint16_t distance = approx_distance(x, z, DS_I16(ds, DS_OPPONENT_X), DS_I16(ds, DS_OPPONENT_Z));
    return x | ((uint64_t)z << 16) | ((uint64_t)distance << 32);
}

void opponent_pick_destination(Game *g)
{
    uint64_t result = opponent_destination_query(g);
    DS_U16(g->ds, 0x04BC) = (uint16_t)result;
    DS_U16(g->ds, 0x04BE) = (uint16_t)(result >> 16);
    DS_U16(g->ds, 0x04C2) = 1 + ((uint16_t)(result >> 32) >= 1536);
}

/* B91F deliberately checks the candidate count, ignoring A840's carry. */
uint32_t opponent_openings_state(uint8_t *ds)
{
    uint16_t x = DS_U16(ds, DS_OPPONENT_X), z = DS_U16(ds, DS_OPPONENT_Z);
    int outside = (int16_t)x < -1024 || (int16_t)x > 2048 || (int16_t)z < -1024 || (int16_t)z > 2048;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    DS_U8(ds, 0xB735) = 255;
    figure_select_position(ds, 0, 1);
    DS_U8(ds, 0xB735) = 0;
    /* AA17 preserves AX on a bounds failure. A scan returns BP=1 on success,
     * or AX=0 after its final XOR AL,AL. C247 consumes the resulting AX. */
    uint16_t ax = outside ? x : (DS_U8(ds, 0x7A18) ? 1 : 0);
    return ax | ((uint32_t)(DS_U8(ds, 0xB734) < 2) << 16);
}

uint8_t opponent_has_openings(uint8_t *ds)
{
    return opponent_openings_state(ds) >> 16;
}

/* B94A: raw follow-mode flag derived from actor identity and remaining health. */
void opponent_choose_follow_mode(uint8_t *ds)
{
    uint16_t actor = DS_U16(ds, DS_VEHICLE);
    uint8_t flag = 0;
    if (actor != 0x04D4) {
        uint16_t maximum = DS_U16(ds, actor + 28), remaining = maximum - DS_U16(ds, actor + 26);
        if ((maximum >> 1) < remaining)
            flag = 255;
    }
    DS_U8(ds, 0x034F) = flag;
    DS_U16(ds, 0x04C2) = 0;
}

void opponent_follow_destination(uint8_t *ds)
{
    if (!DS_U8(ds, 0x034F)) {
        if (DS_U8(ds, 0x0349))
            return;
        DS_U16(ds, DS_PEN_X) = DS_U16(ds, DS_OPPONENT_X);
        DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, DS_OPPONENT_Z);
        figure_select_position(ds, 0, 0);
        DS_U16(ds, 0x04BC) = DS_U16(ds, DS_POINT_X);
        DS_U16(ds, 0x04BE) = DS_U16(ds, DS_POINT_Z);
        return;
    }
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (actor == 0x04D4 && !DS_U8(ds, 0xB69F))
        actor = 0x053C;
    DS_U16(ds, 0x04BC) = DS_U16(ds, actor);
    DS_U16(ds, 0x04BE) = DS_U16(ds, actor + 4);
}

/* C42F: native choice inventory, health gate and available spawn-grid space. */
int opponent_check_travel_interrupt(Game *g)
{
    uint8_t *ds = g->ds;
    opponent_select_choice(g, 0);
    if (DS_U8(ds, 0x0359)) {
        uint16_t actor = DS_U16(ds, DS_VEHICLE);
        if ((uint16_t)(DS_U16(ds, actor + 28) - DS_U16(ds, actor + 26)) >= 6) {
            figure_spawn_grid(g);
            if (DS_U16(ds, 0xB82A) >= 16)
                return 0;
        }
    }
    DS_U16(ds, 0x04D2) = 50;
    return 1;
}
