/* Status conditions and rotating text in the Terminator's HUD. */
#include "term.h"

/* orig E29B. The first status flag is persistent; only slots 1..6 are refreshed. */
void hud_collect_status(uint8_t *ds)
{
    for (unsigned i = 0; i < 6; ++i)
        DS_U8(ds, 0xE47C + i) = 0;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!DS_U16(ds, player + 0x1A))
        DS_U8(ds, 0xE47C) = 255;
    if (DS_U8(ds, player + 0x19))
        DS_U8(ds, 0xE47D) = 255;
    if (DS_U8(ds, 0xE4FB))
        DS_U8(ds, 0xE47E) = 255;
    if (DS_U8(ds, DS_COMPANION_ACTIVE))
        DS_U8(ds, 0xE47F) = 255;
    if (DS_U8(ds, DS_OPPONENT_ACTIVE))
        DS_U8(ds, DS_U8(ds, 0x1152) ? 0xE47F : 0xE480) = 255;
    if ((uint16_t)(DS_U16(ds, player + 0x1C) - DS_U16(ds, player + 0x1A)) < 20)
        DS_U8(ds, 0xE481) = 255;
}

/* orig E307. Return the original carry: 1 means no active message. Index is 0..6. */
int hud_cycle_status(uint8_t *ds)
{
    uint8_t current = DS_U8(ds, 0xE482);
    if (DS_U8(ds, 0xE47B + current) && --DS_U8(ds, 0xE483))
        return 0;
    DS_U8(ds, 0xE483) = 5;
    uint8_t next = current;
    do {
        next = (uint8_t)(next + 1);
        if (next >= 7)
            next = 0;
        if (DS_U8(ds, 0xE47B + next)) {
            DS_U8(ds, 0xE482) = next;
            return 0;
        }
    } while (next != current);
    return 1;
}

/* orig E280. Keep the original text pointer table and inherited font/colour state. */
void hud_draw_status(Game *g)
{
    hud_collect_status(g->ds);
    if (hud_cycle_status(g->ds))
        return;
    uint16_t text = DS_U16(g->ds, 0xE46D + 2 * DS_U8(g->ds, 0xE482));
    hud_draw_text(g, text, 0x01C7);
}
