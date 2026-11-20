/* Sound sample cache/groups and request routing, original 89A2/8B1E/8A9E family.
 * File metadata, idle wait and device submission are explicit platform services. */
#include "term.h"

static int sound_service(Game *g, const SoundServices *host, uint16_t op, uint16_t a, uint16_t b)
{
    return !host || !host->platform || !host->platform->call || host->platform->call(g, op, a, b, host->platform->user)
               ? -1
               : 0;
}

/* 8B1E. Valid installed files required. An exhausted pool deliberately zeroes
 * the current segment slot, even the base slot when the first sample cannot fit. */
int sound_group_load(Game *g, const SoundServices *host, uint16_t filenames, uint16_t count, uint16_t ids)
{
    uint8_t *ds = g->ds;
    uint16_t slot = 0xA743;
    memset(ds + 0xA745, 0, 26);
    DS_U16(ds, 0xA761) = DS_U16(ds, 0xA75F);
    memset(ds + 0xA763, 0, 14);
    DS_U16(ds, 0xA771) = 0xA763;
    DS_U8(ds, 0xA6EA) = 0;
    do {
        uint16_t filename = DS_U16(ds, filenames);
        filenames += 2;
        if (sound_service(g, host, SS_STAT, filename, 0))
            return -1;
        uint16_t paragraphs = (DS_U16(ds, 0x77E5 + 26) >> 4) + 1;
        DS_U16(ds, 0xA761) -= paragraphs;
        if (DS_I16(ds, 0xA761) < 0) {
            DS_U16(ds, slot) = 0;
            return 0;
        }
        uint16_t seg = DS_U16(ds, slot), next = seg + paragraphs;
        if (file_load(g, host->files, filename, seg, 0) == UINT32_MAX)
            return -1;
        slot += 2;
        DS_U16(ds, slot) = next;
        DS_U8(ds, DS_U16(ds, 0xA771)) = DS_U8(ds, ids++);
        DS_U16(ds, 0xA771)++;
    } while (--count);
    DS_U16(ds, slot) = 0;
    return 0;
}

/* Group selectors return immediately when already loaded. A different group
 * waits for current sample completion before overwriting the sample arena. */
int sound_group_select(Game *g, const SoundServices *host, uint8_t mode)
{
    uint16_t filenames, count, ids;
    switch (mode) {
    case 1:
        filenames = 0xA6EC;
        count = 13;
        ids = 0xA706;
        break;
    case 3:
        filenames = 0xA713;
        count = 12;
        ids = 0xA72B;
        break;
    case 4:
        filenames = 0xA737;
        count = 3;
        ids = 0xA73D;
        break;
    case 6:
        filenames = 0xA740;
        count = 1;
        ids = 0xA742;
        break;
    default:
        return -1;
    }
    if (DS_U8(g->ds, 0xA6E9) == mode)
        return 0;
    while (DS_U8(g->ds, 0xAA83))
        if (sound_service(g, host, SS_WAIT_IDLE, 0, 0))
            return -1;
    if (sound_group_load(g, host, filenames, count, ids))
        return -1;
    DS_U8(g->ds, 0xA6E9) = mode;
    return 0;
}

/* 89A2/89C5. The 15-byte scan ignores a match in its final byte (CX==0).
 * Request routing and looping metadata are native; device AX output is not exposed. */
int sound_request(Game *g, const SoundServices *host, uint16_t request)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x0361))
        return 0;
    for (unsigned i = 0; i < 14; ++i)
        if (DS_U8(ds, 0xA763 + i) == (uint8_t)request) {
            uint16_t seg = DS_U16(ds, 0xA743 + i * 2);
            if (!seg)
                return 0;
            if (DS_U8(ds, 0x80E9)) {
                DS_U16(ds, 0xA876) = seg;
                DS_U16(ds, 0xA878) = request;
            }
            return sound_service(g, host, SS_PLAY, seg, request);
        }
    return 0;
}

/* Adapter for vehicle/world callers identified by their original group entry. */
uint32_t sound_group_service(Game *g, uint16_t entry, uint16_t unused, void *user)
{
    uint8_t mode;
    switch (entry) {
    case VS_AUDIO_VEHICLE:
        mode = 1;
        break;
    case VS_AUDIO_FOOT:
        mode = 3;
        break;
    case 0x8ADE:
        mode = 4;
        break;
    case 0x8AFE:
        mode = 6;
        break;
    default:
        return UINT32_MAX;
    }
    return sound_group_select(g, (const SoundServices *)user, mode) < 0 ? UINT32_MAX : 0;
}

/* 8C45: request current-sample completion through AA94, then wait for AA83. */
int sound_stop_and_wait(Game *g, const SoundServices *host)
{
    DS_U8(g->ds, 0xAA94) = 0;
    while (DS_U8(g->ds, 0xAA83))
        if (sound_service(g, host, SS_WAIT_IDLE, 0, 0))
            return -1;
    return 0;
}
