/* Saving, loading and deleting games (0000:4B7E, 4CE5, 4CDE, the picker 4CEA and its actions,
 * the "overwrite?" answers 4CD1 / 4B7E and the unreferenced 4B76, the save block coder 0A76),
 * through the DOS library (src/dos.c).
 *
 * A save file "NAME.CSM" in the current directory holds DS:0252 .. (DS:11FA bytes, coded
 * by 0A76), then 3Ch bytes from the far pointer DS:1208 and C4h bytes from the far pointer
 * at 1200h in that block's segment (the original's LDS reads it through the DS it just
 * set; the game was meant to use DS:1200); a file of any other size is not a save. The
 * picker lists up to 20 of them in a menu.
 *
 * These routines return through the stack in ways a C call cannot: they drop return
 * addresses (ADD SP,2 / 4) to close menus, restart the save with old return addresses still
 * pushed, and an action of the "overwrite?" menu restarts the save from inside that menu's
 * loop, which later returns into the loop again. So they run here as an interpreter over
 * their entry points with an explicit stack of the return addresses (labels), and a menu
 * action that does stack surgery leaves the C menu loop with a status that says where to go
 * on. A menu loop's own frame is a label: popping it runs the loop again.
 */
#include "term.h"

#define FLAG_CF 0x0001
#define FLAG_ZF 0x0040

enum {
    SG_LIST = 0x7795,      /* the search pattern, then the full path */
    SG_DTA = 0x77E5,
    SG_EXTENSION = 0x7790, /* ".CSM" */
    SG_MODE = 0x7810,      /* u8: the picker loads (1) or deletes (0) */
    SG_LOADED = 0x1143,    /* u8: a game was loaded */
    SG_BLOCK = 0x0252,
    SG_BLOCK_SIZE = 0x11FA,
};

/* return addresses */
enum {
    L_CALLER_CLOSE, /* below the menu loop that called the action: the menu closes */
    L_CALLER_RUN,   /* the calling menu loop: it goes on (the action returned) */
    L_SAVE,         /* 4B7E */
    L_AFTER_PICKER, /* 4C22: JMP 4B7E */
    L_AFTER_ASK,    /* 4CCC: after the "overwrite?" menu */
    L_ASK_RUN,      /* that menu's loop */
    L_AFTER_PICK,   /* 4DAF: after the picker's menu */
    L_PICK_RUN,     /* the picker menu's loop */
};

/* where to go */
enum {
    P_SAVE,   /* 4B7E */
    P_DROP_SAVE, /* 4B76: ADD SP,4, the overlay restored, then 4B7E (no menu points at it) */
    P_OPEN,   /* 4C6A, AX = the open flags */
    P_ERROR,  /* 4CAA */
    P_PICKER, /* 4CEA */
    P_PICKED, /* 4DEB, SI = the file's place + 1 */
    P_OVERWRITE, /* 4CD1 */
    P_AFTER_ASK, /* 4CCC */
    P_AFTER_PICK, /* 4DAF */
    P_RETURN, /* pop a label */
};

/* what a menu action of these menus returns to the menu loop, to leave it */
enum { SG_ESCAPE = 0x100 };

typedef struct Interp {
    Game *g;
    const SaveGameServices *host;
    CpuRegs r;
    uint8_t stack[64];
    int depth;
    int carry;
    int closed;
    int escape_target;
} Interp;

static void push(Interp *s, uint8_t label)
{
    if (s->depth < (int)sizeof s->stack)
        s->stack[s->depth++] = label;
}

static int pop(Interp *s)
{
    return s->depth ? s->stack[--s->depth] : -1;
}

static uint8_t *text_segment(Game *g)
{
    return far_ptr(g, DS_U16(g->ds, 0xEA36), 0);
}

static uint8_t *screen_of(const SaveGameServices *host)
{
    return host->menus && host->menus->ratings ? host->menus->ratings->screen : NULL;
}

static int restore(Interp *s)
{
    Game *g = s->g;
    if (!DS_U8(g->ds, DS_FACILITY_SCREEN))
        return scene_overlay_restore(g);
    uint8_t *screen = screen_of(s->host);
    if (!screen)
        return -1;
    scene_vga_overlay_restore(g, screen);
    return 0;
}

static int box(Interp *s, uint16_t text, uint16_t x, uint16_t y, uint16_t w, uint16_t h)
{
    Game *g = s->g;
    const TextPlatform *t = s->host->menus ? s->host->menus->text : NULL;
    if (DS_U8(g->ds, DS_FACILITY_SCREEN))
        return textbox_vga_draw(g, screen_of(s->host), text, x, y, w, h, t);
    return textbox_draw(g, text, x, y, w, h, t);
}

/* the menus these routines show: their actions leave the loop with SG_ESCAPE | target */
static int menu_call(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user)
{
    Interp *s = user;
    if (op == MM_ACTION && (a == 0x4CD1 || a == 0x4B7E || a == 0x4B76 || (a >= 0x4DD7 && a <= 0x4DEA))) {
        s->escape_target = a;
        return SG_ESCAPE;
    }
    const MenuPlatform *menu = s->host->menus ? s->host->menus->menu : NULL;
    return !menu || !menu->call ? -1 : menu->call(g, op, a, b, menu->user);
}

static int show_menu(Interp *s, uint16_t text, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t actions)
{
    MenuPlatform adapter = {menu_call, s};
    if (DS_U8(s->g->ds, DS_FACILITY_SCREEN)) {
        uint8_t *screen = screen_of(s->host);
        return screen ? menu_vga_display(s->g, screen, text, x, y, w, h, actions, &adapter) : -1;
    }
    return menu_display(s->g, text, x, y, w, h, actions, &adapter);
}

static int run_menu_again(Interp *s)
{
    MenuPlatform adapter = {menu_call, s};
    if (DS_U8(s->g->ds, DS_FACILITY_SCREEN)) {
        uint8_t *screen = screen_of(s->host);
        return screen ? menu_vga_run(s->g, screen, &adapter) : -1;
    }
    return menu_run(s->g, &adapter);
}

/* a menu came back: 0 (Esc: CLC) or a closing action's status, or an action of ours */
static int after_menu(Interp *s, int status, uint8_t loop_label, int *pc)
{
    if (status < 0)
        return -1;
    if (status == SG_ESCAPE) { /* the action runs with the loop's frame still pushed */
        push(s, loop_label);
        if (s->escape_target == 0x4CD1)
            *pc = P_OVERWRITE;
        else if (s->escape_target == 0x4B7E)
            *pc = P_SAVE;
        else if (s->escape_target == 0x4B76)
            *pc = P_DROP_SAVE;
        else {
            s->r.si = (uint16_t)(0x4DEB - s->escape_target);
            *pc = P_PICKED;
        }
        return 0;
    }
    s->carry = status == MENU_CLOSED_CARRY;
    *pc = P_RETURN;
    return 0;
}

static int ok(int status)
{
    return status < 0 ? -1 : 0;
}

/* orig 0000:0A76   AX = 0: code the save block (the player as 0 Reese / 1, the list pointers
 * made relative, each byte XOR AAh XOR the countdown); else decode it and set up again */
void savegame_code_block(Game *g, uint16_t ax)
{
    uint8_t *ds = g->ds;
    uint16_t count = DS_U16(ds, SG_BLOCK_SIZE);
    if (!ax) {
        uint16_t player = DS_U16(ds, DS_PLAYER);
        DS_U16(ds, DS_PLAYER) = player == 0x04D4 ? 0 : 1;
        DS_U16(ds, 0x03A2) = (uint16_t)(DS_U16(ds, 0x03A2) - 0x05B0);
        DS_U16(ds, 0x03A4) = (uint16_t)(DS_U16(ds, 0x03A4) - 0x0DF0);
        DS_U16(ds, 0x03A6) = (uint16_t)(DS_U16(ds, 0x03A6) - 0x0F70);
    }
    uint16_t at = SG_BLOCK;
    for (uint32_t n = count ? count : 0x10000; n; --n, at = (uint16_t)(at + 1)) /* LOOP: CX counts down */
        DS_U8(ds, at) = (uint8_t)(DS_U8(ds, at) ^ 0xAA ^ (uint8_t)n);
    if (ax) {
        DS_U16(ds, DS_PLAYER) = DS_U16(ds, DS_PLAYER) ? 0x0508 : 0x04D4;
        DS_U16(ds, 0x03A2) = (uint16_t)(DS_U16(ds, 0x03A2) + 0x05B0);
        DS_U16(ds, 0x03A4) = (uint16_t)(DS_U16(ds, 0x03A4) + 0x0DF0);
        DS_U16(ds, 0x03A6) = (uint16_t)(DS_U16(ds, 0x03A6) + 0x0F70);
        DS_U16(ds, 0x7276) = DS_U16(ds, 0x7278) = DS_U16(ds, 0x727A) = DS_U16(ds, 0x727C) = 0xFFFF;
        DS_U16(ds, 0x1204) = (uint16_t)(0x0E * (uint8_t)DS_U16(ds, DS_EXTRA_COUNT));
    }
}

/* "X:\dir\*.CSM" at DS:7795 (F6AC, then '*' and DS:7790 after the NUL) */
static int pattern(Interp *s)
{
    Game *g = s->g;
    uint8_t *ds = g->ds;
    s->r.si = SG_LIST;
    if (dos_current_directory(g, s->host->machine, &s->r) < 0)
        return -1;
    uint16_t at = SG_LIST;
    for (unsigned n = 0x50; n && DS_U8(ds, at++);) /* REPNE SCASB */
        --n;
    at--;
    DS_U8(ds, at++) = '*';
    uint16_t from = SG_EXTENSION;
    uint8_t ch;
    do
        DS_U8(ds, at++) = ch = DS_U8(ds, from++);
    while (ch);
    return 0;
}

static uint16_t save_size(const uint8_t *ds)
{
    return (uint16_t)(DS_U16(ds, SG_DTA + 0x1A) - 0x3C - 0xC4);
}

/* the three blocks read (F82B) or written (F84D); returns the first one's flags */
static int blocks(Interp *s, int (*io)(Game *, const MachineServices *, CpuRegs *), uint16_t *first_flags)
{
    Game *g = s->g;
    uint8_t *ds = g->ds;
    s->r.si = SG_BLOCK;
    s->r.cx = DS_U16(ds, SG_BLOCK_SIZE);
    if (io(g, s->host->machine, &s->r) < 0)
        return -1;
    *first_flags = s->r.flags;
    uint16_t ds_seg = s->r.ds;
    s->r.ds = DS_U16(ds, 0x120A);
    s->r.si = DS_U16(ds, 0x1208);
    s->r.cx = 0x3C;
    if (io(g, s->host->machine, &s->r) < 0)
        return -1;
    /* LDS SI,[1200] runs with DS still the second block's segment: the pointer comes from
     * there, not from the data segment (in the game 0000:0000, the interrupt vectors) */
    uint16_t seg = s->r.ds;
    s->r.si = (uint16_t)(*far_ptr(g, seg, 0x1200) | *far_ptr(g, seg, 0x1201) << 8);
    s->r.ds = (uint16_t)(*far_ptr(g, seg, 0x1202) | *far_ptr(g, seg, 0x1203) << 8);
    s->r.cx = 0xC4;
    if (io(g, s->host->machine, &s->r) < 0)
        return -1;
    s->r.ds = ds_seg;
    return 0;
}

static int interpret(Interp *s, int pc)
{
    Game *g = s->g;
    uint8_t *ds = g->ds;
    const MachineServices *mc = s->host->machine;
    for (;;) {
        switch (pc) {
        case P_RETURN: {
            int label = pop(s);
            switch (label) {
            case L_CALLER_RUN:
                return MENU_CONTINUE;
            case L_CALLER_CLOSE:
                s->closed = 1;
                return s->carry ? MENU_CLOSED_CARRY : MENU_CLOSED;
            case L_SAVE:
            case L_AFTER_PICKER:
                pc = P_SAVE;
                break;
            case L_AFTER_ASK:
                pc = P_AFTER_ASK;
                break;
            case L_AFTER_PICK:
                pc = P_AFTER_PICK;
                break;
            case L_ASK_RUN:
            case L_PICK_RUN: /* back into that menu's loop */
                if (after_menu(s, run_menu_again(s), (uint8_t)label, &pc) < 0)
                    return -1;
                break;
            default:
                return -1;
            }
            break;
        }

        case P_SAVE: { /* 4B7E */
            uint16_t player = DS_U16(ds, DS_PLAYER);
            if (!(DS_U8(ds, (uint16_t)(player + 0x0E)) & 1)) {
                if (box(s, 0x05C9, 0x0B, 0x0A, 0x15, 7) < 0)
                    return -1;
                s->carry = 0;
                pc = P_RETURN;
                break;
            }
            uint16_t found = 0;
            if (pattern(s) < 0)
                return -1;
            uint16_t at = 2, from = 0x10DF; /* the title copied within DS (here LODSB reads DS) */
            uint8_t ch;
            do
                DS_U8(ds, at++) = ch = DS_U8(ds, from++);
            while (ch);
            s->r.bx = at;
            s->r.dx = (uint16_t)((s->r.dx & 0xFF00) | 3);
            s->r.si = SG_LIST;
            s->r.di = SG_DTA;
            s->r.ax = 0;
            if (dos_find_first(g, mc, &s->r) < 0)
                return -1;
            if (s->r.flags & FLAG_ZF) {
                if (save_size(ds) == DS_U16(ds, SG_BLOCK_SIZE))
                    found++;
                for (;;) {
                    if (dos_find_next(g, mc, &s->r) < 0)
                        return -1;
                    if (!(s->r.flags & FLAG_ZF))
                        break;
                    if (save_size(ds) == DS_U16(ds, SG_BLOCK_SIZE))
                        found++;
                }
                if ((int16_t)found >= 0x14) { /* 4C04: full: delete one first */
                    if (ok(restore(s)) < 0 || box(s, 0x1106, 6, 4, 0x12, 4) < 0)
                        return -1;
                    push(s, L_SAVE);
                    push(s, L_AFTER_PICKER);
                    DS_U8(ds, SG_MODE) = 0;
                    pc = P_PICKER;
                    break;
                }
            }
            /* 4C25 */
            if (ok(restore(s)) < 0)
                return -1;
            const RatingsServices *editor = s->host->menus ? s->host->menus->ratings : NULL;
            if (!editor)
                return -1;
            int typed = name_editor(g, 0x10EC, 6, 0x0A, 8, editor);
            if (typed < 0)
                return -1;
            if (typed == 1) {
                s->carry = 1;
                pc = P_RETURN;
                break;
            }
            /* REPNE SCASB for AL as the editor leaves it (0C6B with AX = 2): 2 on the VGA
             * screen, else the low byte of the draw page; there a short name gets no ".CSM" */
            uint8_t al = DS_U8(ds, DS_FACILITY_SCREEN) ? 2 : (uint8_t)DS_U16(ds, DS_DRAW_PAGE);
            uint16_t name = 0xE3FA; /* the name editor's buffer (SI) */
            at = name;
            for (unsigned n = 9; n && DS_U8(ds, at++) != al;)
                --n;
            at--;
            from = SG_EXTENSION;
            do
                DS_U8(ds, at++) = ch = DS_U8(ds, from++);
            while (ch);
            s->r.si = SG_LIST;
            if (dos_current_directory(g, mc, &s->r) < 0)
                return -1;
            at = SG_LIST;
            for (unsigned n = 0x50; n && DS_U8(ds, at++);)
                --n;
            at--;
            from = name;
            do
                DS_U8(ds, at++) = ch = DS_U8(ds, from++);
            while (ch);
            s->r.bx = name;
            s->r.ax = 0x0501;
            pc = P_OPEN;
            break;
        }

        case P_DROP_SAVE: /* 4B76 */
            pop(s);
            pop(s);
            if (ok(restore(s)) < 0)
                return -1;
            pc = P_SAVE;
            break;

        case P_OVERWRITE: /* 4CD1: ADD SP,4 - the menu's loop and its caller's return */
            pop(s);
            pop(s);
            if (ok(restore(s)) < 0)
                return -1;
            s->r.ax = 0x0301;
            pc = P_OPEN;
            break;

        case P_OPEN: { /* 4C6A */
            s->r.si = SG_LIST;
            if (dos_open(g, mc, &s->r) < 0)
                return -1;
            if (s->r.flags & FLAG_CF) {
                pc = P_ERROR;
                break;
            }
            savegame_code_block(g, 0);
            uint16_t first;
            if (blocks(s, dos_write, &first) < 0)
                return -1;
            savegame_code_block(g, 0xFFFF);
            if (!(first & FLAG_ZF)) {
                pc = P_ERROR;
                break;
            }
            if (dos_close(g, mc, &s->r) < 0)
                return -1;
            pop(s); /* ADD SP,2 */
            s->carry = 0;
            pc = P_RETURN;
            break;
        }

        case P_ERROR: /* 4CAA */
            if (dos_last_error(g) == 0x50) {
                push(s, L_AFTER_ASK);
                if (after_menu(s, show_menu(s, 0x114E, 5, 3, 0x1A, 9, 0x778C), L_ASK_RUN, &pc) < 0)
                    return -1;
                break;
            }
            pop(s); /* ADD SP,2 */
            s->carry = 0;
            pc = P_RETURN;
            break;

        case P_AFTER_ASK: /* 4CCC */
            pop(s);
            s->carry = 0;
            pc = P_RETURN;
            break;

        case P_PICKER: { /* 4CEA */
            uint16_t count = 5;
            if (pattern(s) < 0)
                return -1;
            uint8_t *text = text_segment(g);
            uint16_t at = 2, from = 0x10DF;
            uint8_t ch;
            do
                text[at++] = ch = text[from++];
            while (ch);
            uint16_t entry = at;
            uint8_t number = 3;
            s->r.si = SG_LIST;
            s->r.di = SG_DTA;
            s->r.ax = 0;
            if (dos_find_first(g, mc, &s->r) < 0)
                return -1;
            int more = (s->r.flags & FLAG_ZF) != 0, error = 0;
            while (more) {
                if (save_size(ds) == DS_U16(ds, SG_BLOCK_SIZE)) {
                    count++;
                    at = entry;
                    text[at++] = 4;
                    text[at++] = number++;
                    from = (uint16_t)(SG_DTA + 0x1E);
                    do
                        text[at++] = ch = DS_U8(ds, from++);
                    while (ch);
                    at = (uint16_t)(at - 5);
                    text[at++] = 0; /* ".CSM" cut */
                    entry = at;
                    if ((int16_t)count >= 0x19)
                        break;
                }
                if (dos_find_next(g, mc, &s->r) < 0)
                    return -1;
                if (s->r.flags & FLAG_CF) {
                    error = 1;
                    break;
                }
                more = (s->r.flags & FLAG_ZF) != 0;
            }
            if (error) { /* JMP 4CAA */
                pc = P_ERROR;
                break;
            }
            text[entry] = 0xFF;
            if (count == 5) { /* 4DC2 */
                if (box(s, 0x112A, 6, 4, 0x13, 4) < 0)
                    return -1;
                s->carry = 1;
                pc = P_RETURN;
                break;
            }
            text[entry] = 0xFF;
            if (!DS_U8(ds, SG_MODE) && ok(restore(s)) < 0)
                return -1;
            push(s, L_AFTER_PICK);
            if (after_menu(s, show_menu(s, 2, 0x0C, (uint16_t)(0x0C - (count >> 1)), 0x10, count, 0x78B2), L_PICK_RUN,
                           &pc) < 0)
                return -1;
            break;
        }

        case P_AFTER_PICK: /* 4DAF */
            if (s->carry || DS_U8(ds, SG_MODE)) {
                pc = P_RETURN;
                break;
            }
            if (ok(restore(s)) < 0)
                return -1;
            pop(s); /* ADD SP,2 */
            s->carry = 0;
            pc = P_RETURN;
            break;

        case P_PICKED: { /* 4DEB: the SI-th string from text:0002 is the file */
            uint8_t *text = text_segment(g);
            uint16_t at = 2;
            for (uint16_t n = s->r.si; n; --n) /* LOOP of REPNE SCASB, 50h each */
                for (unsigned k = 0x50; k && text[at++];)
                    --k;
            at = (uint16_t)(at + 2);
            uint16_t to = SG_LIST;
            for (unsigned k = 0x50; k && DS_U8(ds, to++);)
                --k;
            to = (uint16_t)(to - 6);
            uint8_t ch;
            while ((ch = text[at++]) != 0)
                DS_U8(ds, to++) = ch;
            uint16_t from = SG_EXTENSION;
            do
                DS_U8(ds, to++) = ch = DS_U8(ds, from++);
            while (ch);
            if (!DS_U8(ds, SG_MODE)) { /* delete */
                s->r.si = SG_LIST;
                if (dos_delete(g, mc, &s->r) < 0)
                    return -1;
                pop(s);
                s->carry = 0;
                pc = P_RETURN;
                break;
            }
            s->r.ax = 0;
            s->r.si = SG_LIST;
            if (dos_open_mode(g, mc, &s->r) < 0)
                return -1;
            if (s->r.flags & FLAG_CF) {
                pc = P_ERROR;
                break;
            }
            uint16_t first;
            if (blocks(s, dos_read, &first) < 0)
                return -1;
            savegame_code_block(g, 0xFFFF);
            if (first & FLAG_CF) {
                pc = P_ERROR;
                break;
            }
            if (dos_close(g, mc, &s->r) < 0)
                return -1;
            DS_U8(ds, SG_LOADED) = 0xFF;
            if (ok(restore(s)) < 0)
                return -1;
            pop(s);
            s->carry = 1;
            pc = P_RETURN;
            break;
        }

        default:
            return -1;
        }
    }
}

static Interp start(Game *g, const SaveGameServices *host)
{
    Interp s = {0};
    s.g = g;
    s.host = host;
    s.r.ds = s.r.es = g->ds_seg;
    s.r.flags = 2;
    return s;
}

/* orig 0000:4B7E as a menu action: MENU_CONTINUE, MENU_CLOSED or MENU_CLOSED_CARRY */
int savegame_save_action(Game *g, const SaveGameServices *host)
{
    if (!host || !host->machine)
        return -1;
    Interp s = start(g, host);
    push(&s, L_CALLER_CLOSE);
    push(&s, L_CALLER_RUN);
    return interpret(&s, P_SAVE);
}

/* orig 0000:4CDE as a menu action */
int savegame_delete_action(Game *g, const SaveGameServices *host)
{
    if (!host || !host->machine)
        return -1;
    Interp s = start(g, host);
    DS_U8(g->ds, SG_MODE) = 0;
    push(&s, L_CALLER_CLOSE);
    push(&s, L_CALLER_RUN);
    return interpret(&s, P_PICKER);
}

/* orig 0000:4CE5 as a call (the main menu's load): 0, or 1 with the carry; 2 when an error
 * path dropped the caller's return address (ADD SP,2) so that the call returns one level up */
int savegame_load(Game *g, const SaveGameServices *host)
{
    if (!host || !host->machine)
        return -1;
    Interp s = start(g, host);
    DS_U8(g->ds, SG_MODE) = 1;
    push(&s, L_CALLER_CLOSE);
    push(&s, L_CALLER_RUN);
    int status = interpret(&s, P_PICKER);
    return status < 0 ? -1 : s.closed ? 2 : s.carry;
}
