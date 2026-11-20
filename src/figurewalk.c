/* Civilian movement, from 0000:AB77 and 14A7:000C. */
#include "term.h"

static void update_view_recoil(uint8_t *ds)
{
    if (DS_U8(ds, 0xB66D) && !--DS_U8(ds, 0xB66D))
        DS_U16(ds, DS_VIEW_CENTRE_Y) -= 8;
}

static void next_position(const uint8_t *ds, uint16_t figure, uint16_t *x, uint16_t *z)
{
    uint16_t angle = DS_U16(ds, figure + 6) * 2;
    int16_t speed = (uint16_t)(DS_U16(ds, figure + 10) * 2);
    *x += mul_hi(speed, DS_I16(ds, DS_SINE_TABLE + angle));
    *z += mul_hi(speed, DS_I16(ds, DS_SINE_TABLE + angle + 0x100));
}

/* AFD0 leaves carry clear on ordinary removal. It can leave it set on an
 * out-of-range ID or if the deferred-respawn counter wraps in AD4B. */
static uint8_t remove_civilian(Game *g, uint16_t record)
{
    uint8_t *ds = g->ds;
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT), id = DS_U16(ds, record + 8) >> 1;
    uint16_t deferred = DS_U16(ds, 0x116E);
    if (figure_remove(ds, record)) {
        figure_spawn(g, 1, 1);
        return !DS_U16(ds, 0xB82A) && deferred == 0xFFFF;
    }
    return count && (int16_t)(count - id) <= 0 && count < id;
}

/* 14A7:000C. Find a heading on the overhead map, then check the fine grid. */
static int civilian_steer(Game *g, uint16_t figure, uint16_t record)
{
    uint8_t *ds = g->ds;
    for (unsigned i = 0; i < 8; ++i) {
        uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
        next_position(ds, figure, &x, &z);
        if ((uint8_t)figure_map_sample(g, x, z) != 1)
            break;
        DS_U16(ds, figure + 6) = (DS_U16(ds, figure + 6) + 128) & 511;
    }
    int16_t gx = (int16_t)(uint16_t)(DS_U16(ds, record) + 8) >> 4;
    int16_t gz = (int16_t)(uint16_t)(DS_U16(ds, record + 4) + 8) >> 4;
    uint16_t address = 0x9000 - (uint8_t)(gz + 64) * 192 + (gx + 64) - 0x0182;
    if (address >= 0x9000) {
        /* 00D9 removes here, before the caller handles carry and removes again. */
        remove_civilian(g, record);
        DS_U8(ds, 0x8681) = 255;
        return 1;
    }
    uint16_t seg = DS_U16(ds, DS_SEG_COLLISION);
    if (*far_ptr(g, seg, address))
        return 1;
    for (unsigned i = 0; i < 9; ++i) {
        uint16_t sector = (DS_U16(ds, figure + 6) >> 5) & 0xFFFE;
        if (!*far_ptr(g, seg, (uint16_t)(address + DS_U16(ds, 0xBA7A + sector))))
            return 0;
        DS_U16(ds, figure + 6) = (DS_U16(ds, figure + 6) + 64) & 511;
    }
    return 1;
}

/* AEE9, including bearing, flight from danger and vehicle collision. Return CF. */
uint8_t civilian_prepare_move(Game *g, uint16_t figure, uint16_t record)
{
    uint8_t *ds = g->ds;
    uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PROBE_Z) = z;
    collision_grid_address(ds);
    if (DS_U8(ds, 0x8681))
        return remove_civilian(g, record);

    uint16_t actor = DS_U16(ds, DS_PLAYER);
    uint16_t px = DS_U16(ds, actor), pz = DS_U16(ds, actor + 4);
    uint16_t angle = angle_between(ds, x, z, px, pz);
    DS_U16(ds, figure + 14) = angle;
    if (DS_U8(ds, 0xB69F) || DS_U8(ds, DS_IN_BATTLE)) {
        DS_U16(ds, figure + 6) = (angle + 256) & 511;
        DS_U16(ds, figure + 10) = 8;
    }
    uint16_t distance = approx_distance(x, z, px, pz);
    DS_U16(ds, figure + 8) = distance;
    if ((DS_U8(ds, actor + 14) & 2) && distance < 60 && DS_U16(ds, actor + 10) >= 5) {
        event_push(EV_SOUND, DS_U8(ds, figure) & 4 ? 6 : 7, DS_U8(ds, 0x80E9));
        ++DS_U16(ds, 0x0386);
        DS_U16(ds, actor + 48) -= 2;
        if (!DS_U8(ds, 0xB66D))
            DS_U16(ds, DS_VIEW_CENTRE_Y) += 8;
        DS_U8(ds, 0xB66D) = 2;
        return remove_civilian(g, record);
    }
    if (civilian_steer(g, figure, record))
        return remove_civilian(g, record);
    return 0;
}

/* AB77. The removal path decrements twice and can reuse the same slot. */
void civilians_move(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0xB6A1) = 0;
    update_view_recoil(ds);
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT), figure = 0x0B30, record = 0x0DF0;
    while (count) {
        if (!DS_U16(ds, record + 6))
            break;
        if (DS_U8(ds, figure) & 6) {
            if (!civilian_prepare_move(g, figure, record)) {
                uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
                next_position(ds, figure, &x, &z);
                DS_U16(ds, record) = x;
                DS_U16(ds, record + 4) = z;
            }
            if (DS_U8(ds, 0xB6A1)) {
                DS_U8(ds, 0xB6A1) = 0;
                if (!--count)
                    break;
                --count;
                continue;
            }
        }
        figure += 22;
        record += 12;
        --count;
    }
}

/* AFA2: update bit zero from the line walk's carry, after clobbering its inputs. */
static void armed_line_of_sight(Game *g, uint16_t figure, uint16_t record)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, actor);
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, actor + 4);
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, record);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, record + 4);
    if (collision_line_blocker(g))
        DS_U8(ds, figure) &= 0xFE;
    else
        DS_U8(ds, figure) |= 1;
}

static uint8_t armed_select_position(uint8_t *ds, uint16_t record, uint16_t want)
{
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, record);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, record + 4);
    return figure_select_position(ds, 0, want);
}

static int16_t abs_diff16(uint16_t a, uint16_t b)
{
    int16_t delta = (uint16_t)(a - b);
    return delta < 0 ? (uint16_t)-delta : delta;
}

/* A69E: when the destination has been reached, use the grid search's last
 * coordinates even if that search set carry; steering decides removal. */
static int armed_choose_heading(Game *g, uint16_t figure, uint16_t record)
{
    uint8_t *ds = g->ds;
    uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
    DS_U16(ds, 0xB820) = DS_U16(ds, figure + 10);
    DS_U16(ds, 0xB824) = DS_U16(ds, figure + 6);
    if (abs_diff16(x, DS_U16(ds, figure + 2)) <= 10 && abs_diff16(z, DS_U16(ds, figure + 4)) <= 10) {
        armed_select_position(ds, record, !(DS_U8(ds, figure) & 1));
        DS_U16(ds, figure + 2) = DS_U16(ds, DS_POINT_X);
        DS_U16(ds, figure + 4) = DS_U16(ds, DS_POINT_Z);
    } else {
        DS_U16(ds, DS_PEN_X) = x;
        DS_U16(ds, DS_PROBE_Z) = z;
        DS_U16(ds, DS_POINT_X) = DS_U16(ds, figure + 2);
        DS_U16(ds, DS_POINT_Z) = DS_U16(ds, figure + 4);
    }
    return collision_steer(g);
}

/* A7E5: distance changes pace; the vehicle figure decelerates up close. */
static void armed_adjust_speed(uint8_t *ds, uint16_t figure, uint16_t record)
{
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    int vehicle_figure = DS_U8(ds, figure) & 16;
    uint16_t speed = DS_U16(ds, actor + 10);
    if (!(DS_U8(ds, actor + 14) & 1) && !vehicle_figure)
        speed = 10;
    uint16_t dist =
        approx_distance(DS_I16(ds, actor), DS_I16(ds, actor + 4), DS_I16(ds, record), DS_I16(ds, record + 4));
    DS_U16(ds, figure + 8) = dist;
    if (dist >= 512) {
        if (dist < 1024)
            speed *= 2;
        speed -= 2;
        DS_U16(ds, figure + 10) = speed < 2 ? 7 : speed;
    } else if (!vehicle_figure)
        DS_U16(ds, figure + 10) = speed;
    else {
        DS_U16(ds, figure + 10) -= 2;
        if (DS_I16(ds, figure + 10) < 0)
            DS_U16(ds, figure + 10) = 0;
    }
}

/* ABF1: rate limit, vehicle/body damage, armour wear and a visual shot. CF is
 * set for a skipped shot, which prevents the follow-up random draw at A5BE. */
uint8_t armed_figure_fire(Game *g, uint16_t figure, uint16_t record)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0xAA83))
        return 1;
    if (DS_U16(ds, figure + 12)) {
        --DS_U16(ds, figure + 12);
        return 1;
    }
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    uint16_t chance;
    if (DS_U8(ds, actor + 14) & 2) {
        chance = random_word(ds);
        DS_U16(ds, figure + 12) = (chance & 31) + 15;
        if ((int16_t)chance > (int16_t)0x9C40)
            goto visual;
        DS_U16(ds, actor + 48) -= DS_U16(ds, 0xB826);
        if ((int16_t)chance >= 2000)
            goto visual;
    }
    chance = random_word(ds);
    DS_U16(ds, figure + 12) = (chance & 31) + 15;
    uint16_t limit = 3500 - DS_U16(ds, figure + 8);
    if ((int16_t)limit < 0)
        limit = 100;
    if (DS_U8(ds, 0xAA98)) {
        if (!--DS_U8(ds, actor + 51)) {
            DS_U8(ds, 0xAA98) = 0;
            hud_message(g, 0xB6A2);
            inventory_remove(ds, 15);
        }
        limit -= 100;
        if ((int16_t)limit < 0)
            limit = 50;
    }
    if ((chance >> 4) < limit)
        player_hit_native(g, DS_U16(ds, 0xB826));
visual:;
    actor = DS_U16(ds, DS_PLAYER);
    uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
    uint16_t angle = angle_between(ds, x, z, DS_I16(ds, actor), DS_I16(ds, actor + 4));
    DS_U16(ds, 0x7B56) = (angle + 256) & 511;
    DS_U8(ds, 0x7AC3) = 10;
    weapon_visual_insert(ds, x, DS_U16(ds, actor + 2) - 3, z, angle);
    event_push(EV_SOUND, DS_U8(ds, 0x11CD) ? 3 : 5, DS_U8(ds, 0x80E9));
    return 0;
}

static void armed_take_step(uint8_t *ds, uint16_t figure, uint16_t record)
{
    int vehicle_figure = DS_U8(ds, figure) & 16;
    if (vehicle_figure) {
        uint16_t actor = DS_U16(ds, DS_PLAYER);
        DS_U16(ds, figure + 2) = DS_U16(ds, actor);
        DS_U16(ds, figure + 4) = DS_U16(ds, actor + 4);
    }
    uint16_t x = DS_U16(ds, record), z = DS_U16(ds, record + 4);
    next_position(ds, figure, &x, &z);
    DS_U16(ds, record) = x;
    DS_U16(ds, record + 4) = z;
    uint16_t wanted = angle_between(ds, x, z, DS_I16(ds, figure + 2), DS_I16(ds, figure + 4));
    if (!vehicle_figure)
        DS_U16(ds, figure + 6) = wanted;
    else {
        uint16_t old = DS_U16(ds, figure + 6);
        int16_t diff = (uint16_t)(old - wanted);
        if (!diff)
            return;
        int16_t biased = (uint16_t)(diff + 256);
        int forward = biased >= 0 && biased <= 512;
        DS_U16(ds, figure + 6) = (old + ((diff < 0) == forward ? 4 : -4)) & 511;
    }
}

/* A70C: switch bodies after the pose selection, which still sees the old state. */
static void armed_update_bodies(uint8_t *ds)
{
    int driving = DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 2;
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT), figure = 0x0B30, record = 0x0DF0;
    for (; count; --count, figure += 22, record += 12) {
        if (driving && !DS_U8(ds, figure)) {
            DS_U8(ds, figure) |= 16;
            DS_U16(ds, record + 6) = 0x2000;
            DS_U16(ds, record + 10) = 30 + 2 * DS_U16(ds, DS_DIFFICULTY);
        } else if (!driving && (DS_U8(ds, figure) & 16)) {
            DS_U16(ds, figure + 10) = 4;
            DS_U8(ds, figure) &= 0xEF;
            DS_U16(ds, record + 6) = 0x4000;
            DS_U16(ds, record + 10) = 2;
        }
    }
}

/* A54E: steering, pursuit/recovery, shots, then sprite and vehicle selection. */
void armed_figures_move(Game *g)
{
    uint8_t *ds = g->ds;
    update_view_recoil(ds);
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT), figure = 0x0B30, record = 0x0DF0;
    if (!count)
        return;
    while (count) {
        if (!(DS_U8(ds, figure) & 6)) {
            armed_line_of_sight(g, figure, record);
            if (armed_choose_heading(g, figure, record)) {
                figure_remove_complete(g, record);
                if (!--count)
                    break;
                --count;
                continue;
            }
            DS_U16(ds, figure + 6) = DS_U16(ds, 0xB824);
            armed_adjust_speed(ds, figure, record);
            if (DS_U8(ds, figure) & 1) {
                if (DS_U8(ds, figure + 1) != 20) {
                    if (DS_U8(ds, figure + 1)) {
                        if (!(DS_U8(ds, figure) & 16))
                            DS_U16(ds, figure + 10) = 1;
                        --DS_U8(ds, figure + 1);
                    }
                    if (!armed_figure_fire(g, figure, record) && (random_word(ds) & 15) >= 10) {
                        if (!armed_select_position(ds, record, 1)) {
                            DS_U8(ds, figure + 1) = 20;
                            goto advance;
                        }
                    } else
                        DS_U8(ds, figure + 1) = 2;
                }
            } else if (DS_U8(ds, figure + 1) != 100) {
                if (DS_U8(ds, figure + 1))
                    --DS_U8(ds, figure + 1);
                else if (DS_U8(ds, figure) & 16) {
                    uint16_t actor = DS_U16(ds, DS_PLAYER), heading = DS_U16(ds, actor + 6) * 2;
                    DS_U16(ds, figure + 2) += mul_hi(2048, DS_I16(ds, DS_SINE_TABLE + heading));
                    DS_U16(ds, figure + 4) += mul_hi(2048, DS_I16(ds, DS_SINE_TABLE + heading + 0x100));
                    DS_U8(ds, figure + 1) = 100;
                    goto advance;
                } else if (!armed_select_position(ds, record, 0)) {
                    DS_U8(ds, figure + 1) = 10;
                    goto advance;
                }
            }
            armed_take_step(ds, figure, record);
        }
    advance:
        figure += 22;
        record += 12;
        --count;
    }
    figure_select_frames(ds);
    armed_update_bodies(ds);
}

/* 06EF: these updates run in order before the new frame list is built. */
int scene_update_world(Game *g, const MapResources *display)
{
    uint8_t *ds = g->ds;
    int has_guided = DS_U16(ds, DS_GUIDED_COUNT) != 0;
    if (DS_U8(ds, DS_LINK_GAME) || (has_guided && DS_U8(ds, DS_CAMERA_MODE) == 1 && (!display || !display->call)))
        return -1;
    figure_feedback_step(g);
    if (has_guided && weapon_guided_projectiles_step_host(g, display))
        return -1;
    armed_figures_move(g);
    civilians_move(g);
    debris_update(g);
    return 0;
}
