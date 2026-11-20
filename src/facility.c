/* The facility screens the shops lead to (0000:8CB0, entered from the shop screen for kinds
 * 4..6): the bank (4), the firing range (5), the hospital (6). Only Kyle Reese (DS:03A0 =
 * 04D4) is served: the hospital treats him and the bank pays out once; the Terminator sets
 * off the hospital's alarm and can only rob the bank.
 */
#include "term.h"

enum {
    FA_VGA_IMAGES = 0xA968, /* u16[3]: bank256.img, range256.img, hosp256.img */
    FA_EGA_IMAGES = 0xA96E, /* u16[3]: bank.img, range.img, hosp.img */
    FA_BANK_ACTIONS = 0xA97E,
    FA_TREATMENT = 0xA87A,  /* u8: the damage panel is the hospital's */
    FA_BANK_ALARM = 0xA917, /* u8: the alarm is the bank's */
    FA_WITHDRAWN = 0x115B,  /* u8: Reese has had his money */
    FA_REESE = 0x04D4,
};

static int resource(Game *g, const FacilityServices *host, uint16_t op, uint16_t a)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, 0, r->user) ? -1 : 0;
}

static int menu_op(Game *g, const FacilityServices *host, uint16_t op, uint16_t a)
{
    const MenuPlatform *menu = host->menus ? host->menus->menu : NULL;
    return !menu || !menu->call || menu->call(g, op, a, 0, menu->user) ? -1 : 0;
}

/* the sample groups: 8ADE (mode 4, inside) and 8ABE (mode 3, on foot); without a sound
 * service, the host's */
static int samples(Game *g, const FacilityServices *host, uint8_t mode)
{
    if (host->sound)
        return sound_group_select(g, host->sound, mode);
    return menu_op(g, host, mode == 4 ? 0x8ADE : 0x8ABE, 0);
}

static int alarm(Game *g, const FacilityServices *host)
{
    const GameMenuServices *menus = host->menus;
    return shop_alarm(g, host->images, menus ? menus->menu : NULL, menus ? menus->text : NULL, host->screen);
}

/* orig 0000:8DDF */
static int steal_cash(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, DS_CASH) = (uint16_t)(DS_U16(ds, DS_CASH) + (random_word(ds) & 0x1FFF));
    DS_U8(ds, (uint16_t)(DS_U16(ds, DS_PLAYER) + 0x32)) += 0x0A;
    DS_U8(ds, 0x7A18) = 0;
    if (alarm(g, host) < 0)
        return -1;
    DS_U8(ds, 0x8447) = 0;
    return 0;
}

/* the overlay restore of 5776:0247, which on the mode-13h screen is 11BC:2B91 */
static int restore(Game *g, const FacilityServices *host)
{
    if (!DS_U8(g->ds, DS_FACILITY_SCREEN))
        return scene_overlay_restore(g);
    if (!host->screen)
        return -1;
    scene_vga_overlay_restore(g, host->screen);
    return 0;
}

/* the facility menus' actions: yes / no (8E32 / 8E40) and the bank's rob / withdraw (8DD3 /
 * 8DBB); anything else goes to the host */
static int facility_menu_call(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user)
{
    const FacilityServices *host = user;
    uint8_t *ds = g->ds;
    if (op == MM_ACTION && (a == 0x8E32 || a == 0x8E40 || a == 0x8DD3 || a == 0x8DBB)) {
        if (a == 0x8E32 || a == 0x8E40)
            DS_U8(ds, DS_FACILITY_CONFIRMED) = a == 0x8E32 ? 0xFF : 0;
        else if (a == 0x8DBB) { /* orig 0000:8DBB */
            DS_U8(ds, FA_WITHDRAWN) = 0xFF;
            DS_U16(ds, DS_CASH) = (uint16_t)(DS_U16(ds, DS_CASH) + (random_word(ds) & 0x0FFF));
        } else if (steal_cash(g, host) < 0) /* orig 0000:8DD3 */
            return -1;
        return restore(g, host) < 0 ? -1 : MENU_CLOSED;
    }
    const MenuPlatform *menu = host->menus ? host->menus->menu : NULL;
    return !menu || !menu->call ? -1 : menu->call(g, op, a, b, menu->user);
}

/* the menu routine 4A0B: the mode-13h menu on the facility screen */
static int show_menu(Game *g, const FacilityServices *host, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                     uint16_t height, uint16_t actions)
{
    MenuPlatform adapter = {facility_menu_call, (void *)host};
    if (!DS_U8(g->ds, DS_FACILITY_SCREEN))
        return menu_display(g, text, x, y, width, height, actions, &adapter);
    return host->screen ? menu_vga_display(g, host->screen, text, x, y, width, height, actions, &adapter) : -1;
}

/* orig 0000:8DFF (with 8E4E)   yes / no under the question at DS:question */
static int confirm(Game *g, const FacilityServices *host, uint16_t question)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0xEA36), at = 0x0299, length = 0;
    uint8_t *text = far_ptr(g, seg, 0);
    for (uint16_t from = question;; ++length) {
        uint8_t ch = text[at++] = DS_U8(ds, from++);
        if (!ch)
            break;
    }
    for (uint16_t from = 0xA87C; (text[at++] = DS_U8(ds, from++));) /* "      Yes" */
        ;
    for (uint16_t from = 0xA888; (text[at++] = DS_U8(ds, from++));) /* "      No" */
        ;
    text[at] = 0xFF;
    return show_menu(g, host, 0x0296, 10, 10, (uint16_t)(length + 4), 8, 0xA974);
}

/* orig 0000:8D6B */
static int bank(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    if (samples(g, host, 4) < 0)
        return -1;
    DS_U8(ds, FA_BANK_ALARM) = 0xFF;
    if (DS_U16(ds, DS_PLAYER) == FA_REESE && !DS_U8(ds, FA_WITHDRAWN)) {
        if (show_menu(g, host, 0x0311, 10, 10, 0x14, 9, FA_BANK_ACTIONS) < 0)
            return -1;
    } else {
        if (confirm(g, host, 0xA8F4) < 0)
            return -1;
        if (DS_U8(ds, DS_FACILITY_CONFIRMED)) {
            if (steal_cash(g, host) < 0)
                return -1;
            DS_U16(ds, 0x854A) = 1;
            world_toggle_records(ds);
        }
    }
    DS_U8(ds, FA_BANK_ALARM) = 0;
    return samples(g, host, 3);
}

/* orig 0000:8D21 */
static int hospital(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    if (samples(g, host, 4) < 0)
        return -1;
    if (DS_U16(ds, DS_PLAYER) != FA_REESE) {
        const TextPlatform *text = host->menus ? host->menus->text : NULL;
        int shown = DS_U8(ds, DS_FACILITY_SCREEN) ? textbox_vga_draw(g, host->screen, 0x03F8, 0x0C, 0x0F, 0x1A, 6, text)
                                                  : textbox_draw(g, 0x03F8, 0x0C, 0x0F, 0x1A, 6, text);
        if (shown < 0)
            return -1;
        DS_U8(ds, 0x7A18) = 0xFF;
        if (alarm(g, host) < 0)
            return -1;
        DS_U8(ds, 0x7A18) = 0;
    } else {
        if (confirm(g, host, 0xA8DF) < 0)
            return -1;
        if (DS_U8(ds, DS_FACILITY_CONFIRMED)) {
            DS_U8(ds, FA_TREATMENT) = 0xFF;
            const DamagePanelServices *damage = host->menus ? host->menus->damage : NULL;
            if (damage ? damage_panel(g, damage) < 0 : menu_op(g, host, GM_DAMAGE_PANEL, 0) < 0)
                return -1;
            DS_U8(ds, FA_TREATMENT) = 0;
        }
    }
    return samples(g, host, 3);
}

/* ---------------------------------------------------------------- the firing range */

enum {
    RG_TARGET2 = 0xA958,   /* u16: target number times two */
    RG_OFFSET = 0xA95A,    /* u16: screen offset of the target */
    RG_AVG_TICKS = 0xA95C,
    RG_AVG_PENALTY = 0xA95E,
    RG_SUM_TICKS = 0xA960,
    RG_SUM_PENALTY = 0xA962,
    RG_TIMER = 0xA964,     /* u16: counted up by the timer interrupt */
    RG_PREVIOUS = 0xA966,  /* u16: the last target, never shown twice in a row */
    RG_CLASS = 0xA9A8,     /* u16: the rank 0..6 */
};

static int text8(Game *g, const FacilityServices *host, uint16_t text)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN)) {
        if (!host->screen)
            return -1;
        screen_text8_vga(g, host->screen, g->ds_seg, text);
        return 0;
    }
    return screen_text8(g, g->ds_seg, text) < 0 ? -1 : 0;
}

/* orig 0000:8EA5 */
static int draw_target(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t target;
    do
        target = random_word(ds) & 7;
    while (target == DS_U16(ds, RG_PREVIOUS));
    DS_U16(ds, RG_PREVIOUS) = target;
    uint16_t index = (uint16_t)(target * 2);
    DS_U16(ds, RG_TARGET2) = index;
    if (DS_U8(ds, DS_FACILITY_SCREEN)) { /* an 8x8 mask in colour FF, rows two bytes apart */
        uint16_t at = DS_U16(ds, RG_OFFSET) = DS_U16(ds, (uint16_t)(0xA948 + index)), from = 0x7C30;
        uint8_t *screen = host->screen; /* the segment at DS:ADDC: A000 */
        if (!screen)
            return -1;
        for (unsigned row = 0; row < 8; ++row, from = (uint16_t)(from + 2), at = (uint16_t)(at + 0x138)) {
            uint8_t bits = DS_U8(ds, from);
            for (unsigned x = 0; x < 8; ++x, at++, bits = (uint8_t)(bits << 1))
                if (bits & 0x80)
                    screen[at] = 0xFF;
        }
        return 0;
    }
    uint16_t at = DS_U16(ds, RG_OFFSET) = DS_U16(ds, (uint16_t)(0xA938 + index));
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    *far_ptr(g, code, 0x1B41) = 0x0F;
    screen_blit_mask(g, g->ds_seg, 0x7C30, at, 1, 8, 0x0F, DS_U16(far_ptr(g, code, 0x1B42), 0));
    screen_copy_rect(g, 0, 0x2000, 0x28, 0xC8);
    return 0;
}

/* orig 0000:8F1C */
static int restore_target(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t at = DS_U16(ds, RG_OFFSET);
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        uint8_t *screen = host->screen; /* the segment at DS:ADDC: A000 */
        if (!screen)
            return -1;
        for (unsigned row = 0; row < 8; ++row, at = (uint16_t)(at + 0x140))
            for (unsigned x = 0; x < 8; ++x)
                screen[(uint16_t)(at + x)] = 0;
        return 0;
    }
    hud_clear_bytes(g, at, 1);
    hud_clear_bytes(g, (uint16_t)(at + 0x78), 1);
    screen_copy_rect(g, 0, 0x2000, 0x28, 0xC8);
    return 0;
}

/* orig 0000:8F78   aim until Enter or Tab, or 300 ticks. *ticks and *penalty are the
 * original's AX and BX: the time, and twice the horizontal distance from the target's centre
 * (10 when over 8); a vertical miss over 8 also gives 10, and otherwise never counts. */
static int aim(Game *g, const FacilityServices *host, uint16_t *ticks, uint16_t *penalty)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0x724C) = 0x12C;
    DS_U16(ds, RG_TIMER) = 0;
    int shot;
    for (;;) {
        if (resource(g, host, 0x0D8D, 0) < 0 || resource(g, host, 0x0DAA, 0) < 0)
            return -1;
        if (map_pointer_step_display(g, host->screen) < 0)
            return -1;
        shot = DS_U8(ds, KEY_DOWN(SC_ENTER)) || DS_U8(ds, KEY_DOWN(SC_TAB));
        if (shot || DS_U16(ds, RG_TIMER) >= 0x12C)
            break;
    }
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        if (!host->screen)
            return -1;
        screen_restore_mask16_vga(g, host->screen);
    } else
        map_restore_pointer(g);
    DS_U16(ds, 0x1210) = 0;
    if (!shot) {
        *ticks = DS_U16(ds, RG_TIMER);
        *penalty = 10;
        return 0;
    }
    event_push(EV_SOUND, 3, DS_U8(ds, 0x80E9));
    uint16_t at = (uint16_t)(0xA918 + DS_U16(ds, RG_TARGET2) * 2);
    uint16_t dx = (uint16_t)((uint16_t)(DS_U16(ds, at) + 4 - (uint16_t)(DS_U16(ds, DS_POINTER_X) + 6)) * 2);
    uint16_t dy =
        (uint16_t)((uint16_t)(DS_U16(ds, (uint16_t)(at + 2)) + 4 - (uint16_t)(DS_U16(ds, DS_POINTER_Y) + 6)) * 2);
    uint16_t result = (int16_t)dx < 0 ? (uint16_t)-dx : dx;
    if ((int16_t)dy < 0)
        dy = (uint16_t)-dy;
    if (result > 8)
        result = 10;
    if (dy > 8)
        result = 10;
    *ticks = DS_U16(ds, RG_TIMER);
    *penalty = result;
    return 0;
}

/* orig 0000:9032   the averages as text: seconds (ticks * 100 / 60, as whole and hundredths)
 * at DS:7795, the penalty and its remainder of six at DS:77A9 */
static void format_averages(uint8_t *ds)
{
    uint16_t ticks = DS_U16(ds, RG_AVG_TICKS) = (uint16_t)(DS_U16(ds, RG_SUM_TICKS) / 6);
    uint16_t hundredths = (uint16_t)((uint32_t)ticks * 100 / 60);
    uint16_t at = number_format(ds, 0x7795, (uint16_t)(hundredths / 100), 10);
    DS_U8(ds, at) = '.';
    number_decimal(ds, (uint16_t)(at + 1), (uint16_t)(hundredths % 100));
    uint16_t sum = DS_U16(ds, RG_SUM_PENALTY);
    DS_U16(ds, RG_AVG_PENALTY) = (uint16_t)(sum / 6);
    at = number_format(ds, 0x77A9, (uint16_t)(sum / 6), 10);
    DS_U8(ds, at) = '.';
    number_decimal(ds, (uint16_t)(at + 1), (uint16_t)(sum % 6));
}

/* orig 0000:9169   a rectangle outline from (x, y), width w, height h, in colour 1 */
static void outline(Game *g, const FacilityServices *host, uint16_t x, uint16_t y, uint16_t w, uint16_t h)
{
    uint8_t *ds = g->ds;
    uint16_t xs[4] = {(uint16_t)(x + w), (uint16_t)(x + w), x, x};
    uint16_t ys[4] = {y, (uint16_t)(y + h), (uint16_t)(y + h), y};
    int vga = DS_U8(ds, DS_FACILITY_SCREEN) != 0;
    if (vga)
        DS_U8(ds, DS_TEXT_COLOUR) = 1;
    else
        DS_U8(ds, DS_FILL_COLOUR) = 1;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
    for (unsigned i = 0; i < 4; ++i) {
        if (vga) {
            if (host->screen)
                screen_vga_line_to(ds, host->screen, xs[i], ys[i]);
        } else
            line_to(ds, g->planes, xs[i], ys[i]);
    }
}

/* orig 0000:90B0 (with 9132, 907C)   the rank, its picture, the box round it and the averages;
 * then a key */
static int show_results(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    format_averages(ds);
    uint16_t rank = 0, at = 0xA9AA;
    for (; rank < 6; ++rank, at = (uint16_t)(at + 4))
        if (DS_U16(ds, RG_AVG_TICKS) <= DS_U16(ds, at) && DS_U16(ds, RG_AVG_PENALTY) < DS_U16(ds, (uint16_t)(at + 2)))
            break;
    DS_U16(ds, RG_CLASS) = rank;
    int vga = DS_U8(ds, DS_FACILITY_SCREEN) != 0;
    uint16_t seg = DS_U16(ds, DS_FILE_BUFFER_SEG), off = DS_U16(ds, DS_FILE_BUFFER);
    if (file_load(g, host->images, vga ? 0xA90B : 0xA902, seg, off) == UINT32_MAX)
        return -1;
    if (vga) { /* 9132: a raw picture, its size and place in the header, data from offset 10h */
        const uint8_t *picture = far_ptr(g, seg, 0);
        uint16_t width = (uint16_t)(picture[(uint16_t)(off + 4)] | picture[(uint16_t)(off + 5)] << 8);
        uint16_t rows = (uint16_t)(picture[(uint16_t)(off + 6)] | picture[(uint16_t)(off + 7)] << 8);
        uint16_t px = (uint16_t)(picture[(uint16_t)(off + 8)] | picture[(uint16_t)(off + 9)] << 8);
        uint16_t py = (uint16_t)(picture[(uint16_t)(off + 10)] | picture[(uint16_t)(off + 11)] << 8);
        uint8_t *screen = host->screen; /* the segment at DS:ADDC: A000 */
        if (!screen)
            return -1;
        uint16_t to = (uint16_t)(py * 0x140 + px), from = 0x10;
        do { /* LOOP */
            for (uint16_t n = width, d = to; n; --n)
                screen[d++] = picture[from++];
            if (width & 1)
                from++;
            to = (uint16_t)(to + 0x140);
        } while (--rows);
    } else {
        uint16_t ax;
        if (image_unpack_compressed(g, seg, off, seg, 0x0BB8, &ax) < 0)
            return -1;
        screen_blit_planar(g, seg, 0x0BB8);
    }
    outline(g, host, 0x66, (uint16_t)((uint8_t)(0x10 * (uint8_t)rank) + 0x3E), 0x7B, 0x0F);
    DS_U16(ds, DS_TEXT_COLUMN) = 0x16;
    DS_U16(ds, DS_TEXT_ROW) = 4;
    DS_U8(ds, 0xE41C) = 4;
    if (text8(g, host, 0x7795) < 0)
        return -1;
    DS_U16(ds, DS_TEXT_COLUMN) = 0x16;
    DS_U16(ds, DS_TEXT_ROW) = 5;
    DS_U8(ds, 0xE41C) = 5;
    if (text8(g, host, 0x77A9) < 0)
        return -1;
    DS_U8(ds, 0xE41C) = 0;
    map_clear_key_buffer(ds);
    return keyboard_read(g, host->keys) == UINT32_MAX ? -1 : 0;
}

/* orig 0000:8E59   six targets, then the results */
static int firing_range(Game *g, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, RG_PREVIOUS) = 0xFFFF;
    DS_U16(ds, RG_SUM_PENALTY) = 0;
    DS_U16(ds, RG_SUM_TICKS) = 0;
    if (file_load(g, host->images, 0xA8D4, g->ds_seg, 0x7C20) == UINT32_MAX)
        return -1;
    for (uint16_t i = 0; i < 0x13; ++i) /* 8F6C */
        DS_U16(ds, (uint16_t)(0x7BF0 + i * 2)) = DS_U16(ds, (uint16_t)(0xA982 + i * 2));
    DS_U16(ds, DS_POINTER_X) = 0xA0;
    DS_U16(ds, DS_POINTER_Y) = 0x64;
    for (unsigned round = 0; round < 6; ++round) {
        DS_U16(ds, RG_TIMER) = 0xFF88; /* 9023: wait until the timer has counted 120 ticks */
        while (DS_U16(ds, RG_TIMER))
            if (resource(g, host, FA_TICK, 0) < 0)
                return -1;
        if (draw_target(g, host) < 0)
            return -1;
        uint16_t ticks, penalty;
        if (aim(g, host, &ticks, &penalty) < 0)
            return -1;
        DS_U16(ds, RG_SUM_TICKS) = (uint16_t)(DS_U16(ds, RG_SUM_TICKS) + ticks);
        DS_U16(ds, RG_SUM_PENALTY) = (uint16_t)(DS_U16(ds, RG_SUM_PENALTY) + penalty);
        if (restore_target(g, host) < 0)
            return -1;
    }
    if (show_results(g, host) < 0)
        return -1;
    /* 6149: the HUD numbers and the pointer back */
    if (file_load(g, host->images, 0x7BA6, g->ds_seg, 0x7C20) == UINT32_MAX
        || file_load(g, host->images, 0x7BB2, g->ds_seg, 0x7BF0) == UINT32_MAX)
        return -1;
    return 0;
}

/* orig 0000:8CB0   kind 4 (bank), 5 (firing range), 6 (hospital) */
int facility_screen(Game *g, uint16_t kind, const FacilityServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || kind < 4 || kind > 6)
        return -1;
    uint16_t index = (uint16_t)((kind - 4) * 2);
    uint8_t vga = DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    if (vga) {
        if (resource(g, host, MS_VIDEO_MODE, 0x13) < 0 || !host->screen
            || image_vga_load(g, host->images, DS_U16(ds, (uint16_t)(FA_VGA_IMAGES + index)), host->screen,
                              host->palette) < 0)
            return -1;
    } else {
        if (resource(g, host, MS_VIDEO_MODE, 0x0D) < 0 || resource(g, host, MS_SELECT_PAGES, 0) < 0
            || image_load_screen(g, host->images, DS_U16(ds, (uint16_t)(FA_EGA_IMAGES + index))) < 0)
            return -1;
        DS_U16(ds, 0x7D28) = 0x2000;
        screen_copy_rect(g, 0, 0x2000, 0x28, 0xC8);
    }
    int status = kind == 4 ? bank(g, host) : kind == 6 ? hospital(g, host) : firing_range(g, host);
    if (status < 0)
        return -1;
    if (vga)
        DS_U8(ds, DS_FACILITY_SCREEN) = 0;
    DS_U16(ds, DS_VISIBLE_CELL) = 0xFFFE;
    if (update_visible_cells(g, host->images) < 0)
        return -1;
    return camera_reset(g, host->resources, host->images);
}
