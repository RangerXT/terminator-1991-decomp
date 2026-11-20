/* Driving controller and remaining transmission/motion leaves (3269..36A8). */
#include "term.h"

void driving_brake(uint8_t *ds, uint16_t actor)
{
    if (!DS_U8(ds, KEY_DOWN(SC_RBRACKET)))
        return;
    DS_U16(ds, actor + 12) -= DS_U8(ds, KEY_DOWN(SC_RSHIFT)) ? 2 : 1;
    if (DS_I16(ds, actor + 12) < 0)
        DS_U16(ds, actor + 12) = 0;
    if (DS_U8(ds, KEY_DOWN(SC_RSHIFT))) {
        DS_U16(ds, actor + 10)--;
        if (DS_I16(ds, actor + 10) < 0)
            DS_U16(ds, actor + 10) = 0;
    }
    if (DS_U8(ds, 0x0347))
        DS_U8(ds, 0x0347) = 1;
}

void driving_smooth_speed(Game *g, uint16_t actor)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x0347)) {
        DS_U8(ds, 0x0347)--;
        return;
    }
    if (DS_U8(ds, 0x114A)) {
        if (!DS_U16(ds, actor + 12)) {
            DS_U8(ds, 0x0347) = 4;
            if (!DS_U8(ds, 0x114B)) {
                DS_U8(ds, 0x114C) = 0;
                DS_U8(ds, DS_TEXT_COLOUR) = 0;
                DS_U8(ds, 0x5A23) = 7;
                hud_field_marker(g);
            }
            return;
        }
        DS_U16(ds, actor + 12)--;
    }
    if (!(DS_U8(ds, actor + 14) & 8) && !DS_U8(ds, KEY_DOWN(SC_BACKSPACE)) && !DS_U8(ds, 0x114A)
        && !DS_U16(ds, actor + 12))
        DS_U8(ds, 0x114A) = DS_U8(ds, 0x114B) = 255;
    uint16_t speed = DS_U16(ds, actor + 10), wanted = DS_U16(ds, actor + 12);
    if (speed == wanted)
        return;
    if (speed > wanted) {
        DS_U16(ds, actor + 10)--;
        DS_U8(ds, 0x0347) = 4;
    } else if (DS_U8(ds, KEY_DOWN(SC_UP))) {
        DS_U16(ds, actor + 10)++;
        DS_U8(ds, 0x0347) = 3;
    }
}

void driving_displace(uint8_t *ds, uint16_t actor)
{
    int16_t speed = DS_I16(ds, actor + 10);
    if (DS_U16(ds, DS_WARNING_COUNTDOWN))
        speed >>= 1;
    speed = (int16_t)(uint16_t)(speed * 2);
    if (!speed)
        return;
    if (DS_U8(ds, 0x5A24))
        speed = (int16_t)(uint16_t)-speed;
    speed = (int16_t)(uint16_t)(speed * 2);
    uint16_t index = DS_U16(ds, actor + 6) * 2;
    int16_t dx = mul_hi(speed, DS_I16(ds, 0x4188 + index)), dz = mul_hi(speed, DS_I16(ds, 0x4288 + index));
    uint32_t x = DS_U16(ds, actor + 34) | ((uint32_t)DS_U16(ds, actor + 36) << 16),
             z = DS_U16(ds, actor + 42) | ((uint32_t)DS_U16(ds, actor + 44) << 16);
    x += (int32_t)dx;
    z -= (int32_t)dz;
    DS_U16(ds, actor + 34) = x;
    DS_U16(ds, actor + 36) = x >> 16;
    DS_U16(ds, actor + 42) = z;
    DS_U16(ds, actor + 44) = z >> 16;
}

void driving_transmission(Game *g, uint16_t actor)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x114A) && !DS_U8(ds, 0x114B))
        return;
    if ((DS_U8(ds, actor + 14) & 8) || DS_U8(ds, KEY_DOWN(SC_BACKSPACE))) {
        uint32_t key = driving_gear_key(ds);
        if (!(key & 0x10000)) {
            uint16_t gear = key;
            DS_U8(ds, 0x5A23) = 7;
            hud_field_marker(g);
            DS_U16(ds, 0x0414) = gear;
            uint16_t rate = DS_U16(ds, DS_U16(ds, 0x0412) + gear * 2);
            if (rate == 65535)
                goto braking;
            if ((int16_t)rate < 0) {
                if (DS_U8(ds, 0x5A24))
                    goto redraw;
                if (DS_I16(ds, actor + 10) > 10)
                    goto stop;
                if (DS_I16(ds, actor + 10) > 4)
                    goto braking;
                DS_U8(ds, 0x5A24) = 255;
                DS_U8(ds, DS_FORCE_REDO) = 255;
                DS_U8(ds, 0x114A) = DS_U8(ds, 0x114B) = 0;
                DS_U16(ds, 0x5A40) = -rate;
                goto redraw;
            }
            if (DS_U8(ds, 0x5A24)) {
                if (DS_I16(ds, actor + 10) > 10)
                    goto stop;
                if (DS_I16(ds, actor + 10) > 4)
                    goto braking;
                DS_U8(ds, 0x5A24) = 0;
            }
            DS_U8(ds, 0x114A) = DS_U8(ds, 0x114B) = 0;
            DS_U16(ds, 0x5A40) = rate;
            goto redraw;
        braking:
            DS_U8(ds, 0x114A) = DS_U8(ds, 0x114B) = 255;
        redraw:
            DS_U8(ds, 0x5A23) = 12;
            hud_field_marker(g);
        }
    }
    if (DS_U8(ds, 0x00B9))
        goto shut_down;
    int16_t target = DS_I16(ds, 0x5A40), speed = DS_I16(ds, actor + 10);
    if (target < speed) {
        if (DS_U8(ds, 0x114A))
            goto done;
        if (!target) {
            if (speed < 5)
                goto zero_speed;
            if (speed > 15)
                goto stop;
            goto shut_down;
        }
        DS_U8(ds, DS_TEXT_COLOUR) = 4;
        DS_U16(ds, 0x0416)--;
        return;
    }
    if (DS_U8(ds, 0x114A) || (DS_U8(ds, actor + 14) & 8) || DS_U8(ds, KEY_DOWN(SC_BACKSPACE)))
        goto done;
    target = (uint16_t)(target - DS_U16(ds, 0x0414) * 3);
    if (target <= 0 || DS_I16(ds, actor + 12) >= target)
        goto done;
    DS_U8(ds, 0x114A) = 255;
    goto done;
stop:
    DS_U16(ds, 0x0416) = 0;
    DS_U8(ds, 0x114A) = 255;
    goto done;
shut_down:
    DS_U8(ds, 0x00B9) = 0;
    DS_U16(ds, 0x0416) = 0;
    DS_U8(ds, 0x114C) = 0;
zero_speed:
    DS_U16(ds, actor + 12) = DS_U16(ds, actor + 10) = 0;
done:
    DS_U8(ds, DS_TEXT_COLOUR) = 15;
}

/* 3684: five native player hits, followed by external 02B5(BX=1) transition.
 * Return -1 for an unavailable exit; preceding damage remains applied. */
int driving_damage_exit(Game *g, uint16_t actor, const OpponentServices *host)
{
    if (DS_I16(g->ds, actor + 48) > 0)
        return 0;
    DS_U16(g->ds, DS_SCREEN_NOISE) = 10;
    for (unsigned i = 0; i < 5; ++i)
        player_hit_native(g, 10);
    return !host || !host->call || host->call(g, OS_PLAYER_TRANSITION, 1, host->user) == UINT32_MAX ? -1 : 0;
}

/* 3269: the native controller, with only 02B5 destruction/exit remaining external.
 * Sound events carry the source 80E9 playback flag in b (engine start uses FF). */
int driving_step_dx(Game *g, const OpponentServices *host, uint32_t *dx)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    player_position_backup(ds);
    if (dx)
        *dx = DS_U16(ds, player + 44);
    if (DS_U8(ds, 0x114C)) {
        if (!(player_movement_gate(ds, DS_U16(ds, player + 42)) & 0x10000)) {
            driving_steer(ds, player);
            if (!DS_U16(ds, 0x0416))
                DS_U8(ds, 0x114A) = 255;
            else {
                driving_accelerate(ds, player);
                driving_transmission(g, player);
            }
            driving_brake(ds, player);
        }
        driving_smooth_speed(g, player);
        driving_displace(ds, player);
        position_normalize(g, player);
        player_keep_inside(g);
        if (dx)
            *dx = DS_I16(ds, player + 48) <= 0 ? ORIGINAL_DX_UNKNOWN : (uint16_t)(1024 - DS_U16(ds, player + 4));
        return driving_damage_exit(g, player, host);
    }
    if (DS_U8(ds, KEY_DOWN(SC_S))) {
        if (!DS_U8(ds, 0xAA94)) {
            DS_U8(ds, 0xAA94) = 255;
            DS_U8(ds, 0x80E9) = 255;
            event_push(EV_SOUND, 9, 255);
            DS_U8(ds, 0x80E9) = 0;
        }
        DS_U8(ds, 0x0347)++;
        if (!DS_U16(ds, DS_FUEL) || DS_U8(ds, 0x0347) < 10)
            return 0;
        event_push(EV_SOUND, 8, DS_U8(ds, 0x80E9));
        DS_U8(ds, 0x114C) = 255;
        DS_U16(ds, player + 10) = DS_U16(ds, player + 12) = DS_U16(ds, 0x5A40) = 0;
        DS_U8(ds, 0x114A) = DS_U8(ds, 0x114B) = 255;
        DS_U16(ds, 0x0414) = 4;
        DS_U8(ds, DS_TEXT_COLOUR) = 14;
    }
    if (DS_U8(ds, 0xAA94))
        DS_U8(ds, 0xAA94) = 0;
    DS_U8(ds, 0x0347) = 5;
    return 0;
}

int driving_step(Game *g, const OpponentServices *host)
{
    return driving_step_dx(g, host, NULL);
}
