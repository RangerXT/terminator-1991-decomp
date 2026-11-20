/* Complete E170 system-HUD composition and warning/target presentation.
 * Bitmap IO remains a synchronous host service; the HUD target query is native.
 * Sound bodies remain EV_SOUND requests, consistent with hudsweep.c/blast.c. */
#include "term.h"

static uint32_t service(Game *g, const HudServices *host, uint16_t id, uint16_t arg)
{
    return host && host->call ? host->call(g, id, arg, host->user) : UINT32_MAX;
}

static void mask_slot(Game *g, uint16_t slot, uint16_t dest, uint16_t width, uint16_t rows)
{
    uint8_t *ds = g->ds;
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    screen_blit_mask(g, DS_U16(ds, slot + 2), (uint16_t)(DS_U16(ds, slot) + 16),
                     (uint16_t)(dest + DS_U16(ds, DS_DRAW_PAGE)), width, rows, DS_U8(far_ptr(g, code, 0x1B41), 0),
                     DS_U16(far_ptr(g, code, 0x1B42), 0));
}

/* orig 4FE5. Restore the bitmap and copy its upper 110 rows to the other pages. */
int hud_refresh_pages(Game *g, const HudServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
    DS_U16(ds, 0x805C) = 0x0898;
    DS_U16(ds, DS_DRAW_PAGE) = 0;
    DS_U16(ds, 0xC4AE) = 20;
    if (service(g, host, HS_LOAD_IMAGE, 0x775D) == UINT32_MAX)
        return -1;
    DS_U16(ds, 0xC4AE) = 0;
    screen_copy_rect(g, 0, 0x2000, 40, 110);
    screen_copy_rect(g, 0, 0x4000, 40, 110);
    DS_U16(ds, 0x805C) = 0x36B0;
    DS_U16(ds, DS_DRAW_PAGE) = page;
    return 0;
}

/* orig E813. Black text labels behind the target-information values. */
void hud_clear_target_info(Game *g)
{
    DS_U8(g->ds, DS_NUMBER_COLOUR) = 0;
    hud_draw_text(g, 0xE4B8, 0x0C88);
    hud_draw_text(g, 0xE4C0, 0x0D78);
    hud_draw_text(g, 0xE4C7, 0x0E68);
    hud_draw_text(g, 0xE4CE, 0x0F58);
}

/* orig E6E0. Preserve the source's two indirections and byte MUL for record ids. */
void hud_draw_target_info(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x115D) && !DS_U16(ds, DS_TARGET_RECORD))
        return;
    hud_clear_target_info(g);
    uint16_t record = 0;
    uint16_t kind = 0;
    if (!DS_U8(ds, 0x115D)) {
        record = DS_U16(ds, DS_U16(ds, 0xE56C));
        uint16_t flags = DS_U16(ds, record + 6);
        if (flags & 4)
            kind = 4;
        else if (flags & 0x20)
            kind = 0x20;
        else if (flags & 0x4000)
            kind = 0x4000;
    }
    hud_draw_text(g, kind ? 0xE4D9 : 0xE4D3, 0x0C8C);
    hud_draw_text(g, kind == 4 ? 0xE4F3 : kind == 0x20 ? 0xE4EA : 0xE4E1, 0x0D7C);
    if (!kind)
        record = DS_U16(ds, DS_TARGET_RECORD);
    uint16_t first, second;
    if (kind == 4 || kind == 0x20) {
        uint16_t actor = kind == 4 ? 0x053C : 0x04D4;
        first = DS_U16(ds, actor + 10);
        second = DS_U16(ds, actor + 6);
    } else if (kind == 0x4000 || (DS_U16(ds, record + 6) & 0x2000)) {
        uint16_t vehicle = (uint16_t)(0x0B30 + 22 * (uint8_t)(DS_U16(ds, record + 8) >> 1));
        first = DS_U16(ds, vehicle + 10);
        second = DS_U16(ds, vehicle + 6);
    } else {
        first = 0;
        second = DS_U16(ds, 0x72C0 + (uint16_t)(2 * DS_U16(ds, record + 6)));
    }
    hud_draw_number(g, first, 0x0E6C);
    hud_draw_number(g, second, 0x0F5C);
    DS_U8(ds, DS_NUMBER_COLOUR) = 15;
}

/* orig E542, including its E56F bitmap and the DS:E56E polyline table. */
void hud_draw_target_frame(Game *g)
{
    uint8_t *ds = g->ds;
    mask_slot(g, 0xE514, 0x0D5C, 6, 8);
    DS_U16(ds, DS_FILL_COLOUR) = 4;
    uint16_t table = 0xE56E, groups = DS_U16(ds, table);
    table += 2;
    unsigned group_count = groups ? groups : 65536;
    for (unsigned i = 0; i < group_count; ++i) {
        uint16_t count = DS_U16(ds, table);
        DS_U16(ds, DS_PEN_X) = DS_U16(ds, table + 2);
        DS_U16(ds, DS_PEN_Y) = DS_U16(ds, table + 4);
        table += 6;
        unsigned line_count = count ? count : 65536;
        for (unsigned j = 0; j < line_count; ++j) {
            uint16_t x = DS_U16(ds, table), y = DS_U16(ds, table + 2);
            table += 4;
            line_to(ds, g->planes, x, y);
        }
    }
}

/* orig E4AE. Scan result is original SI in low 16 bits, carry in bit 16. */
int hud_draw_target(Game *g, const HudServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x115D) || DS_U8(ds, 0x1140))
        hud_draw_target_info(g);
    if (!DS_U8(ds, DS_WEAPON))
        return 0;
    if (!--DS_U8(ds, 0xE4FD)) {
        DS_U8(ds, 0x1140) = 0;
        DS_U8(ds, 0xE4FD) = 3;
        int found;
        if (DS_U8(ds, 0x115D)) {
            if (DS_U8(ds, 0x0364) != 12)
                return 0;
            found = 1;
        } else {
            DS_U8(ds, 0x7A18) = 255;
            uint32_t result = hud_scan_target(g);
            if (result == UINT32_MAX)
                return -1;
            DS_U16(ds, 0xE56C) = (uint16_t)result;
            DS_U8(ds, 0x7A18) = 0;
            found = (result & 0x10000) != 0;
        }
        if (found) {
            DS_U8(ds, 0x1140) = 255;
            event_push(EV_SOUND, 14, 0);
            goto locked;
        }
    }
    if (!DS_U8(ds, 0x113F) && DS_U8(ds, 0xB512)) {
        DS_U8(ds, 0xB512) = 0;
        DS_U8(ds, 0x113F) = 30;
    }
    if (DS_U8(ds, 0x113F)) {
        --DS_U8(ds, 0x113F);
        hud_draw_target_frame(g);
        hud_flash_bitmap(g, 0xE5B4);
        mask_slot(g, 0xE500, 0x0C74, 8, 8); /* orig E5A3 */
    } else if (DS_U8(ds, 0x1140)) {
    locked:
        hud_draw_target_frame(g);
        hud_flash_bitmap(g, 0xE59C);
        mask_slot(g, 0xE508, 0x0E7C, 10, 8); /* orig E589 */
    }
    return 0;
}

/* orig E5E9. Calls are deliberately ordered: the target pass can change drawing state. */
int hud_draw_warnings(Game *g, const HudServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_ZOOM_1))
        hud_flash_bitmap(g, 0xE5F0);
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if ((DS_U16(ds, player + 0x1C) >> 1) < DS_U16(ds, player + 0x1A))
        hud_flash_bitmap(g, 0xE5E4);
    player = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, player + 0x19))
        hud_flash_bitmap(g, 0xE5C0);
    if (DS_U8(ds, 0x1155))
        hud_flash_bitmap(g, 0xE5CC);
    if (hud_draw_target(g, host) < 0)
        return -1;
    if (DS_U8(ds, DS_IN_BATTLE))
        hud_flash_bitmap(g, 0xE5A8);
    return 0;
}

/* orig E170. The remaining work is now native except bitmap IO and sound. */
int hud_draw_system_dx(Game *g, const HudServices *host, uint16_t *guided_dx)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_PLAYER) != 0x0508 || DS_U8(ds, DS_CAMERA_MODE))
        return 0;
    if (guided_dx && !DS_U8(ds, 0x1150) && !DS_U8(ds, 0x1142))
        *guided_dx = 0x03CE;
    hud_draw_system_frame(g);
    if (!DS_U8(ds, KEY_DOWN(SC_EQUALS)))
        DS_U8(ds, 0xE434) = 0;
    else if (!DS_U8(ds, 0xE434)) {
        if (DS_U8(ds, KEY_DOWN(SC_RSHIFT))) {
            DS_U8(ds, 0xE434) = 255;
            DS_U8(ds, 0x1142) = (uint8_t)~DS_U8(ds, 0x1142);
        } else {
            if (hud_refresh_pages(g, host) < 0)
                return -1;
            if (guided_dx)
                *guided_dx = 0x03CE;
            DS_U8(ds, 0x114E) = (uint8_t)~DS_U8(ds, 0x114E);
            DS_U8(ds, 0xE434) = 255;
        }
    }
    if (DS_U8(ds, 0x114E))
        return 0;
    if (hud_restore_background(g) < 0)
        return -1;
    hud_zoom_key(ds);
    DS_U8(ds, DS_NUMBER_DIGITS) = 4;
    DS_U16(ds, 0xE170) = 65535;
    static const uint16_t dest[] = {0x01BA, 0x043A, 0x06BA, 0x01D5, 0x01D8};
    static const uint8_t field[] = {0, 2, 4, 0x1E, 0x20};
    for (unsigned i = 0; i < 5; ++i) {
        if (i == 3) {
            DS_U8(ds, DS_NUMBER_DIGITS) = 3;
            DS_U16(ds, 0xE170) = 0;
        }
        uint16_t player = DS_U16(ds, DS_PLAYER);
        hud_draw_number(g, DS_U16(ds, player + field[i]), dest[i]);
    }
    hud_format_score(ds);
    hud_draw_text(g, 0x7795, 0x01CF);
    if (DS_U16(ds, 0x8548)) {
        DS_U16(ds, 0xE170) = 65535;
        hud_draw_text(g, DS_U16(ds, 0x8548), 0x01BF);
        DS_U16(ds, 0xE170) = 0;
    }
    uint16_t player = DS_U16(ds, DS_PLAYER);
    hud_draw_number(g, heading_degrees(DS_U16(ds, player + 6)), 0x01DC);
    hud_draw_sweep(g);
    hud_draw_status(g);
    /* Numeric drawing sets DX. The unguided target scan can overwrite it,
     * but that mode never stores the inherited value in a shot record. */
    if (guided_dx)
        *guided_dx = 0x03CE;
    return hud_draw_warnings(g, host);
}

int hud_draw_system(Game *g, const HudServices *host)
{
    return hud_draw_system_dx(g, host, NULL);
}
