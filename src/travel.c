/* Fast-travel controllers. Untranslated simulation/IO runs through an explicit host hook. */
#include "term.h"

static uint32_t travel_call(Game *g, const TravelServices *host, uint16_t service, uint16_t argument)
{
    if (!host || !host->call)
        return UINT32_MAX;
    return host->call(g, service, argument, host->user);
}

/* orig B588: repeat a world step, preserving the original zero-count LOOP behavior.
 * Result follows TR_SIMULATE's convention: remaining CX and carry in bit 16. */
uint32_t travel_simulate(Game *g, const TravelServices *host, uint16_t ticks)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0xDE3C) = 0x80;
    DS_U8(ds, 0xDE3D) = 255;
    uint16_t remaining = ticks;
    uint32_t result;
    for (;;) {
        if (travel_call(g, host, TR_WORLD_STEP, 0) == UINT32_MAX)
            return UINT32_MAX;
        if (DS_U8(ds, DS_OPPONENT_ACTIVE)) {
            result = 0x10000 | remaining;
            break;
        }
        if (!--remaining) {
            result = 0;
            break;
        }
    }
    DS_U8(ds, 0xDE3C) = 0;
    DS_U8(ds, 0xDE3D) = 0;
    return result;
}
/* orig D2BE: coordinate writes and normalization are C; cell loading is external. */
int travel_apply_destination(Game *g, const TravelServices *host)
{
    map_write_destination_position(g->ds);
    position_normalize(g, DS_U16(g->ds, DS_PLAYER));
    DS_U16(g->ds, DS_VISIBLE_CELL) = 65535;
    return travel_call(g, host, TR_LOAD_CELLS, 0) == UINT32_MAX ? -1 : 0;
}

/* orig D177: advance simulation, apply a complete or interrupted destination, and
 * retry the remainder when C42F returns carry. A host result of UINT32_MAX means
 * that a required untranslated operation is unavailable; no success is reported. */
static int travel_run_impl(Game *g, const TravelServices *host, int native_opponents)
{
    uint8_t *ds = g->ds;
    for (;;) {
        uint16_t player = DS_U16(ds, DS_PLAYER), distance = DS_U16(ds, 0xE272);
        if (distance < 100)
            return travel_apply_destination(g, host);
        uint16_t speed = (uint16_t)(DS_U16(ds, player + 10) * 2);
        if (!speed)
            return 0;
        uint16_t ticks = (uint16_t)((distance / speed) << 2);
        if (!ticks)
            return travel_apply_destination(g, host);
        uint32_t result = native_opponents ? travel_simulate(g, host, ticks) : travel_call(g, host, TR_SIMULATE, ticks);
        if (result == UINT32_MAX)
            return -1;
        if (!(result & 0x10000))
            return travel_apply_destination(g, host);
        uint16_t remaining = (uint16_t)result;
        if (remaining >= 20)
            DS_U8(ds, DS_TRAVEL_MESSAGE) = 255;
        uint32_t dividend = (uint32_t)(uint16_t)(ticks - remaining) * 100;
        uint32_t quotient = dividend / ticks;
        uint16_t percent = quotient > 65535 ? (uint16_t)dividend : (uint16_t)quotient;
        if (!percent)
            return 0;
        for (unsigned i = 0; i < 4; ++i)
            DS_U16(ds, 0xE276 + 2 * i) = DS_U16(ds, 0xE26A + 2 * i);
        player = DS_U16(ds, DS_PLAYER);
        static const uint8_t fields[] = {30, 32, 0, 4};
        for (unsigned i = 0; i < 4; ++i) {
            uint16_t base = DS_U16(ds, player + fields[i]);
            int16_t delta = (int16_t)(DS_U16(ds, 0xE26A + 2 * i) - base);
            int32_t product = (int32_t)delta * (int16_t)percent;
            DS_U16(ds, 0xE26A + 2 * i) = (uint16_t)(base + idiv_or_skip(product, 100));
        }
        if (travel_apply_destination(g, host))
            return -1;
        result = native_opponents ? ((uint32_t)opponent_check_travel_interrupt(g) << 16)
                                  : travel_call(g, host, TR_CHECK_INTERRUPT, 0);
        if (result == UINT32_MAX)
            return -1;
        if (result & 0x10000) {
            for (unsigned i = 0; i < 4; ++i)
                DS_U16(ds, 0xE26A + 2 * i) = DS_U16(ds, 0xE276 + 2 * i);
            map_destination_measure(ds);
            continue;
        }
        if (native_opponents) {
            if (DS_U16(ds, DS_PLAYER) != 0x0508)
                opponent_place_ahead(g);
            else {
                opponent_place_flank(g);
                opponent_place_companion(g);
            }
        } else if (DS_U16(ds, DS_PLAYER) != 0x0508) {
            if (travel_call(g, host, TR_OTHER_INTERRUPT, 0) == UINT32_MAX)
                return -1;
        } else {
            if (travel_call(g, host, TR_TERMINATOR_INTERRUPT, 0) == UINT32_MAX)
                return -1;
            if (travel_call(g, host, TR_TERMINATOR_FOLLOWUP, 0) == UINT32_MAX)
                return -1;
        }
        return 0;
    }
}

/* Preserve the original explicit-host API for clients supplying encounter work. */
int travel_run(Game *g, const TravelServices *host)
{
    return travel_run_impl(g, host, 0);
}

/* D177 with B588, C42F, BBF1/C35F/DC7B all native. The host supplies only
 * world-step B5F9 and cell loading 3B88, including their actual state changes. */
int travel_run_native_opponents(Game *g, const TravelServices *host)
{
    return travel_run_impl(g, host, 1);
}

/* orig D265: move away from a blocked arrival until the collision check clears. */
int travel_clear_arrival(Game *g, const TravelServices *host)
{
    uint8_t *ds = g->ds;
    for (;;) {
        DS_U8(ds, 0x8683) = 255;
        uint16_t player = DS_U16(ds, DS_PLAYER);
        uint32_t result = travel_call(g, host, TR_COLLISION, player);
        if (result == UINT32_MAX)
            return -1;
        if (!(result & 0x10000))
            break;
        player = DS_U16(ds, DS_PLAYER);
        uint16_t heading = (uint16_t)(DS_U16(ds, player + 6) * 2);
        int16_t dz = mul_hi(200, DS_I16(ds, 0x4288 + heading));
        int16_t dx = mul_hi(200, DS_I16(ds, 0x4188 + heading));
        uint32_t z = DS_U16(ds, player + 42) | ((uint32_t)DS_U16(ds, player + 44) << 16);
        uint32_t x = DS_U16(ds, player + 34) | ((uint32_t)DS_U16(ds, player + 36) << 16);
        z -= (uint32_t)(int32_t)dz;
        x += (uint32_t)(int32_t)dx;
        DS_U16(ds, player + 42) = (uint16_t)z;
        DS_U16(ds, player + 44) = (uint16_t)(z >> 16);
        DS_U16(ds, player + 34) = (uint16_t)x;
        DS_U16(ds, player + 36) = (uint16_t)(x >> 16);
        position_normalize(g, player);
        if (travel_call(g, host, TR_LOAD_CELLS, 0) == UINT32_MAX)
            return -1;
    }
    DS_U8(ds, 0x8683) = 0;
    if (DS_U16(ds, DS_PLAYER) == 0x04D4 && DS_U16(ds, DS_COMPANION_ORDER) == 2)
        if (travel_call(g, host, TR_ARRIVAL_FOLLOWUP, 0) == UINT32_MAX)
            return -1;
    return 0;
}
/* Bind the verified native world step into B588 while retaining only cell IO
 * and the world's explicit presentation/modal service boundaries. */
typedef struct NativeTravelWorld {
    const TravelServices *io;
    const OpponentServices *platform;
    const VehicleServices *vehicle;
} NativeTravelWorld;

static uint32_t native_world_call(Game *g, uint16_t service, uint16_t arg, void *user)
{
    NativeTravelWorld *host = (NativeTravelWorld *)user;
    if (service == TR_WORLD_STEP)
        return world_step(g, host->platform, host->vehicle) < 0 ? UINT32_MAX : 0;
    return travel_call(g, host->io, service, arg);
}

int travel_run_native_simulation(Game *g, const TravelServices *io, const OpponentServices *platform,
                                 const VehicleServices *vehicle)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1) && !vehicle)
        return -1;
    NativeTravelWorld adapter = {io, platform, vehicle};
    TravelServices host = {native_world_call, &adapter};
    return travel_run_impl(g, &host, 1);
}

int travel_run_native_world(Game *g, const TravelServices *io, const OpponentServices *platform)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return travel_run_native_simulation(g, io, platform, NULL);
}

/* B588 with the native world step: what healing in the damage panel runs. Result as
 * travel_simulate (remaining ticks, carry in bit 16 when the opponent showed up). */
uint32_t travel_simulate_world(Game *g, const TravelServices *io, const OpponentServices *platform,
                               const VehicleServices *vehicle, uint16_t ticks)
{
    NativeTravelWorld adapter = {io, platform, vehicle};
    TravelServices host = {native_world_call, &adapter};
    return travel_simulate(g, &host, ticks);
}
