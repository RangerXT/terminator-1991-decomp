/* The option handlers of the menus opened during play, and the menus they open.
 *
 *   GAME MENU (Esc, actions DS:7852)     joystick on/off, audio on/off, save, delete, quit,
 *                                        new game, ratings
 *   PLAYER MENU (F10, DS:7968)           inventory, physical status, drop item, special action
 *   "Tell Sarah to..." (Q, DS:E3F0)      stay, run away, follow, give item, take item
 *
 * game_menu_display shows one of them through an adapter over the host's MenuPlatform: a
 * chosen option (MM_ACTION, with the handler's address) runs here when it is translated
 * and goes to the host otherwise; everything else (waits, key releases) goes to the host.
 * Handlers return MENU_CONTINUE (the menu stays), MENU_CLOSED, or MENU_CLOSED_CARRY (closed
 * with the carry flag set, which the inventory menu uses to open again); -1 on a missing
 * service. In the original a closing handler drops menu_run's return address (ADD SP,2)
 * and returns straight to the menu's caller.
 *
 * Still the host's (by original address): saving and deleting games without machine
 * services (4B7E, 4CDE; with them src/savegame.c), the ratings screen without ratings
 * services (D300), the damage panel without its services (5F06), joystick detection and
 * calibration (3A12, 38F6); the time bomb's minutes without ratings services (95A5).
 */
#include "term.h"

enum {
    NOT_HERE = 3,                  /* option() result: not translated, ask the host */
    TEXT_NOTHING_SPECIAL = 0x0A7B, /* "There is nothing special here." */
    TEXT_INVENTORY_MENU = 0x0917,  /* "WHAT TYPE?" weapons, ammunition, clothes, drugs, tools, misc. */
    TEXT_SPECIAL_MENU = 0x0AF9,    /* built by inventory_equipment_menu */
    TEXT_ARE_YOU_SURE = 0x10C1,    /* "Are you sure ?" yes / no */
    QUESTION_QUIT = 0x777C,        /* "Are you sure ? " (in DS) */
    ACTIONS_YES_NO = 0x7811,
    ACTIONS_INVENTORY = 0x7970,
    ACTIONS_DROP = 0x7988,
    ACTIONS_SPECIAL = 0xAAAD,
    ACTIONS_CONFIRM = 0xA974,   /* facility_confirm's yes (8E32) and no (8E40) */
    COMPANION_ACTIONS = 0xE3E2, /* u16[5]: what each of Sarah's orders calls */
    INVENTORY_FLAG = 0x9950,
};

static int game_menu_call(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user);

/* orig 0000:F530 (sign) and F54C   the number at DS:at in base `base`, as the registers
 * leave it: *end is where the digits stop. A multiply that overflows leaves the running
 * value at the digit just read (CX after XCHG); an overflowing add wraps. '-' negates
 * values up to 8000h when the digits were good, '+' is skipped. */
static uint16_t parse_number(const uint8_t *ds, uint16_t at, uint8_t base, uint16_t *end)
{
    uint8_t sign = DS_U8(ds, at);
    if (sign == '-' || sign == '+')
        at++;
    uint16_t cx = 0, flags = 0;
    for (;;) {
        uint8_t ch = DS_U8(ds, at++);
        if (ch < '0')
            break;
        if (ch > '9') {
            if (ch < 'A')
                break;
            ch = (uint8_t)((ch & 0xDF) - 7);
        }
        ch = (uint8_t)(ch - '0');
        if (base <= ch)
            break;
        uint32_t product = (uint32_t)cx * base;
        cx = ch;
        if (product > 0xFFFF) {
            flags |= 2;
            continue;
        }
        uint32_t sum = (uint32_t)cx + (uint16_t)product;
        cx = (uint16_t)sum;
        flags |= sum > 0xFFFF ? 2 : 1;
    }
    *end = (uint16_t)(at - 1);
    if (sign == '-' && flags == 1 && cx <= 0x8000)
        cx = (uint16_t)-cx;
    return cx;
}

/* the records of the special items at DS:0B08 + 8n: x, z, a size, a time */
static void special_place(uint8_t *ds, uint16_t record, uint16_t size, uint16_t time)
{
    point_copy(ds, DS_U16(ds, DS_PLAYER), record);
    DS_U16(ds, (uint16_t)(record + 4)) = size;
    DS_U16(ds, (uint16_t)(record + 6)) = time;
}

/* orig 0000:94DA, 95A5, 965C, 9699, 971D   the special actions (DS:AB2E): use up the item
 * (DS:AAA5, AAA7, AAA8, AAA9) and place its record; 95A5 asks for the minutes of a time
 * bomb. NOT_HERE when a service is missing. */
static int special_action(Game *g, uint16_t target, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    switch (target) {
    case 0x94DA:
    case 0x965C:
    case 0x971D: {
        uint16_t item = target == 0x94DA ? 0xAAA5 : target == 0x965C ? 0xAAA7 : 0xAAA9;
        inventory_remove(ds, DS_U8(ds, item));
        DS_U8(ds, item) = 0;
        inventory_refresh_equipment(g);
        if (target == 0x94DA) {
            special_place(ds, 0x0B10, 0x1E, 0x1388);
            DS_U8(ds, 0xAAD1) = 0xFF;
        } else if (target == 0x965C) {
            special_place(ds, 0x0B18, 0x1E, 0x64);
            DS_U8(ds, 0x0343) = DS_U16(ds, DS_PLAYER) == 0x0508 ? 0x64 : 0x9C;
        } else {
            special_place(ds, 0x0B28, 0x64, 0x64);
            uint16_t player = DS_U16(ds, DS_PLAYER);
            DS_U16(ds, 0x0404) = DS_U16(ds, player);
            DS_U16(ds, 0x0406) = DS_U16(ds, (uint16_t)(player + 4));
        }
        return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;
    }
    case 0x95A5: { /* the time bomb: minutes typed, again until there is a number */
        if (!host->ratings)
            return NOT_HERE;
        special_place(ds, 0x0B08, 0x64, DS_U16(ds, 0x0B0E));
        if (scene_overlay_restore(g) < 0)
            return -1;
        uint16_t minutes;
        for (;;) {
            int typed = name_editor(g, 0x0DAD, 6, 0x0A, 2, host->ratings);
            if (typed < 0)
                return -1;
            if (typed == 1) /* Esc (the carry): ask again */
                continue;
            uint16_t end;
            minutes = parse_number(ds, 0xE3FA, 10, &end);
            if (end != 0xE3FA)
                break;
        }
        DS_U16(ds, 0x0B0E) = (uint16_t)(minutes * 8);
        DS_U8(ds, 0xAAA6) = 0;
        inventory_refresh_equipment(g);
        return MENU_CLOSED;
    }
    case 0x9699: { /* only on foot */
        uint16_t player = DS_U16(ds, DS_PLAYER);
        if (!(DS_U8(ds, (uint16_t)(player + 0x0E)) & 1))
            return textbox_draw(g, 0x037F, 0x0A, 6, 0x1B, 5, host->text) < 0 ? -1 : MENU_CONTINUE;
        inventory_remove(ds, DS_U8(ds, 0xAAA8));
        DS_U8(ds, 0xAAA8) = 0;
        inventory_refresh_equipment(g);
        special_place(ds, 0x0B20, 0x1E, 0x190);
        if (scene_overlay_restore(g) < 0)
            return -1;
        if (DS_U16(ds, DS_PLAYER) == 0x04D4) {
            DS_U8(ds, 0xAA9F) = 1;
            return textbox_draw(g, 0x0C18, 4, 4, 0x21, 8, host->text) < 0 ? -1 : MENU_CLOSED;
        }
        event_push(EV_SOUND, 0x0B, DS_U8(ds, 0x80E9));
        return textbox_draw(g, 0x0CA5, 3, 3, 0x22, 9, host->text) < 0 ? -1 : MENU_CLOSED;
    }
    }
    return NOT_HERE;
}

static MenuPlatform adapter_of(const GameMenuServices *host)
{
    MenuPlatform adapter = {game_menu_call, (void *)host};
    return adapter;
}

static int host_call(Game *g, const GameMenuServices *host, uint16_t op, uint16_t a, uint16_t b)
{
    const MenuPlatform *menu = host->menu;
    return !menu || !menu->call ? -1 : menu->call(g, op, a, b, menu->user);
}

static int display(Game *g, const GameMenuServices *host, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                   uint16_t height, uint16_t actions)
{
    MenuPlatform adapter = adapter_of(host);
    return menu_display(g, text, x, y, width, height, actions, &adapter);
}

int game_menu_display(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t actions,
                      const GameMenuServices *host)
{
    return host ? display(g, host, text, x, y, width, height, actions) : -1;
}

/* orig 0000:8E4E   copy a NUL-terminated string from DS to the text segment; returns its
 * length without the NUL and moves *dest past the NUL */
static uint16_t copy_to_text(Game *g, uint16_t text_seg, uint16_t *dest, uint16_t src)
{
    uint16_t length = 0;
    for (;;) {
        uint8_t ch = DS_U8(g->ds, src++);
        *far_ptr(g, text_seg, (*dest)++) = ch;
        length++;
        if (!ch)
            return (uint16_t)(length - 1);
    }
}

/* orig 0000:8DFF   a yes/no menu with the question at DS:question (sets DS:A87B on yes) */
int facility_confirm(Game *g, uint16_t question, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    uint16_t seg = DS_U16(ds, 0xEA36), at = 0x0299;
    uint16_t length = copy_to_text(g, seg, &at, question);
    copy_to_text(g, seg, &at, 0xA87C); /* "      Yes" */
    copy_to_text(g, seg, &at, 0xA888); /* "      No" */
    *far_ptr(g, seg, at) = 0xFF;
    return display(g, host, 0x0296, 10, 10, (uint16_t)(length + 4), 8, ACTIONS_CONFIRM);
}

/* orig 0000:F5D5 (with F58D, F596)   a signed byte in decimal with a NUL at base:dest */
static void byte_decimal(uint8_t *base, uint16_t dest, uint8_t value)
{
    if (value & 0x80) {
        base[dest++] = '-';
        value = (uint8_t)-value;
    }
    uint8_t digits[3];
    unsigned n = 0;
    do {
        digits[n++] = (uint8_t)(value % 10);
        value /= 10;
    } while (value);
    while (n)
        base[dest++] = (uint8_t)('0' + digits[--n]);
    base[dest] = 0;
}

/* One category's items of the list at DS:list as text lines from text:at on (the shared
 * loop of the viewer, the drop menu and the exchange menu: 5277, 5457, 5850): each shown
 * item is (kind, row, [count in two characters, ' ',] name). Returns the offset after the
 * last line; *rows counts the lines. */
static uint16_t item_lines(Game *g, uint8_t *text, uint16_t at, uint8_t kind, uint8_t row, int8_t category,
                           uint16_t list, int counts, unsigned *rows)
{
    uint8_t *ds = g->ds;
    *rows = 0;
    for (uint16_t item = list; DS_U16(ds, item); item = (uint16_t)(item + 6)) {
        uint8_t group = DS_U8(ds, (uint16_t)(item + 4)), id = DS_U8(ds, (uint16_t)(item + 2));
        int shown = category >= 0 ? group == (uint8_t)category : (group < 1 || group > 5) && id != 0x10 && id != 0xA5;
        if (!shown)
            continue;
        text[at++] = kind;
        text[at++] = ++row;
        ++*rows;
        if (counts) {
            byte_decimal(text, at, DS_U8(ds, (uint16_t)(item + 5)));
            if (!text[(uint16_t)(at + 1)]) { /* one digit: right-align it */
                text[(uint16_t)(at + 1)] = text[at];
                text[at] = ' ';
            }
            at = (uint16_t)(at + 2); /* a third character is overwritten: 200 shows as "-5" */
            text[at++] = ' ';
        }
        uint16_t name = DS_U16(ds, item);
        uint8_t ch;
        do {
            ch = DS_U8(ds, name++);
            text[at++] = ch;
        } while (ch);
    }
    return at;
}

static uint16_t copy_text(uint8_t *text, uint16_t at, uint16_t source)
{
    uint8_t ch;
    do {
        ch = text[source++];
        text[at++] = ch;
    } while (ch);
    return at;
}

/* orig 0000:5216 (entered at 51FD..5211 for categories 1-5, at 5216 for Misc.)   the items
 * of one category in a message box: the INVENTORY header, under Misc. the cash, then each
 * item's count (two characters, right-aligned) and name. Closes the category menu with
 * carry, so the inventory handler shows it again. */
static int inventory_view(Game *g, int8_t category, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    if (scene_overlay_restore(g) < 0)
        return -1;
    uint8_t *text = far_ptr(g, DS_U16(ds, 0xEA36), 0);
    DS_U8(ds, DS_INVENTORY_CATEGORY) = (uint8_t)category;
    uint16_t header = category < 0 ? 0 : (uint16_t)category; /* 0 = "MISC INVENTORY" */
    uint16_t at = copy_text(text, 2, DS_U16(text, (uint16_t)(0x0736 + 2 * header)));
    uint8_t row = 2;
    if (!header && DS_U16(ds, DS_CASH)) {
        text[at++] = 2;
        text[at++] = ++row;
        text[at++] = '$';
        at = number_format(text, at, DS_U16(ds, DS_CASH), 10);
        static const char cash[] = " Cash";
        for (unsigned i = 0; i < sizeof cash; ++i)
            text[at++] = (uint8_t)cash[i];
    }
    unsigned rows;
    at = item_lines(g, text, at, 2, row, category, 0x05B0, 1, &rows);
    text[at] = 0xFF;
    return textbox_draw(g, 2, 5, 0, 0x19, 0x19, host->text) < 0 ? -1 : MENU_CLOSED_CARRY;
}

/* orig 0000:5437 (entered at 541B..542F for categories 1-5, at 5434 for Misc.)   "DROP
 * WHAT?": the category's items as a menu (actions DS:7994, one per line), or "You have
 * nothing to drop." */
static int drop_menu(Game *g, int8_t category, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    if (scene_overlay_restore(g) < 0)
        return -1;
    uint8_t *text = far_ptr(g, DS_U16(ds, 0xEA36), 0);
    DS_U8(ds, DS_INVENTORY_CATEGORY) = (uint8_t)category;
    unsigned rows;
    uint16_t at = item_lines(g, text, copy_text(text, 2, 0x095F), 4, 2, category, 0x05B0, 1, &rows);
    if (!rows)
        return textbox_draw(g, 0x0A2E, 0x0A, 3, 0x0D, 7, host->text) < 0 ? -1 : MENU_CLOSED;
    text[at] = 0xFF;
    return display(g, host, 2, 2, 0, 0x1A, 0x19, 0x7994) < 0 ? -1 : MENU_CLOSED;
}

/* orig 0000:565B   leave the item at the player's feet: a 13-byte record (position, name,
 * id and weight, category) in the ring of 20 at DS:0253, next slot DS:03FC; the carried
 * weight DS:116C goes down by the item's */
static void drop_in_world(Game *g, uint16_t item)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, DS_CARRIED_WEIGHT) =
        (uint16_t)(DS_U16(ds, DS_CARRIED_WEIGHT) - (uint16_t)(int16_t)(int8_t)DS_U8(ds, (uint16_t)(item + 3)));
    uint16_t slot = DS_U16(ds, DS_DROPPED_NEXT), player = DS_U16(ds, DS_PLAYER);
    uint16_t record = (uint16_t)(0x0253 + 13 * (uint8_t)slot);
    DS_U16(ds, record) = DS_U16(ds, (uint16_t)(player + 0x1E));
    DS_U16(ds, (uint16_t)(record + 2)) = DS_U16(ds, (uint16_t)(player + 0x20));
    DS_U16(ds, (uint16_t)(record + 4)) = DS_U16(ds, player);
    DS_U16(ds, (uint16_t)(record + 6)) = DS_U16(ds, (uint16_t)(player + 4));
    DS_U16(ds, (uint16_t)(record + 8)) = DS_U16(ds, item);
    DS_U8(ds, (uint16_t)(record + 10)) = DS_U8(ds, (uint16_t)(item + 2));
    DS_U8(ds, (uint16_t)(record + 11)) = DS_U8(ds, (uint16_t)(item + 3));
    DS_U8(ds, (uint16_t)(record + 12)) = DS_U8(ds, (uint16_t)(item + 4));
    DS_U16(ds, DS_DROPPED_NEXT) = slot == 0x13 ? 0 : (uint16_t)(slot + 1);
}

/* orig 0000:551B (entered at 551A..5507 for the 1st..20th line)   drop the chosen item.
 * It is found again by category, where Misc. means category 6 only (the menu also listed
 * categories 0 and 7 and up), and the search has no end. */
static int drop_item(Game *g, uint16_t line, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    uint8_t category = DS_U8(ds, DS_INVENTORY_CATEGORY);
    if (category == 0xFF)
        category = 6;
    uint16_t item = 0x05B0;
    while (DS_U8(ds, (uint16_t)(item + 4)) != category || --line)
        item = (uint16_t)(item + 6);
    drop_in_world(g, item);
    inventory_remove(ds, DS_U8(ds, (uint16_t)(item + 2)));
    return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;
}

/* orig 0000:57D4 (give: from the player's list 05B0 to Sarah's 085C) and 57E7 (take: the
 * other way, DS:0252 = FF)   the categories (actions DS:79E4), then the items. The
 * "Tell Sarah to..." menu opens them, and so do companion modes 3 and 4 in the world step. */
int companion_exchange(Game *g, int take, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    DS_U8(ds, DS_EXCHANGE_TAKE) = take ? 0xFF : 0;
    DS_U16(ds, DS_ITEMS_FROM) = take ? 0x085C : 0x05B0; /* from */
    DS_U16(ds, DS_ITEMS_TO) = take ? 0x05B0 : 0x085C;   /* to */
    return display(g, host, TEXT_INVENTORY_MENU, 5, 4, 0x12, 0x14, 0x79E4);
}

/* orig 0000:582A (entered at 580E..5822 for categories 1-5, at 5827 for Misc.)   "GIVE SARAH
 * WHAT?" / "TAKE WHAT FROM SARAH?": the names of the category's items in the list DS:03FE
 * as a menu (actions DS:79F0), or "There is nothing here to exchange." */
static int exchange_menu(Game *g, int8_t category, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    uint8_t *text = far_ptr(g, DS_U16(ds, 0xEA36), 0);
    DS_U8(ds, DS_INVENTORY_CATEGORY) = (uint8_t)category;
    uint16_t at = copy_text(text, 2, DS_U8(ds, DS_EXCHANGE_TAKE) ? 0x0992 : 0x097E);
    unsigned rows;
    at = item_lines(g, text, at, 4, 2, category, DS_U16(ds, DS_ITEMS_FROM), 0, &rows);
    int status;
    if (!rows)
        status = textbox_draw(g, 0x0A50, 0x0A, 3, 0x0F, 7, host->text);
    else {
        text[at] = 0xFF;
        status = display(g, host, 2, 2, 0, 0x1A, 0x19, 0x79F0);
    }
    if (status < 0 || scene_overlay_restore(g) < 0)
        return -1;
    return MENU_CLOSED;
}

/* orig 0000:58F9 (entered at 58F8..58E5 for the 1st..20th line)   move one of the chosen
 * item, found again by category as in drop_item. Sarah's load DS:0402 may not reach 35
 * ("This item is too heavy for Sarah to carry."); taking from her lowers it - below 0 it
 * wraps and is refused the same way. */
static int exchange_item(Game *g, uint16_t line, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    uint8_t category = DS_U8(ds, DS_INVENTORY_CATEGORY);
    if (category == 0xFF)
        category = 6;
    uint16_t item = DS_U16(ds, DS_ITEMS_FROM);
    while (DS_U8(ds, (uint16_t)(item + 4)) != category || --line)
        item = (uint16_t)(item + 6);
    uint16_t weight = DS_U8(ds, (uint16_t)(item + 3));
    uint16_t load = (uint16_t)(DS_U16(ds, DS_SARAH_LOAD) + weight);
    if (DS_U8(ds, DS_EXCHANGE_TAKE))
        load = (uint16_t)(load - 2 * weight);
    if (load >= 0x23) {
        if (textbox_draw(g, 0x0AA2, 0x0F, 8, 0x10, 8, host->text) < 0)
            return -1;
    } else {
        DS_U16(ds, DS_SARAH_LOAD) = load;
        uint8_t id = DS_U8(ds, (uint16_t)(item + 2));
        inventory_transfer(ds, DS_U16(ds, DS_ITEMS_TO), id, 0);
        inventory_transfer(ds, item, id, 1);
    }
    return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;
}

/* The handlers; target is the handler's address in the action table. */
static int option(Game *g, uint16_t target, const GameMenuServices *host)
{
    uint8_t *ds = g->ds;
    switch (target) {
    case 0x4B4A: /* audio on/off, and the yes/no answers: already in menu.c */
    case 0x4ED2:
    case 0x4EDC:
    case 0x4EEB:
        return menu_basic_action(g, target, host->menu);

    case 0x4F02: /* joystick on/off */
        if (scene_overlay_restore(g) < 0)
            return -1;
        if (!DS_U8(ds, DS_JOYSTICK)) {
            int absent = host_call(g, host, GM_JOYSTICK_DETECT, 0, 0);
            if (absent < 0)
                return -1;
            if (!absent) {
                if (host_call(g, host, GM_JOYSTICK_CALIBRATE, 0, 0) < 0)
                    return -1;
                DS_U8(ds, DS_JOYSTICK) = 1;
                return MENU_CLOSED;
            }
        }
        DS_U8(ds, DS_JOYSTICK) = 0;
        return MENU_CLOSED;

    case 0x4E86: /* quit */
        DS_U8(ds, DS_FACILITY_CONFIRMED) = 0;
        if (facility_confirm(g, QUESTION_QUIT, host) < 0)
            return -1;
        if (DS_U8(ds, DS_FACILITY_CONFIRMED))
            DS_U8(ds, DS_MISSION_OVER) = 0x55;
        return MENU_CLOSED_CARRY;

    case 0x4EA2: /* new game */
        if (scene_overlay_restore(g) < 0 || display(g, host, TEXT_ARE_YOU_SURE, 5, 8, 0x12, 9, ACTIONS_YES_NO) < 0)
            return -1;
        if (DS_U8(ds, DS_MENU_YES))
            DS_U8(ds, DS_MISSION_OVER) = 0xAA;
        return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;

    case 0x4B7E: /* save (the name editor needs the ratings services), delete */
    case 0x4CDE: {
        if (!host->machine || (target == 0x4B7E && !host->ratings))
            return NOT_HERE;
        SaveGameServices saves = {host, host->machine};
        return target == 0x4B7E ? savegame_save_action(g, &saves) : savegame_delete_action(g, &saves);
    }

    case 0x4EFA: /* ratings */
        return (host->ratings ? ratings_screen(g, host->ratings) : host_call(g, host, GM_RATINGS, 0, 0)) < 0
                   ? -1
                   : MENU_CLOSED;

    case 0x51D8: { /* inventory: the category menu, again while a panel asks for it (carry) */
        DS_U8(ds, INVENTORY_FLAG) = 0xFF;
        if (scene_overlay_restore(g) < 0)
            return -1;
        int status;
        do {
            status = display(g, host, TEXT_INVENTORY_MENU, 5, 4, 0x12, 0x12, ACTIONS_INVENTORY);
            if (status < 0)
                return -1;
        } while (status == MENU_CLOSED_CARRY);
        return MENU_CLOSED;
    }

    case 0x51FD: /* the inventory's categories: weapons, ammunition, clothes, drugs, tools, misc. */
    case 0x5202:
    case 0x5207:
    case 0x520C:
    case 0x5211:
        return inventory_view(g, (int8_t)((target - 0x51FD) / 5 + 1), host);
    case 0x5216:
        return inventory_view(g, -1, host);

    case 0x541B: /* drop item: the categories, then the line chosen */
    case 0x5420:
    case 0x5425:
    case 0x542A:
    case 0x542F:
        return drop_menu(g, (int8_t)((target - 0x541B) / 5 + 1), host);
    case 0x5434:
        return drop_menu(g, -1, host);

    case 0x5309: /* physical status */
        if ((host->damage ? damage_panel(g, host->damage) : host_call(g, host, GM_DAMAGE_PANEL, 0, 0)) < 0)
            return -1;
        DS_U16(ds, DS_VISIBLE_CELL) = 0xFFFF;
        return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;

    case 0x53F5: /* drop item; the HUD is rebuilt after */
        if (scene_overlay_restore(g) < 0 || display(g, host, TEXT_INVENTORY_MENU, 5, 4, 0x12, 0x14, ACTIONS_DROP) < 0)
            return -1;
        hud_choose_panel(ds);
        return hud_init_normal(g, host->images) < 0 ? -1 : MENU_CLOSED;

    case 0x578A: /* special action */
        if (scene_overlay_restore(g) < 0)
            return -1;
        if (DS_U8(ds, DS_SPECIAL_MENU_READY)) {
            uint16_t height = DS_U16(ds, DS_SPECIAL_MENU_HEIGHT);
            uint16_t y = (uint16_t)(10 - (height >> 1));
            return display(g, host, TEXT_SPECIAL_MENU, 2, y, 0x24, height, ACTIONS_SPECIAL) < 0 ? -1 : MENU_CLOSED;
        }
        return textbox_draw(g, TEXT_NOTHING_SPECIAL, 8, 2, 0x10, 7, host->text) < 0 ? -1 : MENU_CLOSED;

    case 0x8E32: /* facility_confirm: yes, no */
    case 0x8E40:
        DS_U8(ds, DS_FACILITY_CONFIRMED) = target == 0x8E32 ? 0xFF : 0;
        return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;

    case 0xDD2F: /* Sarah: take item, give item, follow, run away, stay (entered at DD33 - order) */
    case 0xDD30:
    case 0xDD31:
    case 0xDD32:
    case 0xDD33: {
        uint16_t order = (uint16_t)(0xDD33 - target);
        uint16_t action = DS_U16(ds, (uint16_t)(COMPANION_ACTIONS + 2 * order));
        if (order <= 2)
            DS_U16(ds, DS_COMPANION_ORDER) = order;
        else if (action == 0x57E7 || action == 0x57D4) {
            if (companion_exchange(g, action == 0x57E7, host) < 0)
                return -1;
        } else if (host_call(g, host, action, 0, 0) < 0)
            return -1;
        return scene_overlay_restore(g) < 0 ? -1 : MENU_CLOSED;
    }
    }
    if (target == 0x94DA || target == 0x95A5 || target == 0x965C || target == 0x9699 || target == 0x971D)
        return special_action(g, target, host);
    if (target >= 0x5507 && target <= 0x551A)
        return drop_item(g, (uint16_t)(0x551B - target), host);
    if (target >= 0x580E && target <= 0x5822 && (target - 0x580E) % 5 == 0)
        return exchange_menu(g, (int8_t)((target - 0x580E) / 5 + 1), host);
    if (target == 0x5827)
        return exchange_menu(g, -1, host);
    if (target >= 0x58E5 && target <= 0x58F8)
        return exchange_item(g, (uint16_t)(0x58F9 - target), host);
    return NOT_HERE;
}

static int game_menu_call(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user)
{
    const GameMenuServices *host = (const GameMenuServices *)user;
    if (op == MM_ACTION) {
        int status = option(g, a, host);
        if (status != NOT_HERE)
            return status;
    }
    return host_call(g, host, op, a, b);
}

/* one of the menus' actions by its original address, as a menu would run it (the host's
 * when it is not translated) */
int game_menu_action(Game *g, uint16_t target, const GameMenuServices *host)
{
    if (!host)
        return -1;
    int status = option(g, target, host);
    return status != NOT_HERE ? status : host_call(g, host, MM_ACTION, target, 0);
}
