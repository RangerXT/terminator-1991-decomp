/* HUD-only target query. The weapon/damage path of A07B is not translated here. */
#include "term.h"

static int16_t grid_coord(uint16_t value)
{
    return (int16_t)(uint16_t)(value + 8) >> 4;
}

/* orig 11BC:21CA. Mutates endpoints into grid coordinates, as the original does. */
uint16_t collision_grid_address(uint8_t *ds)
{
    DS_U8(ds, 0x8681) = 0;
    DS_U16(ds, DS_POINT_X) = (uint16_t)grid_coord(DS_U16(ds, DS_POINT_X));
    DS_U16(ds, DS_POINT_Z) = (uint16_t)grid_coord(DS_U16(ds, DS_POINT_Z));
    DS_U16(ds, DS_PEN_X) = (uint16_t)grid_coord(DS_U16(ds, DS_PEN_X));
    uint16_t x = (uint16_t)(DS_U16(ds, DS_PEN_X) + 64);
    if ((int16_t)x < 0 || x >= 192)
        DS_U8(ds, 0x8681) = 255;
    DS_U16(ds, DS_PEN_Y) = (uint16_t)grid_coord(DS_U16(ds, DS_PEN_Y));
    DS_U16(ds, DS_PROBE_Z) = (uint16_t)grid_coord(DS_U16(ds, DS_PROBE_Z));
    uint16_t z = (uint16_t)(DS_U16(ds, DS_PROBE_Z) + 64);
    if ((int16_t)z < 0 || z >= 192)
        DS_U8(ds, 0x8681) = 255;
    /* MUL DL uses AL, even when the coordinate is outside the nominal grid. */
    return (uint16_t)(0x9000 - 192 * (uint8_t)z + x);
}

static uint16_t magnitude(uint16_t v)
{
    return (int16_t)v < 0 ? (uint16_t)-v : v;
}

/* orig 11BC:25B0. Return the nonzero blocking cell byte, or zero for clear.
 * The incoming world coordinates are consumed in place. It does not reject the
 * address helper's carry; it checks DI < 9000 inside the walk instead. */
uint64_t collision_line_blocker_state(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_SEG_COLLISION);
    uint16_t at = collision_grid_address(ds);
    uint16_t dx = (uint16_t)(DS_U16(ds, DS_PEN_X) - DS_U16(ds, DS_POINT_X));
    uint16_t dz = (uint16_t)(DS_U16(ds, DS_PROBE_Z) - DS_U16(ds, DS_POINT_Z));
    int16_t row_step = (int16_t)dz < 0 ? -192 : 192;
    DS_U8(ds, 0x8682) = *far_ptr(g, seg, at) ? 255 : 0;
    uint16_t mx = magnitude(dx), mz = magnitude(dz);
    int x_major = mx >= mz;
    uint16_t major = x_major ? mx : mz, minor = x_major ? mz : mx;
    uint16_t count = major;
    if (!x_major && !count)
        return (uint64_t)minor << 32;
    if (DS_U8(ds, 0x8684)) {
        count -= 6;
        if ((int16_t)count < 0)
            return ((uint64_t)minor << 32) | ((uint32_t)count << 16);
    }
    if (x_major && !count)
        return (uint64_t)minor << 32;
    int16_t col_step = (int16_t)dx < 0 ? 1 : -1;
    uint16_t error = minor;
    /* In the Z-major branch, an exact six-step shortened walk has LOOP count 0
     * and executes 65536 iterations unless an earlier grid bound/cell stops it. */
    unsigned steps = count ? count : 65536;
    for (unsigned i = 0; i < steps; ++i) {
        uint64_t regs = ((uint64_t)minor << 32) | ((uint32_t)(uint16_t)(steps - i) << 16);
        if (at >= 0x9000)
            return regs;
        uint8_t cell = *far_ptr(g, seg, at);
        if (cell)
            return regs | cell;
        at += x_major ? col_step : row_step;
        error += minor;
        if (error >= major) {
            error -= major;
            at += x_major ? row_step : col_step;
        }
    }
    return (uint64_t)minor << 32;
}

/* Existing callers consume only the blocking byte; flight also needs CX/DX. */
uint8_t collision_line_blocker(Game *g)
{
    return (uint8_t)collision_line_blocker_state(g);
}

/* orig A2B3. Signed inclusive screen bounds in an 18-byte collected-target entry. */
int hud_target_contains_sight(uint8_t *ds, uint16_t target)
{
    int16_t x = DS_I16(ds, DS_SIGHT_X), y = DS_I16(ds, DS_SIGHT_Y);
    return x >= DS_I16(ds, target + 6) && x <= DS_I16(ds, target + 8) && y >= DS_I16(ds, target + 10)
           && y <= DS_I16(ds, target + 12);
}

/* orig A07B, only when DS:7A18 != 0. Return SI plus carry in bit 16.
 * The query consumes the collision coordinates in place, including the source's
 * repeated scaling when more than one candidate reaches the line test. */
uint32_t hud_scan_target(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x7A18))
        return UINT32_MAX;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, 0xB65E) = DS_U16(ds, 0x118C) & 511;
    DS_U16(ds, 0xB660) = (DS_U16(ds, player + 6) + DS_U16(ds, player + 8) + DS_U16(ds, 0x118A)) & 511;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, player);
    DS_U16(ds, DS_PEN_Y) = DS_U16(ds, player + 2);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, player + 4);
    uint16_t weapon = (uint16_t)(0x0570 + 6 * (uint8_t)(DS_U8(ds, DS_WEAPON) - 1));
    DS_U16(ds, 0xB66A) = (uint16_t)(int16_t)(int8_t)DS_U8(ds, weapon + 5);
    uint16_t count = DS_U16(ds, 0xB64E), result = player;
    uint16_t target = 0xB18E;
    for (unsigned i = 0; i < count; ++i, target += 18) {
        DS_U16(ds, DS_POINT_X) = DS_U16(ds, DS_PEN_X);
        DS_U16(ds, 0xB664) = DS_U16(ds, DS_PEN_Y);
        DS_U16(ds, DS_POINT_Z) = DS_U16(ds, DS_PROBE_Z);
        DS_U16(ds, 0xB668) = DS_U16(ds, target + 4);
        uint16_t pitch = (uint16_t)(2 * DS_U16(ds, 0xB65E));
        uint16_t heading = (uint16_t)(2 * DS_U16(ds, 0xB660));
        int16_t distance = DS_I16(ds, 0xB668);
        DS_U16(ds, 0xB664) += mul_hi(distance, DS_I16(ds, 0x4188 + pitch));
        DS_U16(ds, DS_POINT_X) += mul_hi(distance, DS_I16(ds, 0x4188 + heading));
        DS_U16(ds, DS_POINT_Z) += mul_hi(distance, DS_I16(ds, 0x4288 + heading));
        result = target;
        if (hud_target_contains_sight(ds, target) && !collision_line_blocker(g))
            return (uint32_t)target | 0x10000;
    }
    return result;
}
