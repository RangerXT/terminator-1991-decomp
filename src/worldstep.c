/* B5F9 world-step controller, composed from verified native AI/motion.
 * Modal panels and presentation/streaming use host calls. */
#include "term.h"

static int service(Game *g, const OpponentServices *host, uint16_t op)
{
    return !host || !host->call || host->call(g, op, 0, host->user) == UINT32_MAX ? -1 : 0;
}

/* DD56: normalized position, one of three native movement modes or either
 * untranslated modal panel, then native steering/movement. */
int companion_step_with_services(Game *g, const OpponentServices *host)
{
    uint16_t mode = DS_U16(g->ds, DS_COMPANION_ORDER);
    if (mode > 4)
        return -1;
    position_normalize_companion(g->ds);
    if (mode <= 2)
        companion_choose_behavior(g->ds, mode);
    else if (service(g, host, mode == 3 ? OS_COMPANION_PANEL3 : OS_COMPANION_PANEL4))
        return -1;
    companion_move(g);
    return 0;
}

int world_step(Game *g, const OpponentServices *host, const VehicleServices *vehicle)
{
    uint8_t *ds = g->ds;
    if (!(DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1) && !vehicle)
        return -1;
    world_clock_step(g);
    if (!DS_U8(ds, DS_OPPONENT_ACTIVE))
        DS_U8(ds, 0x034B) = 0;
    if (!DS_U8(ds, DS_LINK_GAME)) {
        if (DS_U16(ds, DS_VEHICLE) != 0x0508) {
            if (DS_U8(ds, DS_PRACTICE_MODE))
                return 0;
            if (opponent_controller(g, vehicle))
                return -1;
            vehicle_follow_route(g);
            if (DS_U8(ds, 0x1152) || position_relative_actor(ds))
                return 0;
            return companion_ai(g, vehicle);
        }
        if (!DS_U8(ds, DS_PRACTICE_MODE)) {
            if (opponent_controller_slow(g, host, vehicle))
                return -1;
            vehicle_follow_route(g);
        }
    } else if (!position_relative_vehicle(g) && !DS_U8(ds, 0xAF52)) {
        if (position_relative_actor(ds))
            return 0;
    }
    if (DS_U16(ds, DS_PLAYER) == 0x04D4)
        return companion_step_with_services(g, host);
    return 0;
}

int world_step_on_foot(Game *g, const OpponentServices *host)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return world_step(g, host, NULL);
}
