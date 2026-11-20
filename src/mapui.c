/* Modal selection portions CC43..CC8C and D021..D0A5. Setup/resource IO is separate. */
#include "term.h"

int map_select(Game *g, const MapPlatform *platform, uint8_t area)
{
    uint8_t *ds = g->ds;
    int escaped;
    for (;;) {
        if (map_pointer_step(g))
            return -1;
        uint8_t action;
        if (area) {
            action = DS_U8(ds, KEY_DOWN(SC_F)) ? 'F' : (DS_U8(ds, KEY_DOWN(SC_H)) ? 'H' : 0);
            DS_U8(ds, DS_MAP_ACTION) = action;
        } else
            action = map_requested_action(ds);
        if (action) {
            escaped = 0;
            break;
        }
        if (!platform || !platform->wait || platform->wait(g, 0, platform->user))
            return -1;
        if (area && DS_U8(ds, KEY_DOWN(SC_N)) && DS_U8(ds, KEY_DOWN(SC_U)) && DS_U8(ds, KEY_DOWN(SC_M))
            && DS_U8(ds, KEY_DOWN(SC_S)) && DS_U8(ds, KEY_DOWN(SC_K)) && DS_U8(ds, KEY_DOWN(SC_L)))
            DS_U8(ds, 0xE1F1) = 255;
        if (DS_U8(ds, KEY_DOWN(SC_ESC)) & 128) {
            escaped = 1;
            break;
        }
        for (unsigned i = 0; i < 5; ++i)
            if (platform->wait(g, (uint8_t)!(i & 1), platform->user))
                return -1;
    }
    if (area) {
        DS_U16(ds, 0x9A5A) = 184;
        DS_U16(ds, 0x7D28) = 0x4000;
    }
    return escaped;
}