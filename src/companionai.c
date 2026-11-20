/* DB26 companion AI, preserving its source register-dependent direction quirks. */
#include "term.h"

static void away(uint8_t *ds)
{
    DS_U16(ds, 0x0568) += 20000;
    position_normalize_companion(ds);
}

static void choose(uint8_t *ds, uint16_t ax, uint16_t bx)
{
    figure_select_position(ds, 0, 1);
    DS_U16(ds, 0x0542) = angle_between(ds, ax, bx, DS_I16(ds, DS_POINT_X), DS_I16(ds, DS_POINT_Z));
}

int companion_ai(Game *g, const VehicleServices *vehicle)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 1) && !vehicle)
        return -1;
    if (!DS_U8(ds, DS_COMPANION_ACTIVE)) {
        DS_U8(ds, 0x0360) = 0;
        return 0;
    }
    companion_move(g);
    position_normalize_companion(ds);
    uint16_t x = DS_U16(ds, DS_COMPANION_X), z = DS_U16(ds, DS_COMPANION_Z);
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, player);
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, player + 4);
    DS_U8(ds, 0x0349) = !collision_line_blocker(g);
    if (DS_U8(ds, 0x0349)) {
        uint16_t distance = approx_distance(x, z, DS_I16(ds, player), DS_I16(ds, player + 4));
        uint16_t ax = angle_between(ds, x, z, DS_I16(ds, player), DS_I16(ds, player + 4));
        if (distance < 1500) {
            ax = random_word(ds);
            if (ax >= 60000) {
                DS_U8(ds, 0xE3E0) = 255;
                int32_t shot = opponent_fire_state(g, x, z, 3, DS_U16(ds, 0xDECC), vehicle);
                if (shot < 0)
                    return -1;
                ax = (uint16_t)shot;
                DS_U8(ds, 0xE3E0) = 0;
            }
        }
        if (distance >= 500 && !DS_U8(ds, 0x034C)) {
            DS_U16(ds, DS_PEN_X) = x;
            DS_U16(ds, DS_PROBE_Z) = z;
            choose(ds, x, z);
            return 0;
        }
        /* DBE9 uses the current AX (possibly random/hit feedback), without a
         * heading mask. DC13 reaches the query with AX=pen Z and BX=table index. */
        uint16_t index = (uint16_t)((ax + 256) * 2);
        DS_U16(ds, DS_PEN_X) = x + mul_hi(1000, DS_I16(ds, 0x4188 + index));
        uint16_t pen_z = z + mul_hi(1000, DS_I16(ds, 0x4288 + index));
        DS_U16(ds, DS_PROBE_Z) = pen_z;
        choose(ds, pen_z, index);
        return 0;
    }
    /* DC18 loads E3EC for both axes; DC2D modifies the high global Z word. */
    uint16_t distance = approx_distance(x, x, DS_I16(ds, player), DS_I16(ds, player + 4));
    uint16_t remaining = DS_U16(ds, 0x0558) - DS_U16(ds, 0x0556);
    if (distance < 500 || DS_U8(ds, 0x034C) || remaining < 8) {
        away(ds);
        return 0;
    }
    if (!DS_U8(ds, DS_OPPONENT_ACTIVE)) {
        if (!DS_U8(ds, 0x034A))
            away(ds);
        return 0;
    }
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    choose(ds, x, z);
    return 0;
}

int companion_ai_on_foot(Game *g)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return companion_ai(g, NULL);
}
