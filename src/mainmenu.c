/* The main menu (0000:9922): the settings screen before each game. Hotkeys set the options
 * (DS:AD32: key, option, value): character, game length, difficulty, detail, controls,
 * practice mode, and run load game, start, ratings and quit; V shows the version. On a VGA
 * installation the options are part of the picture and the chosen ones are lit through
 * DAC registers; on EGA they are written in the scalable font, the hotkey letter coloured.
 */
#include "term.h"

enum {
    MN_KEYS = 0xAD32,     /* 18 x (key, option, value) */
    MN_RECORDS = 0xAD68,  /* u16[10]: per option: count, x, y, then the choices */
    MN_HANDLERS = 0xAD7C, /* u16[10] */
    MN_RADIO = 0xAD90,    /* u8[10]: the option is a choice (else an action) */
    MN_VALUES = 0xAD9A,   /* u8[10]: the current choices */
    MN_DEFAULTS = 0xADA4, /* u8[10]: what they are reset to afterwards */
    MN_DAC_BASE = 0xADAE, /* u8[10]: VGA: DAC register of each option's first choice */
    MN_NORMAL = 0xADD1,   /* u8: text colour */
    MN_SELECTED = 0xADD2,
    MN_HOTKEY = 0xADD3,
    MN_PIECES = 0xAB7E,   /* the choice split: before the hotkey, the hotkey, after */
};

static int resource(Game *g, const MainMenuServices *host, uint16_t op, uint16_t a, uint16_t b)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, b, r->user) ? -1 : 0;
}

/* orig 0000:9C86 / 9C95   a DAC register dim (7, 1Ch, 1Eh) or lit (0, 1Ch, 3Fh) */
static int dac(Game *g, const MainMenuServices *host, uint8_t reg, int lit)
{
    return resource(g, host, MN_DAC_REGISTER, reg, lit ? 0x1C3F : 0x1C1E);
}

/* orig 0000:99E8   light the chosen value of the first six options */
static int light_choices(Game *g, const MainMenuServices *host)
{
    uint8_t *ds = g->ds;
    for (uint16_t i = 0; i < 6; ++i)
        if (dac(g, host, (uint8_t)(DS_U8(ds, (uint16_t)(MN_DAC_BASE + i)) + DS_U8(ds, (uint16_t)(MN_VALUES + i))), 1)
            < 0)
            return -1;
    return 0;
}

/* orig 0000:9CBE   one choice at (x, y), its hotkey letter in the hotkey colour; returns
 * the x after it. A choice is: n, n letters, the hotkey letter, the rest, NUL. */
static uint16_t draw_choice(Game *g, uint16_t x, uint16_t y, uint16_t at)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0xABA6) = 0;
    uint16_t to = MN_PIECES;
    uint8_t n = DS_U8(ds, at++);
    if (n) {
        DS_U16(ds, 0xABA6) = to;
        for (; n; --n)
            DS_U8(ds, to++) = DS_U8(ds, at++);
        DS_U8(ds, to++) = 0;
    }
    DS_U16(ds, 0xABA8) = to;
    DS_U8(ds, to++) = DS_U8(ds, at++);
    DS_U8(ds, to++) = 0; /* the AL of the last STOSB: 0 */
    DS_U16(ds, 0xABAA) = to;
    uint8_t ch;
    do
        DS_U8(ds, to++) = ch = DS_U8(ds, at++);
    while (ch);
    if (DS_U16(ds, 0xABA6)) {
        DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, MN_NORMAL);
        x = font_text(g, x, y, DS_U16(ds, 0xABA6));
    }
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, MN_HOTKEY);
    x = font_text(g, x, y, DS_U16(ds, 0xABA8));
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, MN_NORMAL);
    return font_text(g, x, y, DS_U16(ds, 0xABAA));
}

/* orig 0000:9CA4   the choice `index` of the record at `at`: its text and line */
static uint16_t choice_at(const uint8_t *ds, uint16_t at, uint8_t index, uint16_t *y)
{
    at = (uint16_t)(at + 6);
    for (; index; --index) {
        at++;
        for (unsigned n = 0x28; n && DS_U8(ds, at++);) /* REPNE SCASB, CX = 28h */
            --n;
        *y = (uint16_t)(*y + 0x0C);
    }
    return at;
}

/* orig 0000:9A33   EGA: every option's choices, the chosen one in the selected colour */
static void draw_options(Game *g)
{
    uint8_t *ds = g->ds;
    font_scale(g, 0x0C0C, 0x0C0C, 0x46, DS_U16(ds, 0xADE6), DS_U16(ds, 0xADFE));
    for (uint16_t option = 0; option < 10; ++option) {
        DS_U8(ds, 0xABAD) = DS_U8(ds, (uint16_t)(MN_VALUES + option));
        uint16_t at = DS_U16(ds, (uint16_t)(MN_RECORDS + option * 2));
        uint16_t count = DS_U16(ds, at), x = DS_U16(ds, (uint16_t)(at + 2)), y = DS_U16(ds, (uint16_t)(at + 4));
        DS_U8(ds, 0xABAC) = (uint8_t)count;
        at = (uint16_t)(at + 6);
        do { /* LOOP */
            if (DS_U8(ds, 0xABAC) == 1 || DS_U8(ds, 0xABAD)) {
                DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, MN_NORMAL);
                draw_choice(g, x, y, at);
            } else {
                DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, MN_SELECTED);
                font_text(g, x, y, (uint16_t)(at + 1));
            }
            at++;
            while (DS_U8(ds, at++))
                ;
            DS_U8(ds, 0xABAD)--;
            y = (uint16_t)(y + 0x0C);
        } while (--count);
    }
}

/* orig 0000:9B57   the ratings screen from the menu (DS:ABC8 set), the menu kept at 8000h */
static int ratings(Game *g, const MainMenuServices *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0xABC8) = 0xFF;
    screen_copy_rect(g, 0, 0x8000, 0x50, 0xC8);
    if (host->ratings ? ratings_screen(g, host->ratings) < 0 : resource(g, host, MN_RATINGS, 0, 0) < 0)
        return -1;
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        if (!host->screen || image_vga_load(g, host->images, 0xABBB, host->screen, host->palette) < 0
            || light_choices(g, host) < 0)
            return -1;
    } else
        screen_copy_rect(g, 0x8000, 0, 0x50, 0xC8);
    DS_U8(ds, 0xABC8) = 0;
    return 0;
}

enum { CONTINUE = 0, LEAVE = 1, REENTER = 2 };

/* the option handlers (table DS:AD7C); LEAVE where the original drops its return address
 * (ADD SP,2 / RET), REENTER where it jumps back into the key loop without returning */
static int handler(Game *g, const MainMenuServices *host, uint16_t option)
{
    uint8_t *ds = g->ds;
    uint8_t value = DS_U8(ds, (uint16_t)(MN_VALUES + option));
    switch (option) {
    case 0: /* 9AB1: the character */
        DS_U16(ds, 0x03F2) = value ? 0x96 : 0x12C;
        DS_U16(ds, DS_PLAYER) = value ? 0x04D4 : 0x0508;
        DS_U16(ds, DS_VEHICLE) = value ? 0x0508 : 0x04D4;
        return CONTINUE;
    case 1: /* 9ADE: a short game */
        DS_U8(ds, 0x1151) = value ? 0xFF : 0;
        return CONTINUE;
    case 2: /* 9AF1 */
        DS_U16(ds, DS_DIFFICULTY) = value;
        return CONTINUE;
    case 3: /* 9AFA */
        DS_U16(ds, DS_DETAIL) = value;
        return CONTINUE;
    case 4: /* 9B20: the joystick, if one is there; else the keyboard again ('K') */
        if (!value) {
            DS_U8(ds, DS_JOYSTICK) = 0;
            return CONTINUE;
        }
        {
            const MapResources *r = host->resources; /* 1: none found (the original's carry) */
            int status = r && r->call ? r->call(g, GM_JOYSTICK_DETECT, 0, 0, r->user) : -1;
            if (status < 0)
                return -1;
            if (status == 1)
                return REENTER;
            if (resource(g, host, GM_JOYSTICK_CALIBRATE, 0, 0) < 0)
                return -1;
            DS_U8(ds, DS_JOYSTICK) = 1;
            return CONTINUE;
        }
    case 5: /* 9B03 */
        DS_U8(ds, DS_PRACTICE_MODE) = DS_U8(ds, 0xAA96) = value ? 0xFF : 0;
        return CONTINUE;
    case 6: { /* 9B40: load a game; leave the menu if one was loaded */
        DS_U8(ds, 0x1143) = 0;
        int loaded = host->saves ? savegame_load(g, host->saves) : resource(g, host, MN_LOAD_GAME, 0, 0);
        if (loaded < 0)
            return -1;
        if (loaded == 2) /* 4CE5 dropped 9B40's return: back in the key loop as from 9B40 */
            return CONTINUE;
        return DS_U8(ds, 0x1143) ? LEAVE : CONTINUE;
    }
    case 7: /* 9B53: start */
        return LEAVE;
    case 8: /* 9B57 */
        return ratings(g, host) < 0 ? -1 : CONTINUE;
    case 9: /* 9B9D: quit */
        DS_U8(ds, DS_MISSION_OVER) = 0x55;
        return LEAVE;
    }
    return -1;
}

/* orig 0000:9BCD   read keys until an option leaves the menu. `depth` counts the return
 * addresses the joystick handler left on the stack: each LEAVE only unwinds one. */
static int key_loop(Game *g, const MainMenuServices *host)
{
    uint8_t *ds = g->ds;
    unsigned depth = 0;
    int reentered = 0;
    uint8_t key = 0;
    for (;;) {
        if (!reentered) {
            uint32_t read = keyboard_read(g, host->keys);
            if (read == UINT32_MAX)
                return -1;
            key = (uint8_t)(read & 0xDF);
            if (key == 'V') {
                int shown = DS_U8(ds, DS_FACILITY_SCREEN)
                                ? textbox_vga_draw(g, host->screen, 0x07F5, 5, 5, 0x1E, 5, host->text)
                                : textbox_draw(g, 0x07F5, 5, 5, 0x1E, 5, host->text);
                if (shown < 0)
                    return -1;
                continue;
            }
        }
        reentered = 0;
        uint16_t entry = MN_KEYS;
        unsigned n = 0x12;
        for (; n && DS_U8(ds, entry) != key; --n)
            entry = (uint16_t)(entry + 3);
        if (!n)
            continue;
        uint8_t option = DS_U8(ds, (uint16_t)(entry + 1)), value = DS_U8(ds, (uint16_t)(entry + 2));
        if (DS_U8(ds, (uint16_t)(MN_RADIO + option))) {
            uint8_t old = DS_U8(ds, (uint16_t)(MN_VALUES + option));
            if (old == value)
                continue;
            DS_U8(ds, (uint16_t)(MN_VALUES + option)) = value;
            uint16_t record = DS_U16(ds, (uint16_t)(MN_RECORDS + option * 2));
            uint8_t base = DS_U8(ds, (uint16_t)(MN_DAC_BASE + option));
            if (DS_U8(ds, DS_FACILITY_SCREEN)) {
                if (dac(g, host, (uint8_t)(old + base), 0) < 0 || dac(g, host, (uint8_t)(value + base), 1) < 0)
                    return -1;
            } else {
                uint16_t x = DS_U16(ds, (uint16_t)(record + 2)), y = DS_U16(ds, (uint16_t)(record + 4));
                uint16_t at = choice_at(ds, record, old, &y);
                draw_choice(g, x, y, at);
                y = DS_U16(ds, (uint16_t)(record + 4));
                at = choice_at(ds, record, value, &y);
                DS_U8(ds, DS_TEXT_COLOUR) = 0x0E;
                font_text(g, x, y, (uint16_t)(at + 1));
            }
        }
        int status = handler(g, host, option);
        if (status < 0)
            return -1;
        if (status == REENTER) {
            depth++;
            key = 'K';
            reentered = 1;
        } else if (status == LEAVE) {
            if (!depth)
                return 0;
            depth--;
        }
    }
}

/* orig 0000:9922 */
int main_menu(Game *g, const MainMenuServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || resource(g, host, MS_DEFAULT_PALETTE, 0, 0) < 0)
        return -1;
    uint8_t vga = DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    DS_U16(ds, DS_PLAYER) = 0x0508;
    DS_U16(ds, DS_VEHICLE) = 0x04D4;
    DS_U16(ds, 0x03F2) = 0x12C;
    if (resource(g, host, MS_SELECT_PAGES, 0, 0) < 0 || font_load(g, host->images, 0x7A49) < 0)
        return -1;
    font_scale(g, 0x0C0C, 0x0C0C, 0x46, DS_U16(ds, 0xADE6), DS_U16(ds, 0xADFE));
    DS_U16(ds, 0x805C) = 0x1F40;
    if (vga) {
        DS_U8(ds, MN_NORMAL) = 0xFD;
        DS_U8(ds, MN_SELECTED) = 0xFF;
        DS_U8(ds, MN_HOTKEY) = 0xFE;
        if (resource(g, host, MS_VIDEO_MODE, 0x13, 0) < 0)
            return -1;
        DS_U16(ds, 0x1228) = 0x140;
        if (!host->screen || image_vga_load(g, host->images, 0xABBB, host->screen, host->palette) < 0
            || light_choices(g, host) < 0)
            return -1;
        if (DS_U8(ds, 0xA9D9) && resource(g, host, MN_LINK, 0, 0) < 0) /* 151B:06DE, the serial link */
            return -1;
    } else {
        DS_U8(ds, MN_NORMAL) = 0x0F;
        DS_U8(ds, MN_SELECTED) = 0x0E;
        DS_U8(ds, MN_HOTKEY) = 0x0C;
        DS_U16(ds, 0x1228) = 0x50;
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x50;
        if (image_load_screen(g, host->images, 0xABAE) < 0)
            return -1;
        DS_U8(ds, DS_FILL_COLOUR) = 0x0F; /* 9A0E, then the frame lines 9A13 */
        for (uint16_t at = 0xABCC; at < 0xABCC + 32; at = (uint16_t)(at + 8)) {
            DS_U16(ds, DS_PEN_X) = DS_U16(ds, at);
            DS_U16(ds, DS_PEN_Y) = DS_U16(ds, (uint16_t)(at + 2));
            area_line_to(ds, g->planes, DS_U16(ds, (uint16_t)(at + 4)), DS_U16(ds, (uint16_t)(at + 6)));
        }
        draw_options(g);
        DS_U16(ds, 0x122A) = 0; /* 0B8F */
        if (resource(g, host, MS_VIDEO_PAGE, 0, 0) < 0 || resource(g, host, MS_PALETTE, 0, 0) < 0)
            return -1;
    }
    if (key_loop(g, host) < 0)
        return -1;
    for (uint16_t i = 0; i < 10; ++i) /* 9D29 */
        DS_U8(ds, (uint16_t)(MN_VALUES + i)) = DS_U8(ds, (uint16_t)(MN_DEFAULTS + i));
    if (resource(g, host, MS_VIDEO_MODE, 0x0D, 0) < 0)
        return -1;
    DS_U8(ds, DS_FACILITY_SCREEN) = 0;
    return 0;
}
