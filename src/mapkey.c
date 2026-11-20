/* The map screen the M key opens during play (0000:CA73..CB4A, the body of CA46).
 *
 *   M        the local map; F fast-travels to the pointer, H sets the compass homing on it,
 *            Esc leaves
 *   Alt+M    the area map, the same choices
 *   Ctrl+M   restores the map's information panel area on the screen (CDAA)
 *
 * After fast travel or homing the view is rebuilt: camera_reset and the visible cells
 * reloaded. Everything is C except what the services below still supply.
 */
#include <string.h>

#include "term.h"

enum {
    TEXT_CAR_TOO_SLOW = 0x04B7, /* "This car can not travel at the speed we will be traveling. ..." */
    TEXT_IN_BATTLE = 0x058A,    /* "You are unable to fast travel while engaged in battle." */
};

/* orig 0000:3732   forget every key: clear the key table and empty the keyboard buffer. The
 * original repeats until the table stays clear, because the keyboard interrupt can set a
 * key meanwhile; here the keys change only between calls. */
void keyboard_flush(Game *g)
{
    uint8_t *ds = g->ds;
    for (;;) {
        memset(ds + DS_KEY_DOWN, 0, 255);
        if (!DS_U16(ds, DS_KEYBUF_COUNT))
            return;
        keyboard_read(g, NULL);
    }
}

/* orig 0000:0C6B   AL = page to show, AH = page to draw, then 0C7D picks the pages; nothing
 * while a facility screen is up. The host service MS_SELECT_PAGES (select_pages in C). */
static int pages_service(Game *g, const MapResources *host, uint16_t ax)
{
    if (!host || !host->call)
        return -1;
    return host->call(g, MS_SELECT_PAGES, ax, 0, host->user) ? -1 : 0;
}

/* orig 0000:CDAA   Ctrl+M on foot with the normal camera: clear the information panel and
 * copy its area (8 bytes x 64 rows at 0x11B7) from the shown page to the two others. */
static void restore_info_panel(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_CAMERA_MODE) || !(DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1))
        return;
    map_clear_info(g);
    screen_copy_rect(g, 0x11B7, 0x31B7, 8, 0x40);
    screen_copy_rect(g, 0x11B7, 0x51B7, 8, 0x40);
}

/* What fast travel asks of the host: cells are loaded here (update_visible_cells); the
 * arrival follow-up (0000:057C) and anything else go to the host's travel service. */
static uint32_t travel_service(Game *g, uint16_t service, uint16_t arg, void *user)
{
    const MapKeyServices *host = (const MapKeyServices *)user;
    if (service == TR_LOAD_CELLS)
        return update_visible_cells(g, host->images) < 0 ? UINT32_MAX : 0;
    if (!host->travel || !host->travel->call)
        return UINT32_MAX;
    return host->travel->call(g, service, arg, host->travel->user);
}

/* orig 0000:CAF2..CB3B   travel to the chosen place, unless in a car or in battle */
static int fast_travel(Game *g, const MapKeyServices *host)
{
    uint8_t *ds = g->ds;
    if (!(DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1))
        return textbox_draw(g, TEXT_CAR_TOO_SLOW, 0x0A, 4, 0x19, 8, host->text) < 0 ? -1 : 0;
    if (DS_U8(ds, DS_IN_BATTLE))
        return textbox_draw(g, TEXT_IN_BATTLE, 0x0A, 4, 0x17, 5, host->text) < 0 ? -1 : 0;
    map_destination_measure(ds);
    TravelServices io = {travel_service, (void *)host};
    if (travel_run_native_simulation(g, &io, host->opponents, host->vehicle) < 0)
        return -1;
    return travel_clear_arrival_native(g, &io);
}

/* orig 0000:CA73..CB4A (called with M held) */
int map_screen(Game *g, const MapKeyServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    if (DS_U8(ds, KEY_DOWN(SC_CTRL))) {
        restore_info_panel(g);
        DS_U8(ds, DS_HOMING) = 0;
        return 0;
    }
    DS_U16(ds, DS_VISIBLE_CELL) = 0xFFFF;
    /* 151B:021E (AL=1) does nothing outside a link game */
    int travel = 0;
    if (!DS_U8(ds, KEY_DOWN(SC_ALT))) {
        for (;;) { /* the local map (CA91); chosen again while the place is off the map */
            DS_U8(ds, 0x7A18) = 0;
            keyboard_flush(g);
            if (map_begin_local(g, host->resources) < 0 || map_select(g, host->platform, 0) < 0)
                return -1;
            if (DS_U8(ds, DS_MAP_ACTION) == 'H') {
                map_local_destination(ds);
                DS_U8(ds, DS_HOMING) = 0xFF;
            }
            if (DS_U8(ds, DS_MAP_ACTION) != 'F')
                break;
            DS_U8(ds, DS_MAP_KEY_FLAG) = 0xFF;
            if (!map_local_destination(ds)) {
                travel = 1;
                break;
            }
        }
    } else { /* the area map (CAC1) */
        DS_U8(ds, 0x7A18) = 0;
        if (pages_service(g, host->resources, 0) < 0)
            return -1;
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x50;
        if (map_begin_area(g, host->resources) < 0 || map_select(g, host->platform, 1) < 0)
            return -1;
        if (DS_U8(ds, DS_MAP_ACTION) == 'H') {
            map_area_destination(ds);
            DS_U8(ds, DS_HOMING) = 0xFF;
        }
        if (DS_U8(ds, DS_MAP_ACTION) == 'F') {
            DS_U8(ds, DS_MAP_KEY_FLAG) = 0xFF;
            map_area_destination(ds);
            travel = 1;
        }
    }
    if (travel && fast_travel(g, host) < 0)
        return -1;
    DS_U16(ds, DS_SCREEN_STRIDE) = 0x28; /* CB3E */
    if (camera_reset(g, host->resources, host->images) < 0)
        return -1;
    return update_visible_cells(g, host->images) < 0 ? -1 : 0;
}
