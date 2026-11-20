/* 77F6/781F: candidates for the guided targeting/cycling system. */
#include "term.h"

uint8_t weapon_target_candidate(const uint8_t *ds, uint16_t record)
{
    uint16_t id = DS_U16(ds, record + 8);
    return id == DS_U16(ds, 0x72CA) || id == DS_U16(ds, 0x72CC) || id == DS_U16(ds, 0x72CE)
           || (DS_U16(ds, record + 6) & 0x2000) != 0;
}

static uint16_t collect(uint8_t *ds, uint16_t record, uint16_t count, uint16_t dest)
{
    for (uint16_t i = 0; i < count; ++i, record += 12) {
        if (!weapon_target_candidate(ds, record))
            continue;
        uint16_t actor = DS_U16(ds, DS_PLAYER);
        DS_U16(ds, dest) =
            approx_distance(DS_I16(ds, actor), DS_I16(ds, actor + 4), DS_I16(ds, record), DS_I16(ds, record + 4));
        DS_U16(ds, dest + 2) = record;
        dest += 4;
        if (++DS_U16(ds, 0x1194) >= 41)
            break;
    }
    if (DS_U16(ds, 0x11AA) >= DS_U16(ds, 0x1194))
        DS_U16(ds, 0x11AA) = 0;
    return dest;
}

void weapon_collect_targets(uint8_t *ds)
{
    if (!DS_U8(ds, 0x115D))
        return;
    DS_U16(ds, 0x1194) = 0;
    uint16_t dest = 0x041A, count = DS_U16(ds, DS_VISIBLE_COUNT);
    if (count)
        dest = collect(ds, 0x5F80, count, dest);
    count = DS_U16(ds, DS_FIGURE_COUNT);
    /* The second list is called even if the first reached 41, allowing one more.
     * Empty lists skip index normalization, as in the original JCXZ branches. */
    if (count)
        collect(ds, 0x0DF0, count, dest);
}
