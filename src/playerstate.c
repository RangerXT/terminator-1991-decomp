/* Small native player/world helpers called from the gameplay update. */
#include "term.h"

/* 11BC:1796: noisy companion bearing and probabilistic sound cadence. */
void player_companion_indicator(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (player != 0x04D4 || !DS_U8(ds, 0xAA9F))
        goto reset;
    if ((int8_t)DS_U8(ds, 0x0343) < 0) {
        DS_U8(ds, 0x0343)++;
        return;
    }
    if (DS_U8(ds, player + 14) != 1)
        goto reset;
    if (!DS_U8(ds, DS_OPPONENT_ACTIVE))
        return;
    uint16_t heading = angle_between(ds, DS_I16(ds, player), DS_I16(ds, player + 4), DS_I16(ds, DS_OPPONENT_X),
                                     DS_I16(ds, DS_OPPONENT_Z));
    int16_t jitter = (int8_t)(random_word(ds) >> 8);
    hud_compass_needle(g, 0x7B30, (uint16_t)(heading + (jitter >> 3)), 12);
    if (DS_U8(ds, 0x7AC0) < 4 && !--DS_U8(ds, 0x7AC1)) {
        DS_U8(ds, 0x7AC1) = random_word(ds) & 63;
        event_push(EV_SOUND, 11, 0);
    }
    return;
reset:
    DS_U8(ds, 0x7AC0) = 0;
    DS_U8(ds, 0x7AC1) = 1;
}

/* 091F: the actual map sample value 1 marks the drowning-warning condition. */
void player_sample_warning(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    DS_U8(ds, 0x00B9) = 0;
    if ((uint8_t)figure_map_sample(g, DS_U16(ds, actor), DS_U16(ds, actor + 4)) == 1)
        DS_U8(ds, 0x00B9) = 255;
}

/* 7088: toggle the trailing byte of each eleven-byte record every 4000 steps. */
void world_toggle_records(uint8_t *ds)
{
    if (--DS_U16(ds, 0x854A))
        return;
    DS_U16(ds, 0x854A) = 4000;
    uint16_t at = 0x854E, count = DS_U16(ds, 0x854C);
    unsigned n = count ? count : 65536;
    for (unsigned i = 0; i < n; ++i) {
        at += 10;
        DS_U8(ds, at++) ^= 1;
    }
}

/* 596C: low-byte threat/count bookkeeping; byte additions wrap independently. */
void player_update_threat(uint8_t *ds)
{
    uint8_t value = DS_U8(ds, DS_OPPONENT_ACTIVE);
    if (DS_U16(ds, DS_PLAYER) == 0x0508)
        value += DS_U8(ds, DS_COMPANION_ACTIVE);
    DS_U8(ds, DS_IN_BATTLE) = (uint16_t)(value + DS_U16(ds, DS_FIGURE_COUNT) - DS_U16(ds, 0x119C));
}

/* A426: defer figure creation until the alert cooldown and threat gates clear. */
void figure_retry_deferred(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0xB69F)) {
        DS_U8(ds, 0xB69F)--;
        return;
    }
    if (DS_U8(ds, DS_IN_BATTLE) || --DS_U16(ds, 0xB738))
        return;
    DS_U16(ds, 0xB738) = 100;
    uint16_t count = DS_U16(ds, 0x116E);
    if (count) {
        DS_U16(ds, 0x116E) = 0;
        figure_spawn(g, count, 1);
    }
    count = DS_U16(ds, 0x1170);
    if (count) {
        DS_U16(ds, 0x1170) = 0;
        figure_spawn(g, count, 0);
    }
}

/* 3B54: original code-segment toggle byte and its explanatory modal panel. */
int debug_vector_toggle(Game *g, const TextPlatform *platform)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x5A50))
        return 0;
    if (DS_U8(ds, DS_FACILITY_SCREEN)
        || (!DS_U16(ds, DS_WARNING_COUNTDOWN) && !DS_U8(ds, DS_RELOAD_COUNTDOWN) && !DS_U8(ds, 0x5A4E)
            && (!platform || !platform->poll)))
        return -1;
    DS_U8(ds, 0x5A50) = 0;
    uint8_t *toggle = far_ptr(g, (uint16_t)(g->ds_seg - 0x5C27), 0x3B87);
    *toggle = (uint8_t)~*toggle;
    return textbox_draw(g, *toggle ? 0x0257 : 0x0272, 6, 5, 26, 3, platform);
}

/* 0809..0820: first complete update phase, before player/world controls. */
int gameplay_prepare(Game *g, const TextPlatform *platform)
{
    if (debug_vector_toggle(g, platform) < 0)
        return -1;
    player_update_threat(g->ds);
    figure_retry_deferred(g);
    world_toggle_records(g->ds);
    if (DS_U8(g->ds, 0x1155))
        DS_U8(g->ds, 0x1155)--;
    return 0;
}

/* 0809..0829: preparation, edge warnings, queued blasts and nearby refuelling.
 * 089E's vehicle/companion destruction and the remaining controls follow later. */
int gameplay_update_opening(Game *g, const TextPlatform *ui, const KeyboardPlatform *keys)
{
    if (gameplay_prepare(g, ui) < 0 || player_check_map_edge(g, ui) < 0)
        return -1;
    blast_queue_step_native(g);
    return vehicle_refuel_nearby(g, ui, keys);
}

void player_recover_pose(uint8_t *ds)
{
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, actor + 50) >= 200)
        DS_U8(ds, actor + 50) = 200;
    if (!(DS_U8(ds, actor + 14) & 1)) {
        if (DS_I16(ds, actor + 48) < 0)
            DS_U8(ds, actor + 14) = 1;
        return;
    }
    uint16_t height = DS_U16(ds, actor + 2);
    if (height < 28)
        DS_U16(ds, actor + 2) = 28;
    else if (height > 28)
        DS_U16(ds, actor + 2) = height - 32;
}
