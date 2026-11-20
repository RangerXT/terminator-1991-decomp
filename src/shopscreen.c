/* Four interactive shop screens, original 813E..830E; kinds 4..6 go on to the facility
 * screen 8CB0 (src/facility.c) as the original's jump at 8154 does. Files, BIOS/palette/page
 * operations, input/time and the inventory-key 51C0 panel are explicit services. */
#include "term.h"

static int display(Game *g, const ShopScreenServices *host, uint16_t op, uint16_t a)
{
    return !host || !host->platform || !host->platform->call || host->platform->call(g, op, a, 0, host->platform->user)
               ? -1
               : 0;
}
static int wait_sample(Game *g, const ShopScreenServices *host)
{
    while (DS_U8(g->ds, 0xAA83)) {
        const SoundServices *sound = host->sound;
        if (!sound || !sound->platform || !sound->platform->call
            || sound->platform->call(g, SS_WAIT_IDLE, 0, 0, sound->platform->user))
            return -1;
    }
    return 0;
}
static int release_shop_keys(Game *g, const ShopScreenServices *host)
{
    const MenuPlatform *menu = host->actions->menu;
    while (DS_U8(g->ds, KEY_DOWN(SC_ENTER)) || DS_U8(g->ds, KEY_DOWN(SC_ESC)))
        if (!menu || !menu->call || menu->call(g, SHOP_KEYS_RELEASE, 0, 0, menu->user))
            return -1;
    return 0;
}

int shop_screen_exit(Game *g, const ShopScreenServices *host)
{
    if (!host || !host->actions)
        return -1;
    uint8_t *ds = g->ds;
    const ImageIO *files = host->actions->files;
    if (wait_sample(g, host))
        return -1;
    DS_U16(ds, 0x1210) = 0;
    DS_U8(ds, DS_FACILITY_SCREEN) = 0;
    if (display(g, host, MS_VIDEO_MODE, 13) || display(g, host, MS_DEFAULT_PALETTE, 0))
        return -1;
    DS_U8(ds, DS_PALETTE_RELOAD) = 255;
    DS_U16(ds, DS_SCREEN_STRIDE) = 40;
    DS_U16(ds, 0x805C) = 0x1F40;
    if (camera_reset(g, host->platform, files))
        return -1;
    DS_U8(ds, 0x9A4A) = 0;
    if (hud_weapon_slots(g))
        return -1;
    if (horizon_load(g, files))
        return -1;
    DS_U16(ds, DS_VISIBLE_CELL) = 65535;
    return sound_group_select(g, host->sound, 3);
}

/* entry_sp records the original DOS continuation value in 9A4C for reference
 * comparisons; the native implementation uses structured EXIT results instead. */
int shop_screen(Game *g, uint16_t kind, uint16_t entry_sp, const ShopScreenServices *host)
{
    uint8_t *ds = g->ds;
    if (kind > 3) { /* 8154 */
        if (DS_U8(ds, DS_LINK_GAME) || !host || !host->facility)
            return -1;
        DS_U16(ds, 0x9A4C) = entry_sp;
        DS_U8(ds, 0x9A49) = 0;
        return facility_screen(g, kind, host->facility) < 0 ? -1 : 0;
    }
    if (DS_U8(ds, DS_LINK_GAME) || !host || !host->actions || !host->actions->files
        || !host->actions->files->call || !host->platform || !host->platform->call || !host->sound
        || !host->sound->files || !host->sound->files->call || !host->sound->platform || !host->sound->platform->call)
        return -1;
    const ShopServices *actions = host->actions;
    if (DS_U8(ds, 0xADD0) && (!actions->screen || !host->palette))
        return -1;
    DS_U16(ds, 0x9A4C) = entry_sp;
    DS_U8(ds, 0x9A49) = 0;
    DS_U16(ds, DS_POINTER_X) = 160;
    DS_U16(ds, DS_POINTER_Y) = 100;
    DS_U8(ds, 0x9A4B) = 0;
    if (sound_group_select(g, host->sound, 4) || display(g, host, MS_DEFAULT_PALETTE, 0))
        return -1;
    DS_U8(ds, 0x9A4A) = 1;
    DS_U8(ds, DS_FILL_COLOUR) = 15;
    DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    uint16_t pair = kind * 2, quad = kind * 4, mode = DS_U16(ds, 0x9A66 + pair);
    DS_U16(ds, DS_SCREEN_STRIDE) = DS_U16(ds, 0x9A74 + quad);
    DS_U16(ds, 0x805C) = DS_U16(ds, 0x9A76 + quad);
    DS_U16(ds, 0x724C) = DS_U16(ds, 0x805C) == 0x1F40 ? 310 : 630;
    if (mode != 13 && !DS_U8(ds, DS_FACILITY_SCREEN))
        DS_U16(ds, DS_POINTER_X) *= 2;
    if (display(g, host, MS_VIDEO_MODE, mode) || display(g, host, MS_DEFAULT_PALETTE, 0)
        || display(g, host, MS_SELECT_PAGES, 0))
        return -1;
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        DS_U16(ds, 0x724C) = 310;
        if (display(g, host, MS_VIDEO_MODE, 19)
            || image_vga_load(g, actions->files, DS_U16(ds, 0x9A92 + pair), actions->screen, host->palette))
            return -1;
    } else if (image_load_screen(g, actions->files, DS_U16(ds, 0x9A8A + pair)))
        return -1;
    if (shop_was_visited(ds)) {
        if (display(g, host, MS_PALETTE, 0))
            return -1;
        DS_U8(ds, 0x7A18) = 0;
        if (shop_alarm(g, actions->files, actions->menu, actions->text, actions->screen) < 0)
            return -1;
        return shop_screen_exit(g, host);
    }
    screen_copy_rect(g, 0, 0x4000, DS_U16(ds, DS_SCREEN_STRIDE), 200);
    DS_U16(ds, 0x9A6E) = DS_U16(ds, 0x9AA8 + pair);
    DS_U16(ds, 0x9A88) = DS_U16(ds, 0x9AB0 + pair);
    DS_U16(ds, 0x9A86) = DS_U16(ds, 0x9A9A + pair);
    DS_U16(ds, 0xA612) = pair;
    if (DS_U16(ds, 0x0208))
        DS_U16(ds, 0x9A84) = DS_U16(ds, 0x009F + pair);
    else {
        uint32_t size = file_load(g, actions->files, DS_U16(ds, 0x9A86), DS_U16(ds, 0x94E2), DS_U16(ds, 0x94E0));
        if (size == UINT32_MAX)
            return -1;
        DS_U16(ds, 0x9A84) = (uint16_t)size;
    }
    if (display(g, host, MS_PALETTE, 0))
        return -1;
    for (;;) {
        if (scene_overlay_restore_all(g, actions->screen) || map_pointer_step_display(g, actions->screen)
            || display(g, host, 0x0DAA, 0))
            return -1;
        if (DS_U8(ds, KEY_DOWN(SC_ENTER))) {
            int result = shop_confirm_item(g, DS_U16(ds, DS_POINTER_X), DS_U16(ds, DS_POINTER_Y), actions);
            if (result < 0)
                return -1;
            if (result == SHOP_ACTION_EXIT)
                return shop_screen_exit(g, host);
            map_restore_pointer(g);
            DS_U8(ds, DS_FILL_COLOUR) = 15;
            if (map_draw_pointer_display(g, actions->screen))
                return -1;
            continue;
        }
        if (DS_U8(ds, KEY_DOWN(SC_F10))) {
            DS_U8(ds, 0x9950) = 0;
            if (!host->extra || !host->extra->call || host->extra->call(g, 0x51C0, 0, host->extra->user) == UINT32_MAX)
                return -1;
            if (!DS_U8(ds, 0x9950)) {
                if (DS_U8(ds, DS_FACILITY_SCREEN))
                    scene_vga_overlay_restore(g, actions->screen);
                else if (scene_overlay_restore(g))
                    return -1;
            }
            if (release_shop_keys(g, host))
                return -1;
            map_restore_pointer(g);
            DS_U8(ds, DS_FILL_COLOUR) = 15;
            if (map_draw_pointer_display(g, actions->screen))
                return -1;
            continue;
        }
        if (DS_U8(ds, KEY_DOWN(SC_ESC)))
            return shop_screen_exit(g, host);
        if (display(g, host, 0x0D8D, 0) || display(g, host, 0x0DAA, 0) || display(g, host, 0x0D8D, 0)
            || display(g, host, 0x0DAA, 0) || display(g, host, 0x0D8D, 0))
            return -1;
    }
}

typedef struct ShopInteractionContext {
    const ShopScreenServices *host;
    uint16_t entry_sp;
} ShopInteractionContext;

static uint32_t shop_screen_service(Game *g, uint16_t op, uint16_t kind, void *user)
{
    const ShopInteractionContext *context = user;
    if (op != 0x813E)
        return UINT32_MAX;
    return shop_screen(g, kind, context->entry_sp, context->host) ? UINT32_MAX : 0;
}

int shop_interaction_native(Game *g, const ShopScreenServices *host, uint16_t entry_sp)
{
    ShopInteractionContext context = {host, entry_sp};
    OpponentServices screen = {shop_screen_service, &context};
    return shop_interaction(g, &screen);
}
