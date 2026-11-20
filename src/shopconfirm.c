/* Native confirmation-option handlers 84B5/84BF/850E and 83A6 item selection. */
#include "term.h"

static int close_window(Game *g, const ShopServices *host)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN)) {
        if (!host->screen)
            return -1;
        scene_vga_overlay_restore(g, host->screen);
        return 0;
    }
    return scene_overlay_restore(g);
}

/* Return CLOSED or EXIT instead of mutating a DOS caller stack. */
int shop_option_action(Game *g, uint16_t target, const ShopServices *host)
{
    if (!host)
        return -1;
    uint8_t *ds = g->ds;
    if (target == 0x84B5)
        return close_window(g, host) ? -1 : SHOP_ACTION_CLOSED;
    if (target != 0x84BF && target != 0x850E)
        return -1;
    int stealing = target == 0x850E;
    if (!stealing && DS_U8(ds, 0x9A49)) {
        DS_U8(ds, DS_U16(ds, DS_PLAYER) + 50) += 2;
        DS_U8(ds, 0x7A18) = 0;
        if (shop_alarm(g, host->files, host->menu, host->text, host->screen) < 0
            || scene_overlay_restore_all(g, host->screen))
            return -1;
        return SHOP_ACTION_EXIT;
    }
    if (stealing && !DS_U8(ds, 0x9A4B)) {
        DS_U8(ds, DS_U16(ds, DS_PLAYER) + 50)++;
        DS_U8(ds, 0x9A4B) = 255;
        shop_record_visit(ds);
    }
    uint16_t item = 0, counter = 0;
    int gate = shop_check_capacity(g, &item, &counter, host->text, host->screen);
    if (gate)
        return gate < 0 ? -1 : SHOP_ACTION_CLOSED;
    gate = stealing ? shop_check_permit(g, item, host->text, host->screen)
                    : shop_pay_item(g, item, host->text, host->screen);
    if (gate)
        return gate < 0 ? -1 : SHOP_ACTION_CLOSED;
    int added = shop_add_item(g, item, counter, host->menu, host->text, host->screen);
    if (added < 0)
        return -1;
    /* 8652 skips the remainder of either option handler. */
    if (added == SHOP_ADD_NO_WEAPON)
        return SHOP_ACTION_CLOSED;
    if (stealing)
        DS_U8(ds, 0x0374) = 255;
    else
        event_push(EV_SOUND, 23, DS_U8(ds, 0x80E9));
    if (!DS_U8(ds, 0x9950) && close_window(g, host))
        return -1;
    if (stealing) {
        int alarm = shop_check_theft(g, host->files, host->menu, host->text, host->screen);
        if (alarm < 0)
            return -1;
        if (alarm)
            return SHOP_ACTION_EXIT;
    }
    return SHOP_ACTION_CLOSED;
}

typedef struct ShopConfirm {
    const ShopServices *host;
    int exit_shop;
} ShopConfirm;
static int confirm_service(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user)
{
    ShopConfirm *context = (ShopConfirm *)user;
    const MenuPlatform *input = context->host->menu;
    if (op == MM_ACTION) {
        int result = shop_option_action(g, a, context->host);
        if (result < 0)
            return -1;
        if (result == SHOP_ACTION_EXIT)
            context->exit_shop = 1;
        return 1;
    }
    return input && input->call ? input->call(g, op, a, b, input->user) : -1;
}

/* Valid installed mask records/caches required. Menu/IO/input remain platform
 * services; hit tests, dynamic text, options, transfers and resource/AI work native.
 * EXIT means the owner must run 82C4's shop-exit phase, without a mouse-release wait. */
int shop_confirm_item(Game *g, uint16_t x, uint16_t y, const ShopServices *host)
{
    if (!host || !host->menu || !host->menu->call)
        return -1;
    uint8_t *ds = g->ds;
    if (DS_U16(ds, 0x0208)) {
        DS_U16(ds, 0x94E2) = DS_U16(ds, 0x0208);
        DS_U16(ds, 0x94E0) = DS_U16(ds, 0x009D + DS_U16(ds, 0xA612));
    } else if (file_load(g, host->files, DS_U16(ds, 0x9A86), DS_U16(ds, 0x94E2), DS_U16(ds, 0x94E0)) == UINT32_MAX)
        return -1;
    if (DS_U16(ds, 0xA612) == 2 && DS_U8(ds, DS_FACILITY_SCREEN))
        x *= 2;
    uint16_t record = DS_U16(ds, 0x94E0), seg = DS_U16(ds, 0x94E2), index = 0;
    for (;;) {
        if (shop_item_hit(g, seg, record, x, y))
            break;
        ++index;
        record += DS_U16(far_ptr(g, seg, (uint16_t)(record + 14)), 0) + 16;
        if (record >= DS_U16(ds, 0x9A84))
            return 0;
    }
    index *= 2;
    DS_U16(ds, 0x9A70) = index;
    uint16_t source = DS_U16(ds, DS_U16(ds, 0x9A6E) + index), dest = 0x0DD4, textseg = DS_U16(ds, 0xEA36);
    uint8_t ch;
    do {
        ch = DS_U8(ds, source++);
        *far_ptr(g, textseg, dest++) = ch;
    } while (ch);
    source = DS_U16(ds, 0x9A6E) == 0x9BE2 ? 0x0E30 : 0x0E0C;
    do {
        ch = *far_ptr(g, textseg, source++);
        *far_ptr(g, textseg, dest++) = ch;
    } while ((int8_t)ch >= 0);
    ShopConfirm context = {host, 0};
    MenuPlatform menu = {confirm_service, &context};
    int status = DS_U8(ds, DS_FACILITY_SCREEN) ? menu_vga_display(g, host->screen, 0x0DD1, 15, 4, 22, 10, 0x9AA2, &menu)
                                               : menu_display(g, 0x0DD1, 15, 4, 22, 10, 0x9AA2, &menu);
    if (status < 0)
        return -1;
    if (context.exit_shop)
        return SHOP_ACTION_EXIT;
    while (DS_U8(ds, KEY_DOWN(SC_ENTER)))
        if (host->menu->call(g, SHOP_MOUSE_RELEASE, 0, 0, host->menu->user))
            return -1;
    return 0;
}
