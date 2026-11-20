#include "term.h"

/* orig B660: place record 053C in the player's local coordinate frame.
 * Returns the original carry flag (outside the five-by-five cell neighborhood). */
int position_relative_actor(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U8(ds, DS_COMPANION_ACTIVE) = 0;
    int16_t x = (int16_t)(DS_U16(ds, 0x53C + 30) - DS_U16(ds, player + 30));
    if (x < -2 || x > 2)
        return 1;
    DS_U16(ds, DS_COMPANION_X) = (uint16_t)(x * 1024 + DS_U16(ds, 0x53C));
    int16_t z = (int16_t)(DS_U16(ds, player + 32) - DS_U16(ds, 0x53C + 32));
    if (z < -2 || z > 2)
        return 1;
    DS_U8(ds, DS_COMPANION_ACTIVE) = 255;
    DS_U16(ds, DS_COMPANION_Z) = (uint16_t)(z * 1024 + DS_U16(ds, 0x540));
    return 0;
}

/* orig 2FB2 and DB01: preserve the original AX update of both figure fields. */
static void rebase(Game *g, uint16_t x, uint16_t z)
{
    uint8_t *ds = g->ds;
    uint16_t off = DS_U16(ds, 0x96CC), seg = DS_U16(ds, 0x96CE);
    for (unsigned i = 0; i < DS_U16(ds, 0x1178); ++i, off += 12) {
        DS_U16(far_ptr(g, seg, off), 0) += x;
        DS_U16(far_ptr(g, seg, (uint16_t)(off + 4)), 0) += z;
    }
    for (unsigned i = 0; i < DS_U16(ds, DS_FIGURE_COUNT); ++i) {
        DS_U16(ds, 0xDF0 + 12 * i) += x;
        DS_U16(ds, 0xDF4 + 12 * i) += z;
        DS_U16(ds, 0xB32 + 22 * i) += x;
        DS_U16(ds, 0xB34 + 22 * i) += x;
    }
    for (unsigned i = 0; i < 5; ++i) {
        DS_U16(ds, 0xB08 + 8 * i) += x;
        DS_U16(ds, 0xB0A + 8 * i) += z;
    }
    DS_U16(ds, 0x367) += x;
    DS_U16(ds, 0x36B) += z;
    DS_U16(ds, 0x4BC) += x;
    DS_U16(ds, 0x4BE) += z;
    DS_U16(ds, 0x10F0) += x;
    DS_U16(ds, 0x10F4) += z;
    if (DS_U16(ds, 0x10F8) && !(DS_U16(ds, DS_U16(ds, 0x10FA) + 6) & 0x2000)) {
        DS_U16(ds, 0x10FC) += x;
        DS_U16(ds, 0x10FE) += z;
    }
}

/* orig 0000:2F1C; unsigned DIV overflow keeps AX/DX under the game's skip handler. */
uint16_t position_normalize_bx(Game *g, uint16_t record)
{
    uint8_t *ds = g->ds;
    uint16_t shift[2] = {0, 0};
    DS_U8(ds, 0x5A26) = 0;
    for (unsigned axis = 0; axis < 2; ++axis) {
        uint16_t base = record + (axis ? 0x2A : 0x22);
        uint16_t low = DS_U16(ds, base), high = DS_U16(ds, base + 2);
        uint32_t whole = low | ((uint32_t)high << 16);
        uint16_t cell = high < 1024 ? (uint16_t)(whole / 1024) : low;
        uint16_t rem = high < 1024 ? (uint16_t)(whole % 1024) : high;
        uint16_t at = record + (axis ? 32 : 30), old = DS_U16(ds, at);
        if (old != cell) {
            DS_U8(ds, 0x5A26) = 255;
            shift[axis] = (uint16_t)((old > cell) == (axis == 0) ? 1024 : -1024);
        }
        DS_U16(ds, at) = cell;
        DS_U16(ds, record + (axis ? 4 : 0)) = axis ? (uint16_t)(1024 - rem) : rem;
    }
    if (!DS_U8(ds, 0x5A25)) {
        DS_U8(ds, 0x5EF6) += DS_U8(ds, 0x5A26);
        if (!DS_U8(ds, 0x5EF6)) {
            --DS_U16(ds, DS_FUEL);
            DS_U8(ds, 0x5EF6) = 8;
        }
        if (shift[0] || shift[1])
            rebase(g, shift[0], shift[1]);
    }
    DS_U8(ds, 0x5A25) = 0;
    return shift[1];
}

void position_normalize(Game *g, uint16_t record)
{
    (void)position_normalize_bx(g, record);
}

/* BB2B: local-frame vehicle position, two visibility queries and relative bearing.
 * The first collision query restores pen X/Z before the companion query; the
 * second deliberately leaves its scratch changes. Return original carry. */
int position_relative_vehicle(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER), vehicle = DS_U16(ds, DS_VEHICLE);
    DS_U8(ds, DS_OPPONENT_ACTIVE) = 0;
    int16_t x = (uint16_t)(DS_U16(ds, vehicle + 30) - DS_U16(ds, player + 30));
    if (x < -2 || x > 2)
        return 1;
    DS_U16(ds, DS_OPPONENT_X) = (uint16_t)(x * 1024 + DS_U16(ds, vehicle));
    int16_t z = (uint16_t)(DS_U16(ds, player + 32) - DS_U16(ds, vehicle + 32));
    if (z < -2 || z > 2)
        return 1;
    DS_U8(ds, DS_OPPONENT_ACTIVE) = 255;
    DS_U16(ds, DS_OPPONENT_Z) = (uint16_t)(z * 1024 + DS_U16(ds, vehicle + 4));
    uint16_t px = DS_U16(ds, DS_OPPONENT_X), pz = DS_U16(ds, DS_OPPONENT_Z);
    DS_U16(ds, DS_PEN_X) = px;
    DS_U16(ds, DS_PROBE_Z) = pz;
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, player);
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, player + 4);
    DS_U8(ds, 0x0349) = 0;
    DS_U8(ds, 0x0349) += !collision_line_blocker(g);
    DS_U16(ds, DS_PROBE_Z) = pz;
    DS_U16(ds, DS_PEN_X) = px;
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, 0x053C);
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, 0x0540);
    DS_U8(ds, 0x034A) = 0;
    DS_U8(ds, 0x034A) += !collision_line_blocker(g);
    player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, 0xDE50) = angle_between(ds, DS_I16(ds, DS_OPPONENT_X), DS_I16(ds, DS_OPPONENT_Z), DS_I16(ds, player),
                                       DS_I16(ds, player + 4));
    return 0;
}
