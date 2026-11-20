/* The program's start-up (0000:0000) and its set-up routines (04D3, 04E8, 052C, the EMS
 * preload 09FB / 0A2C, the starting kit 97D8 / 86F4, a game's start 59A6 / 5A58 / 5A0D, the
 * ratings after a game D5B1 / D5FA), and the command-line options (0413) with the argument
 * scanner of the run-time library (F8FC, F97A, FA19, FA2C, F8E0). Routines with services of
 * their own (screens, images, sound, the serial link) are the host's, called by their
 * original address (ProgramServices.call); the memory and machine ones are called here.
 *
 * The scanner reads the command tail at far DS:EA68 (EA6A = FFFFh: the PSP, DS:EA6E), with
 * three sets of characters in the data segment, each a count and a pointer: switches
 * (DS:EA54 / EA56, "/"), separators (EA5C / EA5E, ",;+") and blanks (EA63 / EA65, space
 * and tab). An argument starts with a switch, after a separator or after blanks; a switch
 * inside an argument starts the next one. The counts are constants; a set of none would
 * leave the flag of the instruction before its scan, which the C keeps too.
 */
#include "term.h"

#include <string.h>

#define FLAG_CF 0x0001
#define FLAG_PF 0x0004
#define FLAG_AF 0x0010
#define FLAG_ZF 0x0040
#define FLAG_SF 0x0080
#define FLAG_OF 0x0800

enum {
    ARG_SWITCHES = 0xEA54,  /* u16 count, u16 pointer */
    ARG_SEPARATORS = 0xEA5C,
    ARG_BLANKS = 0xEA63,
    ARG_START = 0xEA68,     /* far pointer: the command tail */
    ARG_NEXT = 0xEA6C,      /* where the next argument is read */
    ARG_PSP = 0xEA6E,
    OPT_LINK_PORT = 0x01E1, /* u8: a COM port was given */
    OPT_SOUND = 0xA773,     /* u16: 1 PC speaker, 2 AdLib, 4 Sound Blaster */
    OPT_COM = 0xA9EA,
    OPT_VGA = 0xADD0,
    OPT_LINK = 0x01DE,
};

static uint8_t rd(Game *g, uint16_t seg, uint16_t off)
{
    return *far_ptr(g, seg, off);
}

static uint16_t rw(Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(rd(g, seg, off) | rd(g, seg, (uint16_t)(off + 1)) << 8);
}

/* REPNE SCASB for al over the set at ES:set (count, pointer): ZF when found; with a count
 * of 0 the flag stays as it was */
static int in_set(Game *g, uint16_t es, uint16_t set, uint8_t al, int zf)
{
    uint16_t cx = rw(g, es, set), di = rw(g, es, (uint16_t)(set + 2));
    while (cx) {
        --cx;
        zf = rd(g, es, di) == al;
        di = (uint16_t)(di + 1);
        if (zf)
            break;
    }
    return zf;
}

/* the flags of CMP a,b (8 bits) */
static uint16_t cmp8(uint16_t flags, uint8_t a, uint8_t b)
{
    uint8_t res = (uint8_t)(a - b);
    unsigned ones = 0;
    for (uint8_t v = res; v; v &= (uint8_t)(v - 1))
        ones++;
    flags &= (uint16_t)~(FLAG_CF | FLAG_PF | FLAG_AF | FLAG_ZF | FLAG_SF | FLAG_OF);
    if (a < b)
        flags |= FLAG_CF;
    if (!(ones & 1))
        flags |= FLAG_PF;
    if ((a ^ b ^ res) & 0x10)
        flags |= FLAG_AF;
    if (!res)
        flags |= FLAG_ZF;
    if (res & 0x80)
        flags |= FLAG_SF;
    if ((a ^ b) & (a ^ res) & 0x80)
        flags |= FLAG_OF;
    return flags;
}

/* orig 0000:F8E0   AL and AH made upper case (a..z AND 5Fh), then CMP AL,AH */
void char_compare_nocase(CpuRegs *r)
{
    uint8_t al = (uint8_t)r->ax, ah = (uint8_t)(r->ax >> 8);
    if (al >= 'a' && al <= 'z')
        al &= 0x5F;
    if (ah >= 'a' && ah <= 'z')
        ah &= 0x5F;
    r->ax = (uint16_t)(ah << 8 | al);
    r->flags = cmp8(r->flags, al, ah);
}

/* orig 0000:FA2C   DS:SI against ES:DI, letters in either case: ZF when they are the same
 * string (the flags of the last compare); registers kept */
void string_compare_nocase(Game *g, CpuRegs *r)
{
    uint16_t si = r->si, di = r->di;
    for (;;) {
        uint8_t al = rd(g, r->ds, si++);
        if (!al) {
            r->flags = cmp8(r->flags, al, rd(g, r->es, di));
            return;
        }
        uint8_t b = rd(g, r->es, di);
        di = (uint16_t)(di + 1);
        r->flags = cmp8(r->flags, al, b); /* SCASB */
        if (r->flags & FLAG_ZF)
            continue;
        CpuRegs t = *r;
        t.ax = (uint16_t)(b << 8 | al);
        char_compare_nocase(&t);
        r->flags = t.flags;
        if (!(r->flags & FLAG_ZF))
            return;
    }
}

/* orig 0000:FA19   the scanner back at the PSP's command tail */
void args_reset(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0xEA6A) = 0xFFFF;
    DS_U16(ds, ARG_START) = 0x81;
    DS_U16(ds, ARG_NEXT) = 0x81;
}

static uint16_t tail_segment(Game *g, uint16_t es)
{
    uint16_t seg = rw(g, es, (uint16_t)(ARG_START + 2));
    return seg == 0xFFFF ? rw(g, es, ARG_PSP) : seg;
}

/* orig 0000:F8FC   CX = the number of arguments from the start of the tail (each separator
 * starts one, empty or not); other registers kept */
void args_count(Game *g, CpuRegs *r)
{
    uint16_t es = r->ds, ds = tail_segment(g, es), si = rw(g, es, ARG_START);
    uint16_t bx = 0xFFFF;
    uint8_t ah, dh;
    int zf;
next:
    bx++;
    ah = dh = 0;
    zf = 1; /* XOR DX,DX */
    for (;;) {
        uint8_t al = rd(g, ds, si);
        si = (uint16_t)(si + 1);
        zf = in_set(g, es, ARG_SWITCHES, al, zf);
        if (zf) {
            if (ah) {
                si--;
                goto next;
            }
            ah++;
            zf = !ah;
            continue;
        }
        zf = in_set(g, es, ARG_SEPARATORS, al, zf);
        if (zf)
            goto next;
        zf = in_set(g, es, ARG_BLANKS, al, zf);
        if (zf) {
            zf = !ah;
            if (ah)
                dh = al;
            continue;
        }
        if (al == 0x0D || al == 0)
            break;
        if (dh) {
            si--;
            goto next;
        }
        ah++;
        zf = !ah;
    }
    if (ah)
        bx++;
    r->cx = bx;
}

/* orig 0000:F97A   the next argument into ES:SI (the data segment) with a NUL: CF when there
 * is none (DS:EA6C kept); AL = the last character looked at, other registers kept */
void args_next(Game *g, CpuRegs *r)
{
    uint16_t es = r->ds, ds = tail_segment(g, es);
    uint16_t si = rw(g, es, ARG_NEXT), bp = r->si;
    uint8_t al = 0, ah = 0, dh = 0;
    int zf = rw(g, es, (uint16_t)(ARG_START + 2)) == 0xFFFF; /* CMP ES:[EA6A],-1 */
    int cf = 0;
    for (;;) {
        al = rd(g, ds, si);
        si = (uint16_t)(si + 1);
        int store = 0;
        zf = in_set(g, es, ARG_SWITCHES, al, zf);
        if (zf) {
            if (ah) {
                si--;
                break;
            }
            store = 1;
        } else {
            zf = in_set(g, es, ARG_SEPARATORS, al, zf);
            if (zf)
                break;
            zf = in_set(g, es, ARG_BLANKS, al, zf);
            if (zf) {
                zf = !ah;
                if (ah)
                    dh = al;
                continue;
            }
            if (al == 0x0D || al == 0) { /* F9F5 */
                si--;
                if (!ah) {
                    cf = 1;
                    goto done;
                }
                break;
            }
            if (dh) {
                si--;
                al = dh;
                break;
            }
            store = 1;
        }
        if (store) { /* F9ED */
            *far_ptr(g, es, bp) = al;
            bp = (uint16_t)(bp + 1);
            ah++;
            zf = !ah;
        }
    }
    /* F9FB */
    *far_ptr(g, es, ARG_NEXT) = (uint8_t)si;
    *far_ptr(g, es, (uint16_t)(ARG_NEXT + 1)) = (uint8_t)(si >> 8);
    *far_ptr(g, es, bp) = 0; /* DL */
done:
    r->ax = (uint16_t)((r->ax & 0xFF00) | al);
    r->flags = (uint16_t)((r->flags & ~FLAG_CF) | cf);
}

static int print(Game *g, const ProgramServices *host, uint16_t text)
{
    CpuRegs r = {0};
    r.ds = r.es = g->ds_seg;
    r.si = text;
    r.flags = 2;
    return dos_print(g, host->machine, &r);
}

/* orig 0000:0413   the command-line options: none / ibmsound / adlib / sblaster, ega / vga,
 * link with com1..com4 (the link's set-up 151B:020F is the host's). 1 when the program ends
 * here (a bad argument, or link without a port: the message printed, ADD SP,2 / RETF) */
int startup_options(Game *g, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || !host->machine)
        return -1;
    DS_U8(ds, OPT_LINK_PORT) = 0;
    DS_U16(ds, OPT_SOUND) = 1;
    args_reset(g);
    CpuRegs r = {0};
    r.ds = r.es = g->ds_seg;
    r.flags = 2;
    args_count(g, &r);
    if (r.cx < 1)
        return 0;
    for (uint16_t left = r.cx; left; --left) { /* LOOP */
        r.si = 0xE3FA;
        args_next(g, &r);
        uint16_t di = 0x00C8, bp = 0;
        int found = 0;
        for (uint16_t n = 0x0B; n; --n) {
            r.si = 0xE3FA;
            r.di = di;
            string_compare_nocase(g, &r);
            if (r.flags & FLAG_ZF) {
                found = 1;
                break;
            }
            for (unsigned k = 0xFF; k && DS_U8(ds, di++);) /* REPNE SCASB */
                --k;
            bp++;
        }
        if (!found)
            return print(g, host, 0x0106) < 0 ? -1 : 1;
        if (bp == 4)
            DS_U8(ds, OPT_VGA) = 0;
        else if (bp == 5)
            DS_U8(ds, OPT_LINK) = 0xFF;
        else if (bp >= 6 && bp <= 9) {
            DS_U16(ds, OPT_COM) = (uint16_t)(bp - 6);
            DS_U8(ds, OPT_LINK_PORT) = 0xFF;
            if (!host->call || host->call(g, 0x151B, 0x020F, &r, host->user))
                return -1;
        } else if (bp == 0x0A)
            DS_U8(ds, OPT_VGA) = 0xFF;
        else {
            if (bp == 3)
                bp++;
            DS_U16(ds, OPT_SOUND) = bp;
            if (!bp) {
                DS_U16(ds, OPT_SOUND)++;
                DS_U8(ds, 0x0361) = 0;
            }
        }
    }
    if (DS_U8(ds, OPT_LINK) && !DS_U8(ds, OPT_LINK_PORT))
        return print(g, host, 0x01C3) < 0 ? -1 : 1;
    return 0;
}

/* ------------------------------------------------------------------------------------------
 * The set-up routines of start-up and of each game, and the start itself. */

static CpuRegs regs_of(Game *g)
{
    CpuRegs r = {0};
    r.ds = r.es = g->ds_seg;
    r.flags = 2;
    return r;
}

/* a routine the host owns, by its original address, with registers */
static int host_call(Game *g, const ProgramServices *host, uint16_t seg, uint16_t off, CpuRegs *r)
{
    CpuRegs t = regs_of(g);
    return !host->call || host->call(g, seg, off, r ? r : &t, host->user) ? -1 : 0;
}

static int host_ax(Game *g, const ProgramServices *host, uint16_t seg, uint16_t off, uint16_t ax)
{
    CpuRegs r = regs_of(g);
    r.ax = ax;
    return host_call(g, host, seg, off, &r);
}

static int video_mode(Game *g, const ProgramServices *host, uint16_t mode)
{
    CpuRegs r = regs_of(g);
    r.ax = mode;
    return bios_video_call(g, host->machine, &r);
}

/* orig 0000:5BCD   CX frames (both retrace waits each), fewer when a key is in the buffer */
static void wait_frames(Game *g, const ProgramServices *host, uint16_t cx)
{
    int zf;
    do { /* LOOPE */
        retrace_wait_start(g, host->machine);
        retrace_wait_end(g, host->machine);
        zf = !DS_U8(g->ds, 0x5BD4);
        cx--;
    } while (cx && zf);
}

/* orig 0000:0A2C   the file named at DS:DI read whole to [0208]:[020A] (open F80F, read
 * F82B with CX = FFFFh, close F770): AX = the bytes read; SI, DI kept */
static int preload_file(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint16_t si = r->si, di = r->di;
    r->si = di;
    r->ax &= 0xFF00;
    if (dos_open_mode(g, host->machine, r) < 0)
        return -1;
    r->si = DS_U16(g->ds, 0x020A);
    uint16_t ds = r->ds;
    r->ds = DS_U16(g->ds, 0x0208);
    r->cx = 0xFFFF;
    if (dos_read(g, host->machine, r) < 0)
        return -1;
    r->bp = r->cx;
    r->ds = ds;
    if (dos_close(g, host->machine, r) < 0)
        return -1;
    r->di = di;
    r->si = si;
    r->ax = r->bp;
    return 0;
}

/* orig 0000:09FB   with the EMS frame (DS:0208), the files named from DS:0000 (to an FFh)
 * one after another into it, their offsets at DS:009D */
int startup_preload(Game *g, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || !host->machine)
        return -1;
    if (!DS_U16(ds, 0x0208))
        return 0;
    CpuRegs r = regs_of(g);
    DS_U16(ds, 0x020A) = 0;
    r.di = 0;
    r.si = 0x009D;
    do {
        if (preload_file(g, host, &r) < 0)
            return -1;
        r.bx = DS_U16(ds, 0x020A);
        DS_U16(ds, r.si) = r.bx;
        r.si = (uint16_t)(r.si + 2);
        DS_U16(ds, 0x020A) = (uint16_t)(DS_U16(ds, 0x020A) + r.ax);
        r.ax &= 0xFF00;
        r.cx = 0xFF;
        while (r.cx) { /* REPNE SCASB (ES = DS) */
            r.cx--;
            if (!DS_U8(ds, r.di++))
                break;
        }
    } while (!(DS_U8(ds, r.di) & 0x80));
    return 0;
}

/* orig 0000:04D3   the random seed and table, the row table, the keyboard interrupt, the
 * intro's buffer, the pictures (1AC9, the host's: images) */
int startup_init(Game *g, const ProgramServices *host)
{
    if (!host || !host->machine)
        return -1;
    random_seed_from_clock(g);
    CpuRegs r = regs_of(g);
    r.ax = 0x2C00; /* 8117: the time of day from DOS */
    if (machine_interrupt(g, host->machine, 0x21, &r) < 0)
        return -1;
    random_refill_from(g->ds, r.dx, r.cx);
    session_row_table(g->ds);
    if (keyboard_install(g, host->machine) < 0)
        return -1;
    intro_set_buffer(g->ds);
    return host_call(g, host, 0, 0x1AC9, NULL);
}

/* orig 0000:04E8   the intro: mode 0Eh, the music (8986), the title (57C5:000E), two movies
 * (B210: DS:00C3 and DS:00BD, width 50h, variants 7 and 8) between pauses, the pages
 * cleared and selected (0C6B, AX = 200h) */
int startup_intro(Game *g, const ProgramServices *host)
{
    if (!host || !host->machine)
        return -1;
    if (video_mode(g, host, 0x0E) < 0 || host_call(g, host, 0, 0x8986, NULL) < 0
        || host_call(g, host, 0x57C5, 0x000E, NULL) < 0)
        return -1;
    static const uint16_t movies[2][2] = {{0x00C3, 7}, {0x00BD, 8}};
    for (int i = 0; i < 2; ++i) {
        wait_frames(g, host, 0x3C);
        CpuRegs r = regs_of(g);
        r.si = movies[i][0];
        r.ax = 0x50;
        r.bx = movies[i][1];
        if (host_call(g, host, 0, 0xB210, &r) < 0)
            return -1;
    }
    wait_frames(g, host, 0x258);
    camera_clear_pages(g);
    return host_ax(g, host, 0, 0x0C6B, 0x0200);
}

/* orig 0000:052C   a game's set-up: the arrival follow-up, mode 0Dh and the palette, the
 * screen width, then the resources and tables (the host's ones by address), the divide
 * handler */
int startup_game_setup(Game *g, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || !host->machine)
        return -1;
    session_arrival_followup(ds);
    if (video_mode(g, host, 0x0D) < 0)
        return -1;
    palette_registers(g, host->machine, 0x1521);
    DS_U8(ds, 0x01DD) = 0xFF;
    DS_U16(ds, 0x9A72) = 0x28;
    DS_U16(ds, 0x1228) = 0x28;
    if (host_ax(g, host, 0, 0x0C6B, 2) < 0 || host_call(g, host, 0, 0x6149, NULL) < 0
        || host_call(g, host, 0, 0x16A9, NULL) < 0)
        return -1;
    hud_choose_panel(ds);
    if (host_call(g, host, 0, 0x8ABE, NULL) < 0 || host_call(g, host, 0, 0x70DF, NULL) < 0)
        return -1;
    build_dither_table(ds);
    if (host_call(g, host, 0, 0xE475, NULL) < 0 || host_call(g, host, 0, 0x6B23, NULL) < 0)
        return -1;
    shop_randomize_balances(ds);
    static const uint16_t loads[] = {0x4F4B, 0xCA1A, 0xB187, 0xB199};
    for (unsigned i = 0; i < sizeof loads / sizeof loads[0]; ++i)
        if (host_call(g, host, 0, loads[i], NULL) < 0)
            return -1;
    divide_handler_install(g);
    return 0;
}

/* orig 0000:86F4   room for the item SI: its weight (byte +1) within the capacity DS:03F2
 * and at most 13h in its category's count (the DS:9A4E table): then the weight taken, 0;
 * else the overlay restored, "too heavy" (the message box 5032), 1: the original's
 * ADD SP,4 / RET then returns to 0000:BX of its caller (97D8: into the program's start) */
static int item_room(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t si = r->si;
    uint16_t ax = (uint16_t)((int16_t)(int8_t)DS_U8(ds, (uint16_t)(si + 1)) + DS_U16(ds, 0x116C));
    r->ax = ax;
    if (ax < DS_U16(ds, 0x03F2)) {
        uint16_t bx = (uint8_t)(DS_U8(ds, (uint16_t)(si + 2)) - 1);
        if (bx > 4)
            bx = 5;
        bx = (uint16_t)(bx + bx);
        r->bx = bx;
        r->di = DS_U16(ds, (uint16_t)(0x9A4E + bx));
        if (DS_U8(ds, r->di) <= 0x13) {
            DS_U16(ds, 0x116C) = ax;
            r->flags &= (uint16_t)~FLAG_CF;
            return 0;
        }
    }
    if (scene_overlay_restore(g) < 0)
        return -1;
    CpuRegs t = regs_of(g);
    t.si = 0x0E49;
    t.ax = 0x0F;
    t.bx = 4;
    t.cx = 0x16;
    t.dx = 0x0A;
    return host_call(g, host, 0, 0x5032, &t) < 0 ? -1 : 1;
}

/* orig 0000:97D8   the starting kit (DS:1151 set) by difficulty (tables DS:AB3C / AB48 /
 * AB52, ids at AB5E / AB6A / AB74): each item through 86F4 and shop_add_item (855A, the
 * host's; carry: not added), its id at DS:05B0 + 6n; DS:11C0 = 12Ch. Without the kit 9845.
 * 2 when 86F4 found no room: the original then returns to 0000:BX (*bx_out), a crash no
 * table of the game reaches. */
int startup_inventory(Game *g, const ProgramServices *host, uint16_t *bx_out)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    if (!DS_U8(ds, 0x1151)) {
        session_clear_flags(ds);
        return 0;
    }
    uint16_t bx = 0, di = 0x05B0;
    uint16_t items = 0xAB52, ids = 0xAB74;
    if (DS_U16(ds, 0x03F0) != 2) {
        items = 0xAB48, ids = 0xAB6A;
        if (DS_U16(ds, 0x03F0) != 1)
            items = 0xAB3C, ids = 0xAB5E;
    }
    DS_U16(ds, 0xAB38) = items;
    DS_U16(ds, 0xAB3A) = ids;
    for (;; bx = (uint16_t)(bx + 2)) {
        uint16_t si = DS_U16(ds, (uint16_t)(DS_U16(ds, 0xAB38) + bx));
        if (!si)
            break;
        CpuRegs r = regs_of(g);
        r.si = si;
        r.bx = bx;
        r.di = di;
        int room = item_room(g, host, &r);
        if (room < 0)
            return -1;
        if (room) {
            if (bx_out)
                *bx_out = bx;
            return 2;
        }
        if (host_call(g, host, 0, 0x855A, &r) < 0)
            return -1;
        if (!(r.flags & FLAG_CF)) {
            DS_U16(ds, di) = DS_U16(ds, (uint16_t)(DS_U16(ds, 0xAB3A) + bx));
            di = (uint16_t)(di + 6);
        }
    }
    DS_U16(ds, 0x11C0) = 0x12C;
    return 0;
}

/* a new random heading (0..1FFh) and place in the city: x = C000h + r + r/2, z = 8000h + r */
static void random_place(uint8_t *ds, uint16_t si)
{
    DS_U16(ds, (uint16_t)(si + 6)) = random_word(ds) & 0x1FF;
    uint32_t x = 0xC000, z = 0x8000;
    uint16_t ax = random_word(ds);
    x += ax;
    x += (uint16_t)(ax >> 1);
    z += random_word(ds);
    DS_U16(ds, (uint16_t)(si + 0x22)) = (uint16_t)x;
    DS_U16(ds, (uint16_t)(si + 0x24)) = (uint16_t)(x >> 16);
    DS_U16(ds, (uint16_t)(si + 0x2A)) = (uint16_t)z;
    DS_U16(ds, (uint16_t)(si + 0x2C)) = (uint16_t)(z >> 16);
}

/* orig 0000:59A6 (5A58, 5A0D)   the start of a game: for a new one (DS:1143 clear) both
 * characters from their templates (DS:7AC8, 7AFC), the vehicle and the player placed at
 * random (DS:5A25 set, 116E = 0Ah); then the player's position normalised, the visible cells
 * (3B88) and the arrival cleared (D265), the host's */
int startup_position(Game *g, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    DS_U16(ds, 0x7242) = 0xFFFF;
    uint16_t si = DS_U16(ds, DS_PLAYER);
    if (!DS_U8(ds, 0x1143)) {
        memcpy(ds + 0x04D4, ds + 0x7AC8, 0x34);
        memcpy(ds + 0x0508, ds + 0x7AFC, 0x34);
        uint16_t vehicle = DS_U16(ds, DS_VEHICLE);
        random_place(ds, vehicle);
        DS_U8(ds, 0x5A25) = 0xFF;
        position_normalize(g, vehicle);
        random_place(ds, si);
        DS_U16(ds, 0x116E) = 0x0A;
    }
    position_normalize(g, si);
    return host_call(g, host, 0, 0x3B88, NULL) < 0 || host_call(g, host, 0, 0xD265, NULL) < 0 ? -1 : 0;
}

/* orig 0000:D5FA   the ratings table (DS:50B2, CFh bytes) coded and written to the player's
 * file (DS:E27E / E28A, created anew: F77C, F84D, F770); left coded */
static int ratings_save(Game *g, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    CpuRegs r = regs_of(g);
    r.si = DS_U16(ds, DS_PLAYER) == 0x04D4 ? 0xE27E : 0xE28A;
    r.ax = 0;
    if (dos_create(g, host->machine, &r) < 0)
        return -1;
    if (r.flags & FLAG_CF)
        return 0;
    ratings_encode(ds + 0x50B2);
    r.cx = 0xCF;
    r.si = 0x50B2;
    if (dos_write(g, host->machine, &r) < 0)
        return -1;
    return dos_close(g, host->machine, &r);
}

/* orig 0000:D5B1   after a game: the ratings read (D628), the score and its place
 * (ratings_insert); a place (DS:11A8 not negative) gets the name (DF3A, unless DS:038A) and
 * the table is saved */
int ratings_commit(Game *g, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || !host->machine)
        return -1;
    DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    if (host_call(g, host, 0, 0xD628, NULL) < 0)
        return -1;
    score_update(ds);
    ratings_insert(ds);
    if (!(DS_U16(ds, 0x11A8) & 0x8000)) {
        if (!DS_U8(ds, 0x038A)) {
            if (host_call(g, host, 0, 0xDF3A, NULL) < 0)
                return -1;
            uint16_t ax = (uint16_t)((uint16_t)(5 - DS_U16(ds, 0x11A8)) * 0x29);
            uint16_t di = (uint16_t)(0x50B2 + ax + 2 + 0x14);
            for (uint16_t i = 0; i < 0x15; ++i)
                DS_U8(ds, (uint16_t)(di + i)) = DS_U8(ds, (uint16_t)(0xE3FA + i));
        }
        if (ratings_save(g, host) < 0)
            return -1;
    }
    DS_U8(ds, DS_FACILITY_SCREEN) = 0;
    return 0;
}

static int dos_call(Game *g, const ProgramServices *host, CpuRegs *r)
{
    return machine_interrupt(g, host->machine, 0x21, r);
}

/* orig 0000:0000   the program: memory resized to the program (DOS 4Ah), the adapter (EGA or
 * VGA, else a message and the end), the options, a 0A00h-paragraph block (DOS 48h, kept at
 * DS:7B8C), EMS, the preload, the set-up, the intro unless DS:5BF6; then menu, game and the
 * after-game screens until the player quits: the credits, the memory and the machine given
 * back. psp: ES at the entry. Returns 0 when the program ends; 2 when the starting kit sent
 * the original astray (startup_inventory). */
int program_start(Game *g, uint16_t psp, const ProgramServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || !host->machine)
        return -1;
    const MachineServices *mc = host->machine;
    DS_U16(ds, ARG_PSP) = psp;
    CpuRegs r = regs_of(g);
    r.ax = (uint16_t)(0x4A00 | (g->ds_seg & 0xFF));
    r.bx = (uint16_t)(g->ds_seg + 0x1040 - psp);
    r.es = psp;
    if (dos_call(g, host, &r) < 0)
        return -1;
    uint16_t adapter;
    if (adapter_detect(g, mc, r.ax, &adapter) < 0)
        return -1;
    if ((uint8_t)adapter != 2) {
        if ((uint8_t)adapter != 4) {
            r = regs_of(g);
            r.ax = (uint16_t)(0x0900 | (adapter & 0xFF));
            r.dx = 0x018E;
            return dos_call(g, host, &r) < 0 ? -1 : 0;
        }
        DS_U8(ds, 0xADD0) = 0xFF;
    }
    int status = startup_options(g, host);
    if (status)
        return status < 0 ? -1 : 0;
    if (DS_U8(ds, OPT_LINK)) {
        r = regs_of(g);
        r.ax = 3;
        if (bios_video_call(g, mc, &r) < 0)
            return -1;
        r.ax = (uint16_t)(0x0900 | (r.ax & 0xFF));
        r.dx = 0x01E2;
        r.ds = g->ds_seg;
        return dos_call(g, host, &r) < 0 ? -1 : 0;
    }
    r = regs_of(g);
    r.ax = 0x4800;
    r.bx = 0x0A00;
    if (dos_call(g, host, &r) < 0)
        return -1;
    if (!(r.flags & FLAG_CF))
        DS_U16(ds, 0x7B8C) = r.ax;
    if (ems_setup(g, mc) < 0)
        return -1;
    if (DS_U16(ds, 0x7B86))
        music_mark_ending(ds);
    if (startup_preload(g, host) < 0 || startup_init(g, host) < 0 || host_call(g, host, 0, 0x8BA2, NULL) < 0)
        return -1;
    if (!DS_U8(ds, 0x5BF6) && startup_intro(g, host) < 0)
        return -1;
    for (;;) { /* 0080 */
        palette_registers(g, mc, 0x1521);
        if (video_mode(g, host, 0x0E) < 0)
            return -1;
        palette_registers(g, mc, 0x1521);
        session_clear_flags(ds);
        session_clear_items(ds);
        session_reset(g);
        session_pointers(ds);
        if (host_call(g, host, 0, 0x9922, NULL) < 0)
            return -1;
        palette_registers(g, mc, 0x1521);
        if (DS_U8(ds, DS_MISSION_OVER) == 0x55)
            break;
        if (host_call(g, host, 0, 0xEA86, NULL) < 0 || host_call(g, host, 0, 0x8C64, NULL) < 0
            || host_call(g, host, 0, 0x8C13, NULL) < 0)
            return -1;
        status = startup_inventory(g, host, NULL);
        if (status)
            return status;
        opponent_init_difficulty(ds);
        if (startup_position(g, host) < 0 || host_call(g, host, 0, 0x8C52, NULL) < 0)
            return -1;
        r = regs_of(g);
        r.bx = 1;
        if (host_call(g, host, 0, 0x02B5, &r) < 0 || startup_game_setup(g, host) < 0)
            return -1;
        if (DS_U8(ds, OPT_LINK) && host_ax(g, host, 0x151B, 0x000E, 3) < 0) /* the word pushed: in AX */
            return -1;
        DS_U16(ds, 0xB73A) = 0x1D06;
        if (host_call(g, host, 0x151B, 0x0437, NULL) < 0 || host_call(g, host, 0, 0x0155, NULL) < 0)
            return -1;
        if (DS_U8(ds, OPT_LINK) && host_call(g, host, 0x151B, 0x009D, NULL) < 0)
            return -1;
        if (host_call(g, host, 0, 0x8C45, NULL) < 0)
            return -1;
        divide_handler_remove(g);
        keyboard_flush(g);
        uint8_t over = DS_U8(ds, DS_MISSION_OVER);
        if (over == 0xAA)
            continue;
        if (over == 0x55)
            break;
        static const uint16_t after[] = {0x5B6A, 0x8C96, 0x8BA2, 0x8986};
        for (unsigned i = 0; i < 4; ++i)
            if (host_call(g, host, 0, after[i], NULL) < 0)
                return -1;
        if (ratings_commit(g, host) < 0)
            return -1;
    }
    /* 011F */
    if (!DS_U8(ds, 0xEA3C)) {
        static const uint16_t music[] = {0x8C64, 0x8C96, 0x8BA2, 0x8986};
        for (unsigned i = 0; i < 4; ++i)
            if (host_call(g, host, 0, music[i], NULL) < 0)
                return -1;
    }
    if (host_call(g, host, 0, 0x91EA, NULL) < 0 || host_call(g, host, 0, 0x8C64, NULL) < 0)
        return -1;
    if (DS_U16(ds, 0x7B8C)) {
        r = regs_of(g);
        r.es = DS_U16(ds, 0x7B8C);
        r.ax = 0x4900;
        if (dos_call(g, host, &r) < 0)
            return -1;
    }
    if (ems_release(g, mc) < 0 || keyboard_remove(g, mc) < 0)
        return -1;
    return video_mode(g, host, 3) < 0 ? -1 : 0;
}
