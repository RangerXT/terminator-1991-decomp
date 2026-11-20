/* Opponent controllers C21F/B7B6 with native foot/vehicle target combat. */
#include "term.h"

static void disengage(Game *g, uint16_t ax, uint16_t mask)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_OPPONENT_ACTIVE) = 0;
    DS_U16(ds, 0x04D2) = ax & mask;
    world_update_delay(ds);
    DS_U8(ds, 0x034E) = 255;
    DS_U8(ds, 0x7A18) = 0;
    world_displace_vehicle(g);
}

int opponent_controller(Game *g, const VehicleServices *vehicle)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 1) && !vehicle)
        return -1;
    if (!position_relative_vehicle(g)) {
        if (DS_U8(ds, 0x0349)) {
            /* BB2B ends with angle_between, whose DX is the octant DIV remainder. */
            uint32_t bearing = angle_between_state(ds, DS_I16(ds, DS_OPPONENT_X), DS_I16(ds, DS_OPPONENT_Z),
                                                   DS_I16(ds, player), DS_I16(ds, player + 4));
            if (opponent_burst(g, 1, bearing >> 16, vehicle))
                return -1;
            if (!DS_U8(ds, 0x0359))
                DS_U8(ds, 0x034B) = 255;
        } else {
            uint16_t r = random_word(ds);
            if (r >= 0xFFDC) {
                disengage(g, r, 127);
                return 0;
            }
        }
        player = DS_U16(ds, DS_PLAYER);
        uint16_t actor = DS_U16(ds, DS_VEHICLE);
        uint16_t distance = approx_distance(DS_I16(ds, player), DS_I16(ds, player + 4), DS_I16(ds, DS_OPPONENT_X),
                                            DS_I16(ds, DS_OPPONENT_Z));
        uint16_t maximum = DS_U16(ds, actor + 28), remaining = maximum - DS_U16(ds, actor + 26);
        if (distance >= 500 && remaining >= (maximum >> 1) && !DS_U8(ds, 0x034B)) {
            opponent_choose_follow_mode(ds);
            opponent_follow_destination(ds);
            return 0;
        }
        opponent_pick_destination(g);
        if (DS_U8(ds, 0x0349))
            return 0;
        uint32_t state = opponent_openings_state(ds);
        if (!(state & 0x10000))
            disengage(g, state, 127);
        return 0;
    }
    DS_U8(ds, 0x034E) = 255;
    if (!DS_U16(ds, 0x04D2)) {
        if (opponent_check_travel_interrupt(g))
            return 0;
        DS_U16(ds, 0x04D2) = random_word(ds) & 127;
        world_update_delay(ds);
        if (!DS_U8(ds, 0xDE3D) && random_word(ds) < 50000) {
            DS_U8(ds, 0x7A18) = 255;
            world_displace_vehicle(g);
            if (position_relative_vehicle(g))
                return 0;
        } else
            opponent_place_flank(g);
        DS_U8(ds, 0x034E) = 0;
        if (!DS_U8(ds, DS_COMPANION_ACTIVE) && !DS_U8(ds, 0x1152))
            opponent_place_companion(g);
        return 0;
    }
    uint16_t r = random_word(ds), actor = DS_U16(ds, DS_VEHICLE);
    if (r < 0xFE4C)
        return 0;
    if (r < 0xFF46) {
        DS_U8(ds, actor + 50)++;
        opponent_cycle_item(g, 0xDE94);
        if (DS_U16(ds, 0x0556))
            DS_U16(ds, 0x0556)--;
    } else if (r < 0xFFDC) {
        if (!DS_U8(ds, 0x1152) && DS_U16(ds, actor + 26))
            DS_U16(ds, actor + 26)--;
    } else
        DS_U8(ds, actor + 50) += r & 3;
    return 0;
}

/* BFB3: return AX | DX<<16 for the following B7B6 branch. Saved CX/DX are
 * popped into AX/CX to supply the shooter's X/Z to the visual-shot ring. */
uint32_t opponent_fire_at_companion_state(Game *g, uint16_t ax, uint16_t dx)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0xAA83))
        return ax | ((uint32_t)dx << 16);
    ax = random_word(ds);
    uint16_t difficulty = (uint8_t)DS_U16(ds, DS_DIFFICULTY);
    uint16_t threshold = 0xFF14 - DS_U16(ds, 0x0386) * 5 - (difficulty * 257 * 4) + DS_U16(ds, 0x1174);
    if (ax < threshold)
        return ax | ((uint32_t)dx << 16);
    uint8_t latched = DS_U8(ds, 0x0359);
    ax = opponent_select_choice(g, ax);
    if (!latched)
        dx = (dx & 0xFF00) | 4;
    if (!DS_U8(ds, 0x0359))
        return ax | ((uint32_t)dx << 16);
    event_push(EV_SOUND, DS_U8(ds, 0x035F), 0);
    DS_U8(ds, 0x7AC4) = 10;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, 0x7B64) = angle_between(ds, DS_I16(ds, player), DS_I16(ds, player + 4), DS_I16(ds, DS_OPPONENT_X),
                                       DS_I16(ds, DS_OPPONENT_Z));
    uint16_t actor = DS_U16(ds, DS_VEHICLE);
    dx = angle_between(ds, DS_I16(ds, 0x053C), DS_I16(ds, 0x0540), DS_I16(ds, actor), DS_I16(ds, actor + 4));
    weapon_visual_insert(ds, DS_U16(ds, actor), DS_U16(ds, actor + 2), DS_U16(ds, actor + 4), dx);
    ax = random_word(ds);
    if (ax & 4) {
        ax = (uint16_t)((ax & 1) + ((ax >> 8) & 1) + 1 + DS_U16(ds, 0x0556));
        DS_U16(ds, 0x0556) = ax;
        if (ax >= DS_U16(ds, 0x0558)) {
            DS_U8(ds, 0x1158) = 255;
            DS_U8(ds, DS_MISSION_OVER) = 1;
        }
    }
    return ax | ((uint32_t)dx << 16);
}

void opponent_fire_at_companion(Game *g)
{
    opponent_fire_at_companion_state(g, 0, 0);
}

static int scene_service(Game *g, const OpponentServices *host, uint16_t service, uint16_t arg)
{
    return !host || !host->call || host->call(g, service, arg, host->user) == UINT32_MAX ? -1 : 0;
}

/* B7B6: on-foot target path, including the native inventory, companion attack,
 * movement and placement branches. Cutscene, wait, cell IO and camera reset are
 * explicit synchronous services. This does not claim those bodies translated. */
int opponent_controller_slow(Game *g, const OpponentServices *host, const VehicleServices *vehicle)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 1) && !vehicle)
        return -1;
    if (!position_relative_vehicle(g)) {
        uint32_t bearing = angle_between_state(ds, DS_I16(ds, DS_OPPONENT_X), DS_I16(ds, DS_OPPONENT_Z),
                                               DS_I16(ds, player), DS_I16(ds, player + 4));
        uint16_t ax = bearing, dx = bearing >> 16;
        if (!DS_U8(ds, 0xB69F)) {
            if (!DS_U8(ds, 0x034A))
                goto health;
            bearing = opponent_fire_at_companion_state(g, ax, dx);
            ax = bearing;
            dx = bearing >> 16;
        }
        if (DS_U8(ds, 0x0349)) {
            if (opponent_burst(g, 0, dx, vehicle))
                return -1;
            if (!DS_U8(ds, 0x0359))
                DS_U8(ds, 0x034B) = 255;
        } else {
            ax = opponent_select_choice(g, ax);
            if (DS_U8(ds, 0x0359)) {
                ax = random_word(ds);
                if (ax < 0xFFDC)
                    goto health;
            }
            disengage(g, ax, 255);
            return 0;
        }
    health:;
        uint16_t actor = DS_U16(ds, DS_VEHICLE), maximum = DS_U16(ds, actor + 28),
                 remaining = maximum - DS_U16(ds, actor + 26);
        if (remaining >= (maximum >> 4) && !DS_U8(ds, 0x034B)) {
            opponent_choose_follow_mode(ds);
            opponent_follow_destination(ds);
            return 0;
        }
        opponent_pick_destination(g);
        if (DS_U8(ds, 0x0349))
            return 0;
        uint32_t openings = opponent_openings_state(ds);
        if (!(openings & 0x10000))
            disengage(g, openings, 255);
        return 0;
    }
    DS_U8(ds, 0x034E) = 255;
    if (!DS_U16(ds, 0x04D2)) {
        DS_U16(ds, 0x04D2) = random_word(ds) & 255;
        world_update_delay(ds);
        if (!DS_U8(ds, 0xDE3D) && random_word(ds) < 50000) {
            DS_U8(ds, 0x7A18) = 255;
            world_displace_vehicle(g);
            if (position_relative_vehicle(g))
                return 0;
        } else
            opponent_place_ahead(g);
        DS_U8(ds, 0x034E) = 0;
        DS_U8(ds, 0x115C) = 255;
        return 0;
    }
    uint16_t r = random_word(ds), actor = DS_U16(ds, DS_VEHICLE);
    if (r < 0xFE4C)
        return 0;
    if (r < 0xFF46) {
        DS_U8(ds, actor + 50)++;
        opponent_cycle_item(g, 0xDE5A);
        return 0;
    }
    if (r < 0xFFDC) {
        if (DS_U16(ds, actor + 26))
            DS_U16(ds, actor + 26)--;
        return 0;
    }
    if (r < 0xFFF0) {
        DS_U8(ds, actor + 50) += r & 3;
        return 0;
    }
    if (DS_U8(ds, 0x115C) || DS_U8(ds, 0xDE3C) == 0x81)
        return 0;
    DS_U8(ds, 0xDB61) = 3;
    if (scene_service(g, host, OS_CUTSCENE, 0xDE34))
        return -1;
    DS_U8(ds, 0xDB61) = 0;
    if (scene_service(g, host, OS_WAIT, 120))
        return -1;
    DS_U16(ds, DS_VISIBLE_CELL) = 65535;
    if (scene_service(g, host, OS_LOAD_CELLS, 0) || scene_service(g, host, OS_CAMERA_RESET, 0))
        return -1;
    if (DS_U8(ds, 0xDE3C) & 0x80)
        DS_U8(ds, 0xDE3C)++;
    return 0;
}

int opponent_controller_on_foot(Game *g)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return opponent_controller(g, NULL);
}

int opponent_controller_slow_on_foot(Game *g, const OpponentServices *host)
{
    if (!(DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) & 1))
        return -1;
    return opponent_controller_slow(g, host, NULL);
}
