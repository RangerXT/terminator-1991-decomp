/* 089E loss handling and A28A record promotion. */
#include "term.h"

void companion_promote_record(uint8_t *ds)
{
    uint16_t dest = DS_U16(ds, DS_VEHICLE);
    DS_U16(ds, DS_VEHICLE) = 0x053C;
    for (unsigned i = 0; i < 52; ++i)
        DS_U8(ds, dest + i) = DS_U8(ds, 0x053C + i);
    DS_U8(ds, 0x1152) = 255;
    DS_U8(ds, DS_OPPONENT_ACTIVE) = DS_U8(ds, DS_COMPANION_ACTIVE);
    DS_U8(ds, DS_COMPANION_ACTIVE) = 0;
}

static int loss_service(Game *g, const MovieServices *host, uint16_t op, uint16_t arg)
{
    return !host || !host->other || !host->other->call || host->other->call(g, op, arg, host->other->user) == UINT32_MAX
               ? -1
               : 0;
}

int gameplay_check_losses(Game *g, const MovieServices *movie, const SoundServices *sound)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_VEHICLE);
    if (DS_U16(ds, actor + 26) >= DS_U16(ds, actor + 28)) {
        if (!DS_U8(ds, 0x1152)) {
            if (DS_U8(ds, DS_LINK_GAME) && loss_service(g, movie, 0x0248, 0))
                return -1;
            DS_U8(ds, 0x1157) = 255;
            if (DS_U16(ds, DS_PLAYER) == 0x0508) {
                if (!movie || !movie->files || sound_stop_and_wait(g, sound))
                    return -1;
                if (cutscene_play(g, 0x7A1D, 40, 8, 1, movie) || loss_service(g, movie, OS_WAIT, 120))
                    return -1;
                if (character_models_load(g, movie->files, 0)
                    || character_models_load(g, movie->files, DS_U16(ds, 0x11CD) ? 1 : 2))
                    return -1;
                DS_U16(ds, DS_VISIBLE_CELL) = 65535;
                if (loss_service(g, movie, OS_LOAD_CELLS, 0) || loss_service(g, movie, OS_CAMERA_RESET, 0))
                    return -1;
                companion_promote_record(ds);
                return 0;
            }
            DS_U8(ds, DS_MISSION_OVER) = 1;
            return 0;
        }
    } else if (DS_U16(ds, 0x0556) < DS_U16(ds, 0x0558))
        return 0;
    if (DS_U8(ds, DS_LINK_GAME) && loss_service(g, movie, 0x023B, 0))
        return -1;
    DS_U16(ds, 0x1158) = 65535;
    DS_U8(ds, DS_MISSION_OVER) = 1;
    return 0;
}
