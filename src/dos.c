/* The game's DOS file library (0000:F63F .. F8D5), against the machine interface. The
 * routines pass everything in registers and answer in CF / ZF, so each takes the register
 * block and leaves it as the original does (what it saves and restores, what it returns).
 * Errors are kept at DS:EA50, in the segment the code word 0000:F8FA names (F8B3 / F8D5).
 */
#include "term.h"

#define FLAG_CF 0x0001
#define FLAG_ZF 0x0040

static void flags(CpuRegs *r, int cf, int zf)
{
    r->flags = (uint16_t)((r->flags & ~(FLAG_CF | FLAG_ZF)) | (cf ? FLAG_CF : 0) | (zf ? FLAG_ZF : 0));
}

static int carry(const CpuRegs *r)
{
    return r->flags & FLAG_CF;
}

static uint8_t *at(Game *g, uint16_t seg, uint16_t off)
{
    return far_ptr(g, seg, 0) + off;
}

static uint8_t byte_at(Game *g, uint16_t seg, uint16_t off)
{
    return *far_ptr(g, seg, off);
}

static uint16_t word_at(Game *g, uint16_t seg, uint16_t off)
{
    const uint8_t *p = far_ptr(g, seg, 0);
    return (uint16_t)(p[off] | p[(uint16_t)(off + 1)] << 8);
}

static void put_word(Game *g, uint16_t seg, uint16_t off, uint16_t value)
{
    uint8_t *p = far_ptr(g, seg, 0);
    p[off] = (uint8_t)value;
    p[(uint16_t)(off + 1)] = (uint8_t)(value >> 8);
}

static int dos(Game *g, const MachineServices *mc, CpuRegs *r)
{
    return machine_interrupt(g, mc, 0x21, r);
}

static uint16_t data_segment(Game *g)
{
    const uint8_t *code = far_ptr(g, (uint16_t)(g->ds_seg - 0x5C27), 0);
    return (uint16_t)(code[0xF8FA] | code[0xF8FB] << 8);
}

/* orig 0000:F8B3 */
void dos_store_error(Game *g, uint16_t ax)
{
    uint8_t *p = far_ptr(g, data_segment(g), 0);
    p[0xEA50] = (uint8_t)ax;
    p[0xEA51] = (uint8_t)(ax >> 8);
}

/* orig 0000:F8D5 */
uint16_t dos_last_error(Game *g)
{
    const uint8_t *p = far_ptr(g, data_segment(g), 0);
    return (uint16_t)(p[0xEA50] | p[0xEA51] << 8);
}

/* orig 0000:FA72   the length of DS:SI */
static uint16_t length_of(Game *g, uint16_t seg, uint16_t off)
{
    uint16_t n = 0;
    while (byte_at(g, seg, (uint16_t)(off + n)))
        n++;
    return n;
}

/* orig 0000:FA5D   SI to the NUL of DS:SI */
uint16_t dos_string_end(Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(off + length_of(g, seg, off));
}

/* orig 0000:F63F   the string DS:SI to standard output (DOS 40h, handle 1); flags from DOS */
int dos_print(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs t = *r;
    t.cx = length_of(g, r->ds, r->si);
    t.dx = r->si;
    t.bx = 1;
    t.ax = (uint16_t)(0x4000 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    r->flags = t.flags;
    return 0;
}

/* orig 0000:F714   a trailing backslash cut from DS:SI (not after a drive's colon, not in
 * a string under three characters): ZF when it was cut; CF when the string was too short */
void dos_strip_backslash(Game *g, CpuRegs *r)
{
    uint16_t n = length_of(g, r->ds, r->si);
    if (n < 3) {
        flags(r, 1, 0);
        return;
    }
    uint16_t last = (uint16_t)(r->si + n - 1);
    if (byte_at(g, r->ds, last) != '\\') {
        flags(r, byte_at(g, r->ds, last) < '\\', 0); /* CMP [SI],5Ch */
        return;
    }
    if (byte_at(g, r->ds, (uint16_t)(last - 1)) == ':') {
        flags(r, 0, 0); /* TEST SP,SP */
        return;
    }
    *at(g, r->ds, last) = 0;
    flags(r, 0, 1);
}

/* orig 0000:F664   CX = 5Ch when a trailing backslash was cut, else 0 */
static void strip_for_search(Game *g, CpuRegs *r)
{
    r->cx = 0;
    dos_strip_backslash(g, r);
    if (r->flags & FLAG_ZF)
        r->cx = (uint16_t)((r->cx & 0xFF00) | 0x5C);
}

/* orig 0000:F66E   the cut character (CX: char, NUL) put back at the end of DS:SI */
static void restore_for_search(Game *g, const CpuRegs *r)
{
    if (!r->cx)
        return;
    uint16_t end = dos_string_end(g, r->ds, r->si);
    *at(g, r->ds, end) = (uint8_t)r->cx;
    *at(g, r->ds, (uint16_t)(end + 1)) = (uint8_t)(r->cx >> 8);
}

/* orig 0000:F738   AL = the current drive's letter (DOS 19h), AH as BH was (the caller's AH
 * through XCHG BX,AX) */
int dos_drive_letter(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t bx = r->bx;
    CpuRegs t = *r;
    t.bx = r->ax;
    t.ax = (uint16_t)(0x1900 | (uint8_t)r->bx);
    if (dos(g, mc, &t) < 0)
        return -1;
    uint8_t letter = (uint8_t)((uint8_t)t.ax + 0x41);
    *r = t;
    r->ax = (uint16_t)((t.bx & 0xFF00) | letter);
    r->bx = bx;
    flags(r, (uint8_t)t.ax + 0x41 > 0xFF, letter == 0);
    return 0;
}

/* orig 0000:F754   a backslash added to DS:SI unless it is empty or ends in \ or : */
void dos_add_backslash(Game *g, uint16_t seg, uint16_t off)
{
    if (!byte_at(g, seg, off))
        return;
    uint16_t end = dos_string_end(g, seg, off);
    uint8_t prev = byte_at(g, seg, (uint16_t)(end - 1));
    if (prev == '\\' || prev == ':')
        return;
    *at(g, seg, end) = '\\';
    *at(g, seg, (uint16_t)(end + 1)) = 0;
}

/* orig 0000:F6AC (into F67B)   "X:\path\" of the current drive and directory at DS:SI (DOS
 * 19h, 47h); CF on an error (kept). AX, CX, DX, SI, ES as they were. */
int dos_current_directory(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs keep = *r;
    if (dos_drive_letter(g, mc, r) < 0)
        return -1;
    CpuRegs t = *r;
    if (!(uint8_t)t.ax && dos_drive_letter(g, mc, &t) < 0)
        return -1;
    uint8_t letter = (uint8_t)(t.ax & 0xDF);
    uint16_t si = r->si;
    *at(g, r->ds, si++) = letter;
    *at(g, r->ds, si++) = ':';
    *at(g, r->ds, si++) = '\\';
    uint16_t ax = (uint16_t)((t.ax & 0xFF00) | letter);
    t.si = si;
    t.dx = (uint16_t)((ax & 0xFF00) | (uint8_t)(letter - 0x40));
    t.ax = (uint16_t)(0x4700 | (uint8_t)keep.dx);
    if (dos(g, mc, &t) < 0)
        return -1;
    int failed = carry(&t);
    if (failed)
        dos_store_error(g, t.ax);
    else
        dos_add_backslash(g, r->ds, si);
    r->bx = t.bx;
    r->di = t.di;
    r->bp = t.bp;
    r->ax = keep.ax;
    r->cx = keep.cx;
    r->dx = keep.dx;
    r->si = keep.si;
    r->es = keep.es;
    r->ds = t.ds;
    flags(r, failed, t.flags & FLAG_ZF);
    return 0;
}

/* orig 0000:F8BE   the DTA at ES:DI (kept at DS:EA4C / EA4E) */
static int set_dta(Game *g, const MachineServices *mc, CpuRegs *r)
{
    put_word(g, r->ds, 0xEA4C, r->di);
    put_word(g, r->ds, 0xEA4E, r->es);
    CpuRegs t = *r;
    t.ds = r->es;
    t.dx = r->di;
    t.ax = (uint16_t)(0x1A00 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    r->dx = t.dx;
    r->flags = t.flags;
    return 0;
}

/* the answer of 0000:F6B3 / F6E8: DL = 1 found, 2 no more (or 3: path), 0 another error;
 * CMP DL,1 */
static void search_answer(CpuRegs *r, uint8_t dl)
{
    flags(r, dl < 1, dl == 1);
}

/* orig 0000:F6B3   find the first match of DS:SI (a trailing backslash cut meanwhile) with
 * the attributes AX, the DTA at ES:DI: ZF found, CF on an error other than "no more" */
int dos_find_first(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs keep = *r;
    if (set_dta(g, mc, r) < 0)
        return -1;
    r->dx = r->si;
    strip_for_search(g, r);
    uint16_t cut = r->cx;
    CpuRegs t = *r;
    t.cx = keep.ax;
    t.ax = (uint16_t)(0x4E00 | (uint8_t)cut);
    if (dos(g, mc, &t) < 0)
        return -1;
    r->bx = t.bx;
    r->si = t.si;
    r->di = t.di;
    r->cx = cut;
    restore_for_search(g, r);
    uint8_t dl = 1;
    if (carry(&t)) {
        dl = 2;
        uint16_t error = t.ax;
        if (error == 0x12)
            error = 3;
        else if (error != 3)
            dl = 0;
        dos_store_error(g, error);
    }
    r->ax = keep.ax;
    r->cx = keep.cx;
    r->dx = keep.dx;
    search_answer(r, dl);
    return 0;
}

/* orig 0000:F6E8   the next match (the DTA set again when ES:DI moved) */
int dos_find_next(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs keep = *r;
    if ((r->di != word_at(g, r->ds, 0xEA4C) || r->es != word_at(g, r->ds, 0xEA4E)) && set_dta(g, mc, r) < 0)
        return -1;
    CpuRegs t = *r;
    t.ax = (uint16_t)(0x4F00 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    uint8_t dl = 1;
    if (carry(&t)) {
        dl = t.ax == 0x12 ? 2 : 0;
        put_word(g, r->ds, 0xEA50, t.ax);
    }
    r->bx = t.bx;
    r->cx = t.cx;
    r->si = t.si;
    r->di = t.di;
    r->ax = keep.ax;
    r->dx = keep.dx;
    search_answer(r, dl);
    return 0;
}

/* orig 0000:F744   delete DS:SI (DOS 41h); CF on an error (kept) */
int dos_delete(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs t = *r;
    t.dx = r->si;
    t.ax = (uint16_t)(0x4100 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    if (carry(&t))
        dos_store_error(g, t.ax);
    r->bx = t.bx;
    r->cx = t.cx;
    r->flags = t.flags;
    return 0;
}

/* orig 0000:F770   close BX (DOS 3Eh) */
int dos_close(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs t = *r;
    t.ax = (uint16_t)(0x3E00 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    if (carry(&t))
        dos_store_error(g, t.ax);
    r->cx = t.cx;
    r->dx = t.dx;
    r->flags = t.flags;
    return 0;
}

/* orig 0000:F77C   create DS:SI with the attributes AX (DOS 3Ch); with bit 400h only when it
 * does not exist yet (else error 50h); BX = the handle; CF on an error (kept) */
int dos_create(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs keep = *r, t = *r;
    t.dx = r->si;
    t.cx = r->ax;
    int failed = 0;
    if (r->ax & 0x400) {
        CpuRegs q = t;
        q.ax = 0x4300;
        if (dos(g, mc, &q) < 0)
            return -1;
        t.bx = q.bx;
        if (!carry(&q)) {
            t.ax = 0x50;
            failed = 1;
        } else if (q.ax != 2) {
            t.ax = q.ax;
            failed = 1;
        } else
            t.ax = q.ax;
    }
    if (!failed) {
        t.ax = (uint16_t)(0x3C00 | (t.ax & 0xFF));
        if (dos(g, mc, &t) < 0)
            return -1;
        failed = carry(&t);
        if (!failed) {
            uint16_t handle = t.ax;
            t.ax = t.bx;
            t.bx = handle;
        }
    }
    if (failed)
        dos_store_error(g, t.ax);
    *r = t;
    r->ax = keep.ax;
    r->cx = keep.cx;
    r->dx = keep.dx;
    flags(r, failed, t.flags & FLAG_ZF);
    return 0;
}

/* orig 0000:F7AD   open DS:SI by the flags AX: low bits the mode (3 bits before DOS 3), 100h
 * create when missing, 200h truncate (create anew), 400h with 100h fail when it exists (50h);
 * BX = the handle; CF on an error (kept). AX, CX, DX, BP as they were. */
int dos_open(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs keep = *r, t = *r;
    uint16_t mode = r->ax;
    t.bp = r->ax;
    t.ax = keep.bp;
    t.dx = r->si;
    t.ax = 0x4300;
    if (dos(g, mc, &t) < 0)
        return -1;
    int failed = 0, create = 0;
    if (carry(&t)) {
        if (t.ax != 2)
            failed = 1;
        else if (mode & 0x100)
            create = 1;
        else {
            t.ax = 2;
            failed = 1;
        }
    } else if ((mode & 0x400) && (mode & 0x100)) {
        t.ax = 0x50;
        failed = 1;
    } else if (mode & 0x200)
        create = 1;
    if (!failed && create) { /* F7FA */
        t.cx = 0;
        t.ax = (uint16_t)(0x3C00 | (t.ax & 0xFF));
        if (dos(g, mc, &t) < 0)
            return -1;
        if (carry(&t))
            failed = 1;
        else {
            uint16_t handle = t.ax;
            t.ax = t.bx;
            t.bx = handle;
            t.ax = (uint16_t)(0x3E00 | (t.ax & 0xFF));
            if (dos(g, mc, &t) < 0)
                return -1;
            failed = carry(&t);
        }
    }
    if (!failed) { /* F7E4 */
        t.bp = t.ax;
        t.ax = mode;
        if (byte_at(g, r->ds, 0xEA4A) < 3)
            t.ax = (uint16_t)((t.ax & 0xFF00) | (t.ax & 3));
        t.ax = (uint16_t)(0x3D00 | (t.ax & 0xFF));
        if (dos(g, mc, &t) < 0)
            return -1;
        failed = carry(&t);
        if (!failed) {
            uint16_t handle = t.ax;
            t.ax = t.bx;
            t.bx = handle;
        }
    }
    if (failed)
        dos_store_error(g, t.ax);
    *r = t;
    r->ax = keep.ax;
    r->cx = keep.cx;
    r->dx = keep.dx;
    r->bp = keep.bp;
    flags(r, failed, t.flags & FLAG_ZF);
    return 0;
}

/* orig 0000:F80F   open DS:SI with the mode AL (DOS 3Dh); BX = the handle */
int dos_open_mode(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs keep = *r, t = *r;
    t.dx = r->si;
    if (byte_at(g, r->ds, 0xEA4A) < 3)
        t.ax = (uint16_t)((t.ax & 0xFF00) | (t.ax & 3));
    t.ax = (uint16_t)(0x3D00 | (t.ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    if (carry(&t))
        dos_store_error(g, t.ax);
    else {
        uint16_t handle = t.ax;
        t.ax = t.bx;
        t.bx = handle;
    }
    *r = t;
    r->ax = keep.ax;
    r->dx = keep.dx;
    return 0;
}

/* orig 0000:F82B   read CX bytes from BX into DS:SI (DOS 3Fh): CX = bytes read; ZF when some
 * were (and with CX = 0 at once); CF on an error (kept, CX = 0) */
int dos_read(Game *g, const MachineServices *mc, CpuRegs *r)
{
    if (!r->cx) {
        flags(r, 0, 1);
        return 0;
    }
    CpuRegs keep = *r, t = *r;
    t.dx = r->si;
    t.ax = (uint16_t)(0x3F00 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    if (carry(&t)) {
        dos_store_error(g, t.ax);
        t.cx = 0;
        uint16_t ax = (uint16_t)(t.ax + 1);
        *r = t;
        flags(r, 1, ax == 0);
    } else {
        uint16_t got = t.ax;
        *r = t;
        r->cx = got;
        flags(r, 0, got != 0);
    }
    r->ax = keep.ax;
    r->dx = keep.dx;
    return 0;
}

/* orig 0000:F84D   write CX bytes from DS:SI to BX (DOS 40h): CX = bytes written; ZF when all
 * were; CF on an error (kept, CX = 0) */
int dos_write(Game *g, const MachineServices *mc, CpuRegs *r)
{
    if (!r->cx) {
        flags(r, 0, 1);
        return 0;
    }
    CpuRegs keep = *r, t = *r;
    t.dx = r->si;
    t.ax = (uint16_t)(0x4000 | (r->ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    if (carry(&t)) {
        dos_store_error(g, t.ax);
        t.cx = 0;
        uint16_t ax = (uint16_t)(t.ax + 1);
        *r = t;
        flags(r, 1, ax == 0);
    } else {
        uint16_t wrote = t.ax, wanted = keep.cx;
        *r = t;
        r->cx = wrote;
        flags(r, wanted < wrote, wanted == wrote);
    }
    r->ax = keep.ax;
    r->dx = keep.dx;
    return 0;
}

/* orig 0000:FACE   the file DS:DX read whole (up to FFFFh bytes) to ES:BX (DOS 3Dh, 3Fh,
 * 3Eh): AX = the bytes read, BX the handle, CX FFFFh, DX the offset; CF when the read
 * failed. A failed open returns with AX its code, the other registers as they were and CF
 * clear: the ADD SP,4 that drops the saved words sets the flags (the stack is not near
 * FFFFh). */
int dos_load_file(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t es = r->es, bx = r->bx;
    CpuRegs t = *r;
    t.ax = 0x3D00;
    if (dos(g, mc, &t) < 0)
        return -1;
    if (carry(&t)) {
        *r = t;
        r->flags &= (uint16_t)~FLAG_CF;
        return 0;
    }
    t.cx = 0xFFFF;
    t.bx = t.ax;
    t.dx = bx;
    t.ax = es;
    uint16_t ds = t.ds;
    t.ds = es;
    t.ax = (uint16_t)(0x3F00 | (t.ax & 0xFF));
    if (dos(g, mc, &t) < 0)
        return -1;
    t.ds = ds;
    if (!carry(&t)) {
        uint16_t got = t.ax;
        t.ax = (uint16_t)(0x3E00 | (got & 0xFF));
        if (dos(g, mc, &t) < 0)
            return -1;
        t.ax = got;
    }
    *r = t;
    return 0;
}

/* orig 11BC:10C6   close the handle BX (DOS 3Eh) */
int dos_close_handle(Game *g, const MachineServices *mc, CpuRegs *r)
{
    r->ax = (uint16_t)(0x3E00 | (r->ax & 0xFF));
    return dos(g, mc, r);
}

/* orig 11BC:10CB   read CX bytes from BX to DS:SI (DOS 3Fh), DX kept */
int dos_read_at_si(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint16_t dx = r->dx;
    r->dx = r->si;
    r->ax = (uint16_t)(0x3F00 | (r->ax & 0xFF));
    if (dos(g, mc, r) < 0)
        return -1;
    r->dx = dx;
    return 0;
}
