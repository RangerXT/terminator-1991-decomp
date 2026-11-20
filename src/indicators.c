/* Post-scene compass indicators and the alternate-view bearing tick. */
#include "term.h"

/* orig 11BC:19E1. Each history has one endpoint for each of three video pages. */
static uint16_t indicator_erase_dx(Game *g, uint16_t history, uint16_t dx)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, history) == 65535 && DS_U16(ds, history + 4) == 65535 && DS_U16(ds, history + 8) == 65535)
        return dx;
    DS_U8(ds, 0x7AC5) = 255;
    dx = (uint16_t)(hud_compass_needle_registers(g, history, 0, 0, dx) >> 16);
    DS_U8(ds, 0x7AC5) = 0;
    return dx;
}

void hud_indicator_erase(Game *g, uint16_t history)
{
    (void)indicator_erase_dx(g, history, 0);
}

/* Both 18F2 and 195C use AX/CX for columns but BX/DX for target/player rows. */
static uint16_t indicator_direction(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint16_t other = DS_U8(ds, DS_LINK_GAME) && DS_U8(ds, 0xAF52) ? DS_U16(ds, DS_VEHICLE) : 0x053C;
    return angle_between(ds, DS_I16(ds, player + 30), DS_I16(ds, other + 32), DS_I16(ds, other + 30),
                         DS_I16(ds, player + 32));
}

/* orig 11BC:195C: projected relative direction in the alternate camera mode. */
uint16_t hud_bearing_x(uint8_t *ds)
{
    uint16_t p = DS_U16(ds, DS_PLAYER);
    uint16_t heading = DS_U16(ds, p + 6) + DS_U16(ds, p + 8);
    uint16_t angle = (uint16_t)(indicator_direction(ds) - heading + 511) & 511;
    int16_t signed_angle = angle < 256 ? (int16_t)angle : (int16_t)(angle - 512);
    return (uint16_t)((signed_angle >> 1) + DS_U16(ds, DS_VIEW_CENTRE_X));
}

/* orig 11BC:19AE. The line routine's returned pen state feeds the second stroke. */
static uint16_t bearing_tick_dx(Game *g, uint16_t x)
{
    uint8_t *ds = g->ds;
    uint16_t y = DS_U16(ds, DS_VIEW_HEIGHT) + 5;
    DS_U8(ds, DS_FILL_COLOUR) = 0;
    DS_U16(ds, DS_PEN_X) = x - 2;
    DS_U16(ds, DS_PEN_Y) = y;
    line_to(ds, g->planes, x, (uint16_t)(y - 3));
    uint16_t next_x = DS_U16(ds, DS_PEN_X) + 2;
    uint16_t next_y = DS_U16(ds, DS_PEN_Y) + 3;
    return (uint16_t)(line_to_registers(ds, g->planes, next_x, next_y) >> 16);
}

void hud_bearing_tick(Game *g, uint16_t x)
{
    (void)bearing_tick_dx(g, x);
}

/* orig 11BC:181B, with its local helpers. Timer and history side effects are part
 * of this rendering pass, including the player-specific second indicator gate. */
uint16_t hud_draw_indicators_dx(Game *g, uint16_t dx)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 1) || DS_U8(ds, DS_CAMERA_MODE)) {
        if (DS_U8(ds, DS_PRACTICE_MODE) || DS_U8(ds, DS_COMPANION_ACTIVE) || DS_U8(ds, DS_OPPONENT_ACTIVE))
            return dx;
        return bearing_tick_dx(g, hud_bearing_x(ds));
    }
    static const uint16_t history[] = {0x7B66, 0x7B4A, 0x7B58};
    static const uint16_t timer[] = {0x7AC4, 0x7AC2, 0x7AC3};
    static const uint16_t direction[] = {0x7B64, 0x7B48, 0x7B56};
    static const uint8_t colour[] = {11, 15, 4};
    for (unsigned i = 0; i < 3; ++i) {
        if ((i == 1 && DS_U16(ds, DS_PLAYER) == 0x04D4) || !DS_U8(ds, timer[i])) {
            dx = indicator_erase_dx(g, history[i], dx);
            continue;
        }
        player = DS_U16(ds, DS_PLAYER);
        uint16_t heading = DS_U16(ds, player + 6) + DS_U16(ds, player + 8);
        uint16_t angle = (uint16_t)(511 - (heading - DS_U16(ds, direction[i]))) & 511;
        uint8_t pen = i == 0 && DS_U8(ds, 0x1152) ? 15 : colour[i];
        dx = (uint16_t)(hud_compass_needle_registers(g, history[i], angle, pen, dx) >> 16);
        --DS_U8(ds, timer[i]);
    }
    if (DS_U8(ds, DS_PRACTICE_MODE) || (DS_U16(ds, DS_PLAYER) != 0x04D4 && DS_U8(ds, DS_COMPANION_ACTIVE))
        || DS_U8(ds, DS_OPPONENT_ACTIVE)) {
        return indicator_erase_dx(g, 0x7B72, dx);
    }
    player = DS_U16(ds, DS_PLAYER);
    uint16_t heading = DS_U16(ds, player + 6) + DS_U16(ds, player + 8);
    uint16_t angle = (uint16_t)(511 - (heading - indicator_direction(ds))) & 511;
    return (uint16_t)(hud_compass_needle_registers(g, 0x7B72, angle, 10, dx) >> 16);
}

void hud_draw_indicators(Game *g)
{
    (void)hud_draw_indicators_dx(g, 0);
}
