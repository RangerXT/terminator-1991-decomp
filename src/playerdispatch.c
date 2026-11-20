/* Main player control dispatch, original 0255..02B5/035D. */
#include "term.h"

static int dispatch_movement(Game *g, const VehicleServices *vehicle, uint32_t *dx)
{
    if (DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1) {
        uint32_t registers = walking_step_registers(g, 0);
        if (dx)
            *dx = registers >> 16;
        return 0;
    }
    OpponentServices transition = {vehicle_transition_service, (void *)vehicle};
    return driving_step_dx(g, &transition, dx);
}

int player_control_step_dx(Game *g, const VehicleServices *vehicle, const TravelServices *stream, uint32_t *dx)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    if (dx)
        *dx = ORIGINAL_DX_UNKNOWN;
    if (DS_U8(ds, KEY_DOWN(SC_W)) && (DS_U8(ds, actor + 14) & 2)) {
        DS_U16(ds, 0x040C) = DS_U16(ds, actor);
        DS_U16(ds, 0x040E) = DS_U16(ds, actor + 4);
        uint16_t damage = DS_U16(ds, actor + 10) >> 3;
        if (damage) {
            actor = player_hit_native_registers(g, damage, actor) >> 16;
            DS_U8(ds, DS_CAR_EXIT_MESSAGE) = 255;
        }
        if (vehicle_park(g, actor))
            return -1;
        DS_U16(ds, DS_VISIBLE_CELL) = 65534;
        if (!stream || !stream->call || stream->call(g, TR_LOAD_CELLS, 0, stream->user) == UINT32_MAX)
            return -1;
    } else {
        if (!DS_U8(ds, KEY_DOWN(SC_D)))
            return dispatch_movement(g, vehicle, dx);
        if (DS_U8(ds, actor + 14) & 2)
            return vehicle_transition(g, 2, vehicle);
    }
    if (vehicle_transition(g, 1, vehicle))
        return -1;
    return travel_clear_arrival_native(g, stream);
}

int player_control_step(Game *g, const VehicleServices *vehicle, const TravelServices *stream)
{
    return player_control_step_dx(g, vehicle, stream, NULL);
}
