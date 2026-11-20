/* Vehicle transition 02B5, including native resource/HUD and walking/driving tails.
 * BIOS/palette and sound-group bodies remain explicit platform operations. */
#include "term.h"

static int audio_group(Game *g, const VehicleServices *host, uint16_t entry)
{
    return !host->audio || !host->audio->call || host->audio->call(g, entry, 0, host->audio->user) == UINT32_MAX ? -1
                                                                                                                 : 0;
}

static uint32_t transition_service(Game *g, uint16_t op, uint16_t mode, void *user)
{
    if (op != OS_PLAYER_TRANSITION)
        return UINT32_MAX;
    return vehicle_transition(g, mode, (const VehicleServices *)user) < 0 ? UINT32_MAX : 0;
}

static int transition(Game *g, uint16_t mode, const VehicleServices *host, uint16_t *exit_bx)
{
    if (!host || !host->display || !host->display->call)
        return -1;
    uint8_t *ds = g->ds;
    if (host->display->call(g, MS_DEFAULT_PALETTE, 0, 0, host->display->user))
        return -1;
    DS_U8(ds, DS_PALETTE_RELOAD) = 255;
    if (mode == 1 || mode == 2) {
        DS_U16(ds, DS_VIEW_CENTRE_Y) = 60;
        DS_U8(ds, 0xAAD0) = 0;
        if (mode == 1) {
            if (character_resources_load(g, host->images) || audio_group(g, host, VS_AUDIO_FOOT))
                return -1;
        } else {
            driving_reset(ds);
            if (vehicle_hud_load(g, host->images) || audio_group(g, host, VS_AUDIO_VEHICLE))
                return -1;
        }
        /* Reset uses the old actor flags; 02B5 changes them only afterward. */
        if (camera_reset(g, host->display, host->images))
            return -1;
        uint16_t player = DS_U16(ds, DS_PLAYER);
        if (mode == 1) {
            uint16_t speed = player == 0x04D4 ? 10 : 8;
            DS_U16(ds, player + 10) = DS_U16(ds, player + 12) = speed;
            DS_U8(ds, player + 14) = 1;
            DS_U16(ds, player + 2) = 28;
            DS_U16(ds, player + 48) = 0;
        } else {
            DS_U16(ds, player + 2) = 12;
            DS_U16(ds, player + 10) = DS_U16(ds, player + 12) = 0;
            DS_U8(ds, player + 14) = 2;
            DS_U16(ds, 0x0412) = 0x5A34;
            DS_U16(ds, player + 48) = DS_U16(ds, 0x5F76);
            if (DS_U8(ds, 0x5EF7)) {
                DS_U8(ds, player + 14) |= 8;
                DS_U16(ds, 0x0412) = 0x5A28;
            }
        }
        hud_choose_panel(ds);
        if (exit_bx) {
            int32_t bx = hud_init_walking_state(g, host->images, DS_U8(ds, DS_CAMERA_MODE) ? 6 : 12);
            if (bx < 0)
                return -1;
            *exit_bx = (uint16_t)bx;
        } else if (hud_init_normal(g, host->images))
            return -1;
    }
    if (DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1) {
        if (exit_bx)
            *exit_bx = walking_step_bx(g, *exit_bx);
        else
            walking_step(g);
        return 0;
    }
    OpponentServices native_exit = {transition_service, (void *)host};
    return driving_step(g, &native_exit);
}

int vehicle_transition(Game *g, uint16_t mode, const VehicleServices *host)
{
    return transition(g, mode, host, NULL);
}

/* The mode=1 exit is the only 02B5 register output used by vehicle combat. */
int32_t vehicle_exit_state(Game *g, const VehicleServices *host)
{
    uint16_t bx = 1;
    return transition(g, 1, host, &bx) < 0 ? -1 : bx;
}
