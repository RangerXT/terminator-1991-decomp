/* The sound layer (0000:EFA0 .. F4DB, 89F0, 8A41, 8BA2, 8C13, 8C33, 8C96) and the 32-bit
 * division of the run-time library (FAF3, FAF7, FAFC, FB01, the body FB04).
 *
 * A thin library between the game and its sound drivers: wrappers that call a driver's
 * entry with the function number in BX (the voice driver at 101F:0000, the music driver at
 * 10BB:0000, the FM driver at 0FBA:058F, the sample driver's routines in 5B67), the Sound
 * Blaster and AdLib detection through the ports (DSP at DS:EA3E + 6 / A / C / E, the FM chip
 * at + 8 / 9), and the IRQ detection, which points IRQ 2, 3, 5 and 7 at four small handlers,
 * has the DSP raise its interrupt and waits for one of them to note which it was. The
 * drivers themselves are not the game's: they are the host's, called by address through
 * ProgramServices.call with every register. Registers follow the original's throughout.
 */
#include "term.h"

#define FLAG_CF 0x0001
#define FLAG_ZF 0x0040

enum {
    SB_BASE = 0xEA3E,  /* u16: the card's port base */
    SB_IRQ = 0xEA40,   /* u16: the IRQ the detection saw */
    SB_MASK = 0xEA38,  /* u8: the PIC mask kept meanwhile */
    MUSIC_FLAG = 0xEA3C,
};

static uint16_t code_segment(const Game *g)
{
    return (uint16_t)(g->ds_seg - 0x5C27);
}

static uint8_t in8(Game *g, const MachineServices *mc, uint16_t port)
{
    return (uint8_t)(mc && mc->in ? mc->in(g, port, 1, mc->user) : 0xFF);
}

static void out8(Game *g, const MachineServices *mc, uint16_t port, uint8_t value)
{
    if (mc && mc->out)
        mc->out(g, port, 1, value, mc->user);
}

static uint16_t base(Game *g)
{
    return DS_U16(g->ds, SB_BASE);
}

/* ADD DL,n / SUB DL,n: DH untouched */
static uint16_t dl_add(uint16_t dx, int n)
{
    return (uint16_t)((dx & 0xFF00) | (uint8_t)(dx + n));
}

static void set_al(CpuRegs *r, uint8_t al)
{
    r->ax = (uint16_t)((r->ax & 0xFF00) | al);
}

static void set_cf(CpuRegs *r, int cf)
{
    r->flags = (uint16_t)((r->flags & ~FLAG_CF) | (cf ? FLAG_CF : 0));
}

static int driver(Game *g, const ProgramServices *host, uint16_t seg, uint16_t off, CpuRegs *r)
{
    return !host || !host->call || host->call(g, seg, off, r, host->user) ? -1 : 0;
}

/* orig 0000:EFA0   a byte from the DSP: AL, CF when none came in 200h polls of + E */
void sb_dsp_read(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = dl_add(base(g), 0x0E);
    uint8_t al = (uint8_t)r->ax;
    int ready = 0;
    for (uint16_t cx = 0x200; cx; --cx) {
        al = in8(g, mc, dx);
        if (al & 0x80) {
            ready = 1;
            break;
        }
    }
    if (ready)
        al = in8(g, mc, dl_add(dx, -4));
    set_al(r, al);
    set_cf(r, !ready);
}

/* orig 0000:EFBE   AL to the DSP (+ C) once it is ready (AH = AL), CF after 200h polls */
void sb_dsp_write(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = dl_add(base(g), 0x0C);
    uint8_t ah = (uint8_t)r->ax, al = ah;
    int ready = 0;
    for (uint16_t cx = 0x200; cx; --cx) {
        al = in8(g, mc, dx);
        if (!(al & 0x80)) {
            ready = 1;
            break;
        }
    }
    if (ready) {
        al = ah;
        out8(g, mc, dx, al);
    }
    r->ax = (uint16_t)(ah << 8 | al);
    set_cf(r, !ready);
}

/* orig 0000:EFDD   a byte from the DSP, waiting as long as it takes */
void sb_dsp_read_wait(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = dl_add(base(g), 0x0E);
    while (!(in8(g, mc, dx) & 0x80))
        ;
    set_al(r, in8(g, mc, dl_add(dx, -4)));
}

/* orig 0000:EFF2   AL to the DSP, waiting as long as it takes (AH = AL) */
void sb_dsp_write_wait(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = (uint16_t)(base(g) + 0x0C);
    uint8_t ah = (uint8_t)r->ax;
    while (in8(g, mc, dx) & 0x80)
        ;
    out8(g, mc, dx, ah);
    r->ax = (uint16_t)(ah << 8 | ah);
}

/* orig 0000:F030 / F048   the IRQ DS:EA40 unmasked / masked at the PIC (SHL AH,CL: 0 from 8) */
void sb_irq_unmask(Game *g, const MachineServices *mc)
{
    uint8_t cl = (uint8_t)DS_U16(g->ds, SB_IRQ) & 0x1F;
    uint8_t ah = (uint8_t)~(cl < 8 ? 1u << cl : 0u);
    out8(g, mc, 0x21, (uint8_t)(in8(g, mc, 0x21) & ah));
}

void sb_irq_mask(Game *g, const MachineServices *mc)
{
    uint8_t cl = (uint8_t)DS_U16(g->ds, SB_IRQ) & 0x1F;
    uint8_t ah = (uint8_t)(cl < 8 ? 1u << cl : 0u);
    out8(g, mc, 0x21, (uint8_t)(in8(g, mc, 0x21) | ah));
}

static const struct {
    uint8_t vector, irq;
    uint16_t handler;
} SB_HANDLERS[4] = {{0x0A, 2, 0xF13A}, {0x0B, 3, 0xF11C}, {0x0D, 5, 0xF147}, {0x0F, 7, 0xF154}};

/* orig 0000:F11C, F13A, F147, F154   the detection's handlers of IRQ 3, 2, 5, 7: the IRQ noted
 * at DS:EA40, the DSP's interrupt acknowledged (+ E), end of interrupt */
void sb_irq_handler(Game *g, const MachineServices *mc, uint8_t irq)
{
    DS_U16(g->ds, SB_IRQ) = irq;
    in8(g, mc, (uint16_t)(base(g) + 0x0E));
    out8(g, mc, 0x20, 0x20);
}

/* an interrupt the machine raises now: one of the detection's handlers when its vector
 * points there (another handler is not the game's, and nothing the C runs) */
static void take_irq(Game *g, const MachineServices *mc)
{
    if (!mc || !mc->irq)
        return;
    int vector = mc->irq(g, mc->user);
    if (vector < 0)
        return;
    uint32_t at = vector_get(g, (uint16_t)vector);
    for (int i = 0; i < 4; ++i)
        if (at == ((uint32_t)code_segment(g) << 16 | SB_HANDLERS[i].handler)) {
            sb_irq_handler(g, mc, SB_HANDLERS[i].irq);
            return;
        }
}

/* orig 0000:F05E   which IRQ the card uses: the four handlers in (the old vectors kept), IRQ
 * 2 3 5 7 unmasked, DSP command F2h, up to 65536 looks at DS:EA40, all put back: AX = the
 * IRQ, 0 when none came. BX, CX, DX as the original leaves them. */
void sb_irq_detect(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint32_t old[4];
    for (int i = 0; i < 4; ++i) {
        old[i] = vector_get(g, SB_HANDLERS[i].vector);
        vector_set(g, SB_HANDLERS[i].vector, SB_HANDLERS[i].handler, code_segment(g));
    }
    uint8_t mask = in8(g, mc, 0x21);
    DS_U8(ds, SB_MASK) = mask;
    out8(g, mc, 0x21, mask & 0x53);
    DS_U16(ds, SB_IRQ) = 0;
    r->ax = 0x00F2;
    sb_dsp_write_wait(g, mc, r);
    uint16_t cx = 0;
    do { /* LOOP from 0: 65536 */
        take_irq(g, mc);
        if (DS_U16(ds, SB_IRQ))
            break;
    } while (--cx);
    out8(g, mc, 0x21, DS_U8(ds, SB_MASK));
    for (int i = 3; i >= 0; --i)
        vector_set(g, SB_HANDLERS[i].vector, (uint16_t)old[i], (uint16_t)(old[i] >> 16));
    r->ax = DS_U16(ds, SB_IRQ);
    r->bx = (uint16_t)(SB_HANDLERS[0].vector << 2);
    r->cx = cx;
    r->dx = (uint16_t)(old[0] >> 16);
}

/* orig 0000:F162   the DSP reset: speaker off (D3h, then a pause), 1 and 0 to + 6, AAh
 * awaited in 20h reads: AX = 0, or 1 with CF */
void sb_dsp_reset(Game *g, const MachineServices *mc, CpuRegs *r)
{
    r->dx = (uint16_t)(base(g) + 0x0C);
    set_al(r, 0xD3);
    sb_dsp_write(g, mc, r);
    if (!(r->flags & FLAG_CF))
        r->cx = 0; /* LOOP $ from FFFFh */
    r->dx = dl_add(base(g), 6);
    out8(g, mc, r->dx, 1);
    out8(g, mc, r->dx, 0); /* after DEC AL from 0 to 0 */
    set_al(r, 0);
    for (r->cx = 0x20;;) {
        sb_dsp_read(g, mc, r);
        if (!(r->flags & FLAG_CF) && (uint8_t)r->ax == 0xAA) {
            r->ax = 0;
            r->flags = (uint16_t)((r->flags & ~FLAG_CF) | FLAG_ZF);
            return;
        }
        if (!--r->cx)
            break;
    }
    r->ax = 1;
    set_cf(r, 1);
}

/* orig 0000:F3B8   five reads of the FM status, its delay */
void adlib_delay(Game *g, const MachineServices *mc)
{
    uint16_t dx = dl_add(base(g), 8);
    for (int i = 0; i < 5; ++i)
        in8(g, mc, dx);
}

/* orig 0000:F3A5   the FM register AL := AH (DX = + 9, AL = AH after) */
void adlib_write(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = dl_add(base(g), 8);
    uint8_t ah = (uint8_t)(r->ax >> 8);
    out8(g, mc, dx, (uint8_t)r->ax);
    adlib_delay(g, mc);
    dx = (uint16_t)(dx + 1);
    out8(g, mc, dx, ah);
    adlib_delay(g, mc);
    r->dx = dx;
    r->ax = (uint16_t)(ah << 8 | ah);
}

/* orig 0000:F384   the FM status's top three bits = AL's, in 40h reads; CF when not */
void adlib_wait_status(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = dl_add(base(g), 8);
    uint8_t ah = (uint8_t)r->ax & 0xE0, al = (uint8_t)r->ax;
    int found = 0;
    for (uint16_t cx = 0x40; cx; --cx) {
        al = in8(g, mc, dx) & 0xE0;
        if (al == ah) {
            found = 1;
            break;
        }
    }
    r->ax = (uint16_t)(ah << 8 | al);
    set_cf(r, !found);
}

/* orig 0000:F2FA   what is at the base: AX bit 0 the + 6 / + A echo, bit 2 a DSP (reset,
 * E0h identifies C6h as 39h), bit 1 (added) the FM chip (its timer 1 at the status) */
void sb_detect(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t bx = 0;
    uint16_t dx = dl_add(base(g), 6);
    out8(g, mc, dx, 0xC6);
    dx = dl_add(dx, 4);
    out8(g, mc, dx, 0);
    uint8_t al = in8(g, mc, dx);
    int dsp = 1;
    if (al == 0xC6) {
        dx = dl_add(dx, -4);
        out8(g, mc, dx, 0x39);
        dx = dl_add(dx, 4);
        out8(g, mc, dx, 0);
        al = in8(g, mc, dx);
        if (al == 0x39) {
            bx = 1;
            dsp = 0;
        }
    }
    r->dx = dx;
    set_al(r, al);
    r->bx = bx;
    if (dsp) { /* F327 */
        sb_dsp_reset(g, mc, r);
        if (!(r->flags & FLAG_CF)) {
            set_al(r, 0xE0);
            sb_dsp_write(g, mc, r);
            if (!(r->flags & FLAG_CF)) {
                set_al(r, 0xC6);
                sb_dsp_write(g, mc, r);
                if (!(r->flags & FLAG_CF)) {
                    sb_dsp_read(g, mc, r);
                    if (!(r->flags & FLAG_CF) && (uint8_t)r->ax == 0x39)
                        r->bx = 4;
                }
            }
        }
    }
    /* F346: the FM chip's timer 1 */
    static const uint16_t reset[3] = {0x0001, 0x6004, 0x8004};
    for (int i = 0; i < 3; ++i) {
        r->ax = reset[i];
        adlib_write(g, mc, r);
    }
    set_al(r, 0);
    adlib_wait_status(g, mc, r);
    if (!(r->flags & FLAG_CF)) {
        r->ax = 0xFF02;
        adlib_write(g, mc, r);
        r->ax = 0x2104;
        adlib_write(g, mc, r);
        set_al(r, 0xC0);
        adlib_wait_status(g, mc, r);
        if (!(r->flags & FLAG_CF)) {
            r->ax = 0x6004;
            adlib_write(g, mc, r);
            r->ax = 0x8004;
            adlib_write(g, mc, r);
            r->bx = (uint16_t)(r->bx + 2);
        }
    }
    r->ax = r->bx;
}

/* orig 0000:F3CA   the music driver (10BB) at the base (BX FFFDh), started (FFFFh; CF: AX = 0),
 * then DS:EA3C given as its status word (1), the old one kept at CS:F405: AX = 1 */
int music_driver_init(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint16_t ds = r->ds;
    r->ds = g->ds_seg;
    r->ax = base(g);
    r->bx = 0xFFFD;
    if (driver(g, host, 0x10BB, 0, r) < 0)
        return -1;
    r->bx = 0xFFFF;
    if (driver(g, host, 0x10BB, 0, r) < 0)
        return -1;
    if (r->flags & FLAG_CF) {
        r->ax = 0;
        r->flags = (uint16_t)((r->flags & ~FLAG_CF) | FLAG_ZF);
    } else {
        r->dx = g->ds_seg;
        r->ax = MUSIC_FLAG;
        r->bx = 1;
        if (driver(g, host, 0x10BB, 0, r) < 0)
            return -1;
        uint8_t *code = far_ptr(g, code_segment(g), 0);
        code[0xF407] = (uint8_t)r->dx;
        code[0xF408] = (uint8_t)(r->dx >> 8);
        code[0xF405] = (uint8_t)r->ax;
        code[0xF406] = (uint8_t)(r->ax >> 8);
        r->ax = 1;
    }
    r->ds = ds;
    return 0;
}

/* orig 0000:F4C1   the music driver stopped (FFFEh) and its old status word given back */
int music_driver_close(Game *g, const ProgramServices *host, CpuRegs *r)
{
    r->bx = 0xFFFE;
    if (driver(g, host, 0x10BB, 0, r) < 0)
        return -1;
    const uint8_t *code = far_ptr(g, code_segment(g), 0);
    r->bx = 1;
    r->dx = (uint16_t)(code[0xF407] | code[0xF408] << 8);
    r->ax = (uint16_t)(code[0xF405] | code[0xF406] << 8);
    return driver(g, host, 0x10BB, 0, r);
}

/* orig 0000:F4AE   AX = DS:EA3C, which becomes FFh when it was not 0 (flags kept) */
void music_flag_take(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    r->ax = 0;
    if (DS_U8(ds, MUSIC_FLAG)) {
        set_al(r, DS_U8(ds, MUSIC_FLAG));
        DS_U8(ds, MUSIC_FLAG) = 0xFF;
    }
}

/* the wrappers of the driver functions: the C library's calls with their stack arguments
 * (args[0] at [BP+4]) */
int sound_wrapper(Game *g, const ProgramServices *host, uint16_t entry, CpuRegs *r, const uint16_t *args)
{
    uint16_t es = r->es, di = r->di;
    switch (entry) {
    case 0xF19E: /* voice driver (101F) functions by BX */
    case 0xF1FC:
    case 0xF205:
    case 0xF23F:
    case 0xF248:
        r->bx = entry == 0xF19E ? 0 : entry == 0xF1FC ? 8 : entry == 0xF205 ? 9 : entry == 0xF23F ? 0x0A : 0x0B;
        return driver(g, host, 0x101F, 0, r);
    case 0xF1A7: /* the port, the IRQ, start, then the status word DS:EA3A */
        r->bx = 1;
        r->ax = base(g);
        if (driver(g, host, 0x101F, 0, r) < 0)
            return -1;
        r->bx = 2;
        r->ax = DS_U16(g->ds, SB_IRQ);
        if (driver(g, host, 0x101F, 0, r) < 0)
            return -1;
        r->bx = 3;
        if (driver(g, host, 0x101F, 0, r) < 0)
            return -1;
        r->ax = r->es = g->ds_seg; /* MOV AX,DS; MOV ES,AX */
        r->di = 0xEA3A;
        r->bx = 5;
        if (driver(g, host, 0x101F, 0, r) < 0)
            return -1;
        r->es = es;
        return 0;
    case 0xF1D8:
    case 0xF251:
        r->bx = entry == 0xF1D8 ? 4 : 0x0C;
        r->ax = args[0];
        return driver(g, host, 0x101F, 0, r);
    case 0xF1E8:
    case 0xF22B:
        r->bx = entry == 0xF1E8 ? 5 : 6;
        r->di = args[0];
        r->es = args[1];
        if (driver(g, host, 0x101F, 0, r) < 0)
            return -1;
        r->di = di;
        r->es = es;
        return 0;
    case 0xF20E:
        r->bx = 7;
        r->ax = args[4];
        r->dx = args[3];
        r->cx = args[2];
        r->di = args[0];
        r->es = args[1];
        if (driver(g, host, 0x101F, 0, r) < 0)
            return -1;
        r->di = di;
        r->es = es;
        return 0;
    case 0xF262: /* the FM driver */
        r->bx = 0;
        return driver(g, host, 0x0FBA, 0x058F, r);
    case 0xF409: /* music driver (10BB) functions: DX:AX a far pointer, CX a count */
    case 0xF41C:
    case 0xF42F:
        r->dx = args[1];
        r->ax = args[0];
        if (entry == 0xF42F)
            r->cx = args[2];
        r->bx = entry == 0xF409 ? 1 : entry == 0xF41C ? 6 : 2;
        return driver(g, host, 0x10BB, 0, r);
    case 0xF452:
    case 0xF462:
    case 0xF484:
        r->ax = args[0];
        r->bx = entry == 0xF452 ? 3 : entry == 0xF462 ? 4 : 5;
        return driver(g, host, 0x10BB, 0, r);
    case 0xF445:
    case 0xF472:
    case 0xF47B:
    case 0xF494:
    case 0xF4A1:
        r->bx = entry == 0xF445 ? 8 : entry == 0xF472 ? 7 : entry == 0xF47B ? 0 : entry == 0xF494 ? 9 : 0x0A;
        return driver(g, host, 0x10BB, 0, r);
    case 0xF4DB: /* BX as it is */
        return driver(g, host, 0x10BB, 0, r);
    }
    return -1;
}

static void neg32(uint16_t *hi, uint16_t *lo)
{
    uint16_t borrow = *lo != 0;
    *lo = (uint16_t)-*lo;
    *hi = (uint16_t)(-*hi - borrow);
}

/* orig 0000:FB04 (entries FAF3 signed quotient, FAF7 unsigned, FAFC signed remainder, FB01
 * unsigned)   the 32-bit division of the C library, arguments on the stack: AX:DX the
 * result, BX and CX as it leaves them. With both high words 0, or the divisor's high word 0
 * and its low one too, a 16-bit DIV; a divide error there resumes after it (the game's
 * handler 0407), AX and DX as they were. */
void long_division(uint16_t mode, uint16_t a_lo, uint16_t a_hi, uint16_t b_lo, uint16_t b_hi, CpuRegs *r)
{
    uint16_t di = mode, ax = a_lo, dx = a_hi, bx = b_lo, cx = b_hi;
    if (!cx && (!dx || !bx)) { /* FB88 */
        if (bx) {
            uint32_t n = (uint32_t)dx << 16 | ax;
            ax = (uint16_t)(n / bx);
            dx = (uint16_t)(n % bx);
        }
        if (di & 2)
            ax = dx;
        r->ax = ax;
        r->dx = 0;
        r->bx = bx;
        r->cx = cx;
        return;
    }
    if (!(di & 1)) {
        if (dx & 0x8000) {
            neg32(&dx, &ax);
            di |= 0x0C;
        }
        if (cx & 0x8000) {
            neg32(&cx, &bx);
            di ^= 4;
        }
    }
    uint16_t bp = cx, hi = 0, lo = 0;
    for (int i = 0; i < 32; ++i) {
        uint16_t c1 = ax >> 15, c2 = dx >> 15, c3 = lo >> 15;
        ax = (uint16_t)(ax << 1);
        dx = (uint16_t)(dx << 1 | c1);
        lo = (uint16_t)(lo << 1 | c2);
        hi = (uint16_t)(hi << 1 | c3);
        if (hi > bp || (hi == bp && lo >= bx)) {
            uint32_t s = ((uint32_t)hi << 16 | lo) - ((uint32_t)bp << 16 | bx);
            hi = (uint16_t)(s >> 16);
            lo = (uint16_t)s;
            ax++;
        }
    }
    bx = di;
    if (bx & 2) {
        ax = lo;
        dx = hi;
        bx >>= 1;
    }
    if (bx & 4)
        neg32(&dx, &ax);
    r->ax = ax;
    r->dx = dx;
    r->bx = bx;
    r->cx = 0;
}

static uint16_t far_word(Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(*far_ptr(g, seg, off) | *far_ptr(g, seg, (uint16_t)(off + 1)) << 8);
}

/* orig 0000:8A41   the song at ES:0 started: its tempo (word + Ch) as the timer rate
 * 1234DCh / tempo (FAF3; music function 4), its instruments (far + 6, count + 24h; function
 * 2, when there are some) and its notes (far + 8, function 6). SI comes back as the tempo's
 * sign word (see the end). */
int music_song_start(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint16_t es = r->es, bp = r->bp;
    uint16_t off6 = far_word(g, es, 6), off8 = far_word(g, es, 8);
    uint16_t tempo = far_word(g, es, 0x0C);
    r->bx = off8;
    r->ax = tempo;
    r->dx = (uint16_t)(tempo & 0x8000 ? 0xFFFF : 0); /* CWD */
    uint16_t high = r->dx;
    long_division(0, 0x34DC, 0x0012, tempo, high, r);
    uint16_t rate = r->ax;
    if (sound_wrapper(g, host, 0xF462, r, &rate) < 0)
        return -1;
    r->cx = rate; /* POP CX */
    if (off6) {
        uint16_t args[3] = {off6, es, far_word(g, es, 0x24)};
        if (sound_wrapper(g, host, 0xF42F, r, args) < 0)
            return -1;
    }
    uint16_t args[2] = {off8, es};
    if (sound_wrapper(g, host, 0xF41C, r, args) < 0)
        return -1;
    /* FAF3's RET 8 left the divisor's high word on the stack: POP SI takes it */
    r->si = high;
    r->bp = bp;
    return 0;
}

/* orig 0000:89F0   with AdLib or a Sound Blaster (DS:A773 2 or 4): the song DS:DX loaded
 * into the music block (DS:A743) if it fits (DS:A761, paragraphs left of A75F), then
 * started (8A41, also after a failed load) */
int music_load(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    const MachineServices *mc = host ? host->machine : NULL;
    if (!mc)
        return -1;
    uint16_t es = r->es;
    uint16_t sound = DS_U16(ds, 0xA773);
    if (sound != 2 && sound != 4)
        return 0;
    for (uint16_t i = 0; i < 18; ++i) /* REP STOSW at ES:A745, 9 words */
        *far_ptr(g, r->es, (uint16_t)(0xA745 + i)) = 0;
    r->di = (uint16_t)(0xA745 + 18);
    r->cx = 0;
    r->ax = 0;
    DS_U16(ds, 0xA761) = DS_U16(ds, 0xA75F);
    DS_U8(ds, 0xA6EA) = 0xFF;
    r->si = r->dx;
    r->di = 0x77E5;
    r->ax = 0;
    if (dos_find_first(g, mc, r) < 0)
        return -1;
    if (!(r->flags & FLAG_ZF)) {
        r->es = es;
        return 0;
    }
    r->cx = 4;
    r->bx = (uint16_t)(((int16_t)DS_U16(ds, (uint16_t)(r->di + 0x1A)) >> 4) + 1);
    uint16_t left = (uint16_t)(DS_U16(ds, 0xA761) - r->bx);
    DS_U16(ds, 0xA761) = left;
    if (left & 0x8000) {
        r->es = es;
        return 0;
    }
    r->ax = DS_U16(ds, 0xA743);
    r->es = r->ax;
    r->bx = 0;
    if (dos_load_file(g, mc, r) < 0 || music_song_start(g, host, r) < 0)
        return -1;
    r->es = es;
    return 0;
}

/* orig 0000:8BA2   the sound at start-up: AdLib at 380h, or a Sound Blaster at 220h
 * (DS:A863) detected, its IRQ (DS:A865) when it has the DSP and the FM chip; the music
 * driver started (not for a DSP without FM, nor for the PC speaker); a block for the music
 * (DOS 48h: E00h paragraphs, else the largest less 8Ch; DS:A743, A75F) */
int sound_init(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    const MachineServices *mc = host ? host->machine : NULL;
    if (!mc)
        return -1;
    uint16_t es = r->es;
    uint16_t sound = DS_U16(ds, 0xA773);
    int init = 0;
    if (sound == 2) {
        DS_U16(ds, SB_BASE) = 0x380;
        init = 1;
    } else if (sound == 4) {
        DS_U16(ds, SB_BASE) = 0x220;
        DS_U16(ds, 0xA863) = 0x220;
        sb_detect(g, mc, r);
        init = 1;
        if (r->ax & 4) {
            if (!(r->ax & 2))
                init = 0;
            else {
                sb_irq_detect(g, mc, r);
                if (r->ax)
                    DS_U8(ds, 0xA865) = (uint8_t)r->ax;
            }
        }
    }
    if (init && music_driver_init(g, host, r) < 0)
        return -1;
    if (!DS_U16(ds, 0xA75F)) { /* 8BE7 */
        r->bx = 0x0E00;
        r->ax = (uint16_t)(0x4800 | (r->ax & 0xFF));
        if (machine_interrupt(g, mc, 0x21, r) < 0)
            return -1;
        DS_U16(ds, 0xA75F) = 0x0D74;
        DS_U16(ds, 0xA743) = r->ax;
        if (r->flags & FLAG_CF) {
            DS_U16(ds, 0xA75F) = (uint16_t)(r->bx - 0x8C);
            r->ax = (uint16_t)(0x4800 | (r->ax & 0xFF));
            if (machine_interrupt(g, mc, 0x21, r) < 0)
                return -1;
            if (!(r->flags & FLAG_CF))
                DS_U16(ds, 0xA743) = r->ax;
        }
    }
    DS_U8(ds, 0xA615) = 0xFF;
    r->es = es;
    return 0;
}

/* orig 0000:8C13   the sample driver: its device (5B67:0786, BX = DS:A773; carry: none),
 * then 08C5 and 0895 with BX = 6; DS:A614 set */
int sample_init(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint16_t es = r->es;
    r->bx = DS_U16(g->ds, 0xA773);
    if (driver(g, host, 0x5B67, 0x0786, r) < 0)
        return -1;
    r->bx = 6;
    if (!(r->flags & FLAG_CF)) {
        if (driver(g, host, 0x5B67, 0x08C5, r) < 0 || driver(g, host, 0x5B67, 0x0895, r) < 0)
            return -1;
        DS_U8(g->ds, 0xA614) = 0xFF;
    }
    r->es = es;
    return 0;
}

/* orig 0000:8C33   the music block given back (DOS 49h) */
int sound_memory_free(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint16_t es = r->es;
    r->ax = DS_U16(g->ds, 0xA743);
    r->es = r->ax;
    r->ax = (uint16_t)(0x4900 | (r->ax & 0xFF));
    if (!host || machine_interrupt(g, host->machine, 0x21, r) < 0)
        return -1;
    r->es = es;
    return 0;
}

/* orig 0000:8C96   with the sample driver (DS:A614): its stop (5B67:0915) and the device's
 * (the far pointer DS:AA78), the speaker off (port 61h bits 0, 1) */
int sample_stop(Game *g, const ProgramServices *host, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0xA614))
        return 0;
    uint16_t es = r->es;
    /* the far pointer holds the running segment: to the host as the file's (5B67) */
    uint16_t seg = (uint16_t)(DS_U16(ds, 0xAA7A) - code_segment(g));
    if (driver(g, host, 0x5B67, 0x0915, r) < 0 || driver(g, host, seg, DS_U16(ds, 0xAA78), r) < 0)
        return -1;
    uint8_t al = (uint8_t)(in8(g, host->machine, 0x61) & 0xFC);
    out8(g, host->machine, 0x61, al);
    set_al(r, al);
    r->es = es;
    return 0;
}
