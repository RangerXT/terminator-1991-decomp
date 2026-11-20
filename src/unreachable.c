/* The routines no path of the game reaches (tools/names.py: no reference anywhere in the
 * executable, or only from another such routine), translated for completeness, register for
 * register, each tested by a direct call (tests/test_unreachable.py). Where one calls a
 * routine whose C version returns less than the original leaves in the registers, the
 * comment says which registers are then not modelled. A divide error resumes after the
 * division with the registers as they were, as under the game's handler 0407.
 */
#include "term.h"

#define FLAG_CF 0x0001
#define FLAG_PF 0x0004
#define FLAG_AF 0x0010
#define FLAG_ZF 0x0040
#define FLAG_SF 0x0080
#define FLAG_OF 0x0800

static uint16_t code_segment(const Game *g)
{
    return (uint16_t)(g->ds_seg - 0x5C27);
}

/* the flags of CMP a,b at `bits` (8 or 16) */
static uint16_t cmp_flags(uint16_t flags, uint16_t a, uint16_t b, int bits)
{
    uint32_t mask = bits == 8 ? 0xFF : 0xFFFF, sign = bits == 8 ? 0x80 : 0x8000;
    a &= mask, b &= mask;
    uint32_t res = (a - b) & mask;
    unsigned ones = 0;
    for (uint8_t v = (uint8_t)res; v; v &= (uint8_t)(v - 1))
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
    if (res & sign)
        flags |= FLAG_SF;
    if ((a ^ b) & (a ^ res) & sign)
        flags |= FLAG_OF;
    return flags;
}

/* IDIV r16 on DX:AX: 0 on a divide error (nothing changes) */
static int idiv16(uint16_t *ax, uint16_t *dx, uint16_t divisor)
{
    if (!divisor)
        return 0;
    int64_t n = (int32_t)((uint32_t)*dx << 16 | *ax), d = (int16_t)divisor;
    int64_t q = n / d, rem = n % d;
    if (q < -32768 || q > 32767)
        return 0;
    *ax = (uint16_t)q;
    *dx = (uint16_t)rem;
    return 1;
}

/* orig 0000:1814   BL = bit 0 of the byte at DS:111B + the draw page in planes 3..0 (the
 * read map, GC 4), then CMP BL,AL */
void unused_plane_bits(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t si = (uint16_t)(0x111B + DS_U16(ds, DS_DRAW_PAGE)), seg = DS_U16(ds, 0xADDC);
    uint8_t bl = 0, plane = 3;
    for (int i = 0; i < 4; ++i, --plane) {
        ega_gc(g->planes, 4, plane);
        uint8_t al = seg == 0xA000 ? ega_load(g->planes, si) : *far_ptr(g, seg, si);
        bl = (uint8_t)(bl + bl + (al & 1));
    }
    r->bx = (uint16_t)((r->bx & 0xFF00) | bl);
    r->cx = 0;
    r->dx = 0x3CE;
    r->si = si;
    r->flags = cmp_flags(r->flags, bl, (uint8_t)r->ax, 8);
}

/* orig 0000:2707   CF when every vertex of the face at SI + 4 (a count, then offsets into
 * the vertex buffer BX) has z (+ 4) negative */
static int face_behind(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    r->si = (uint16_t)(r->si + 4);
    uint16_t cx = DS_U16(ds, r->si);
    r->si = (uint16_t)(r->si + 2);
    do { /* LOOP: a count of 0 is 65536 */
        r->ax = DS_U16(ds, r->si);
        r->si = (uint16_t)(r->si + 2);
        if (!(DS_U16(ds, (uint16_t)(r->bx + r->ax + 4)) & 0x8000)) {
            r->cx = cx;
            return 0;
        }
    } while (--cx);
    r->cx = 0;
    return 1;
}

/* orig 0000:26DF   for each face of the model BX (count + 2, list + 6): its byte at
 * DS:[40E0] + n raised by one when it is wholly behind (2707) */
void unused_faces_behind(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t bx = r->bx, cx = DS_U16(ds, (uint16_t)(bx + 2)), si = DS_U16(ds, (uint16_t)(bx + 6));
    r->bx = DS_U16(ds, 0x3CDC);
    r->di = DS_U16(ds, 0x40E0);
    do {
        r->si = si;
        int cf = face_behind(g, r);
        DS_U8(ds, r->di) = (uint8_t)(DS_U8(ds, r->di) + cf);
        r->di = (uint16_t)(r->di + 1);
        r->ax = (uint16_t)(DS_U16(ds, (uint16_t)(si + 4)) * 2 + 6);
        si = (uint16_t)(si + r->ax);
    } while (--cx);
    r->si = si;
    r->cx = 0;
    r->bx = bx;
}

/* orig 0000:296A   the camera moved by the heading of DS:[DI + 6]: x += FED4h * sine >> 16,
 * z += 12Ch * cosine >> 16 (tables DS:4188, 4288) */
void unused_camera_offset(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t bx = (uint16_t)(DS_U16(ds, (uint16_t)(r->di + 6)) * 2);
    int32_t p = (int32_t)(int16_t)0xFED4 * DS_I16(ds, (uint16_t)(bx + 0x4188));
    DS_U16(ds, 0x57BE) = (uint16_t)(DS_U16(ds, 0x57BE) + (uint16_t)((uint32_t)p >> 16));
    int32_t q = 0x12C * (int32_t)DS_I16(ds, (uint16_t)(bx + 0x4288));
    DS_U16(ds, 0x57C2) = (uint16_t)(DS_U16(ds, 0x57C2) + (uint16_t)((uint32_t)q >> 16));
    r->ax = (uint16_t)q;
    r->dx = (uint16_t)((uint32_t)q >> 16);
    r->bx = bx;
}

/* orig 0000:43B9   no extras (DS:04C6), DS:1204 = DS:1200 */
void unused_extras_clear(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0x04C6) = 0;
    r->ax = DS_U16(ds, 0x1200);
    DS_U16(ds, 0x1204) = r->ax;
}

/* CWD; MOV DL,AH; MOV AH,AL: DX:AX = AX * 256 with the low byte repeated */
static void widen(uint16_t *ax, uint16_t *dx)
{
    uint16_t sign = *ax & 0x8000 ? 0xFF00 : 0;
    *dx = (uint16_t)(sign | *ax >> 8);
    *ax = (uint16_t)((*ax & 0xFF) << 8 | (*ax & 0xFF));
}

/* orig 0000:47A8   AX and BX divided by CX after widening (IDIV), times 8 when CX >= 64h */
void unused_scale_down(Game *g, CpuRegs *r)
{
    uint16_t ax = r->ax, dx = r->dx;
    widen(&ax, &dx);
    idiv16(&ax, &dx, r->cx);
    uint16_t first = ax;
    ax = r->bx;
    widen(&ax, &dx);
    idiv16(&ax, &dx, r->cx);
    uint16_t bx = ax;
    ax = first;
    if (r->cx >= 0x64) {
        ax = (uint16_t)(ax << 3);
        bx = (uint16_t)(bx << 3);
    }
    r->ax = ax;
    r->bx = bx;
    r->dx = dx;
}

/* orig 0000:47CE   a perspective step: AX, BX times 4, CX negated; each v becomes
 * v + (-v * CX) / (CX - 1Eh) (IMUL, IDIV), AX the first, BX the second */
void unused_project(Game *g, CpuRegs *r)
{
    uint16_t ax = (uint16_t)(r->ax << 2), bx = (uint16_t)(r->bx << 2), cx = (uint16_t)-r->cx, dx = r->dx;
    for (int pass = 0; pass < 2; ++pass) {
        uint16_t keep_bx = bx, keep_ax = ax;
        int32_t p = (int32_t)(int16_t)(uint16_t)-ax * (int16_t)cx;
        ax = (uint16_t)p;
        dx = (uint16_t)((uint32_t)p >> 16);
        idiv16(&ax, &dx, (uint16_t)(0xFFE2 + cx));
        dx = keep_ax;
        ax = (uint16_t)(ax + dx);
        bx = keep_bx;
        uint16_t t = ax; /* XCHG BX,AX */
        ax = bx;
        bx = t;
    }
    r->ax = ax;
    r->bx = bx;
    r->cx = cx;
    r->dx = dx;
}

/* orig 0000:47FD   AX and BX times 128 (widened, SAR / RCR) divided by CX: AX the first */
void unused_scale_half(Game *g, CpuRegs *r)
{
    uint16_t ax = r->ax, bx = r->bx, dx = r->dx;
    for (int pass = 0; pass < 2; ++pass) {
        widen(&ax, &dx);
        ax &= 0xFF00; /* XOR AL,AL */
        uint32_t v = (uint32_t)((int32_t)((uint32_t)dx << 16 | ax) >> 1);
        ax = (uint16_t)v;
        dx = (uint16_t)(v >> 16);
        idiv16(&ax, &dx, r->cx);
        uint16_t t = ax; /* XCHG BX,AX */
        ax = bx;
        bx = t;
    }
    r->ax = ax;
    r->bx = bx;
    r->dx = dx;
}

/* orig 0000:481A (inside 47FD's bytes)   a divide-error handler of another kind: the
 * division skipped (the frame's IP at SS:SP + 2), AX = 7E6Fh XOR the sign of DL */
void unused_divide_handler(Game *g, uint16_t ss, uint16_t sp, CpuRegs *r)
{
    uint8_t *frame = far_ptr(g, ss, sp);
    uint16_t ip = (uint16_t)((frame[0] | frame[1] << 8) + 2);
    frame[0] = (uint8_t)ip;
    frame[1] = (uint8_t)(ip >> 8);
    uint16_t dx = (r->dx & 0x80) ? 0xFFFF : 0; /* MOV AH,DL; CWD */
    r->dx = dx;
    r->ax = (uint16_t)(0x7E6F ^ dx);
}

/* orig 0000:5622 (and its far thunk EF77)   the item of kind DS:[AX + 78DC] dropped in the
 * world: found in the list DS:A38E (kind, weight, category; FFh ends: nothing), built at
 * DS:51FD (name DS:[2 AX + 78EC], count 1) and dropped as 565B does */
void unused_drop_kind(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t bx = r->ax;
    uint8_t dl = DS_U8(ds, (uint16_t)(bx + 0x78DC)), al;
    r->dx = (uint16_t)((r->dx & 0xFF00) | dl);
    uint16_t si = 0xA38E;
    for (;;) {
        al = DS_U8(ds, si);
        si = (uint16_t)(si + 1);
        if (al == dl)
            break;
        if (al & 0x80) {
            r->ax = (uint16_t)((r->ax & 0xFF00) | al);
            r->bx = bx;
            r->si = si;
            return;
        }
        si = (uint16_t)(si + 3);
    }
    bx = DS_U16(ds, (uint16_t)(bx * 2 + 0x78EC));
    uint16_t di = 0x51FD;
    DS_U16(ds, di) = bx;
    DS_U8(ds, (uint16_t)(di + 2)) = al;
    DS_U8(ds, (uint16_t)(di + 3)) = DS_U8(ds, si);
    DS_U8(ds, (uint16_t)(di + 4)) = DS_U8(ds, (uint16_t)(si + 1));
    DS_U8(ds, (uint16_t)(di + 5)) = 1;
    /* 565B */
    DS_U16(ds, 0x116C) = (uint16_t)(DS_U16(ds, 0x116C) - (uint16_t)(int16_t)(int8_t)DS_U8(ds, (uint16_t)(di + 3)));
    uint16_t cx = DS_U16(ds, 0x03FC);
    uint16_t to = (uint16_t)(0x0253 + (uint16_t)(0x0D * (uint8_t)cx));
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, to) = DS_U16(ds, (uint16_t)(player + 0x1E));
    DS_U16(ds, (uint16_t)(to + 2)) = DS_U16(ds, (uint16_t)(player + 0x20));
    DS_U16(ds, (uint16_t)(to + 4)) = DS_U16(ds, player);
    DS_U16(ds, (uint16_t)(to + 6)) = DS_U16(ds, (uint16_t)(player + 4));
    DS_U16(ds, (uint16_t)(to + 8)) = DS_U16(ds, di);
    DS_U8(ds, (uint16_t)(to + 0x0A)) = DS_U8(ds, (uint16_t)(di + 2));
    DS_U8(ds, (uint16_t)(to + 0x0B)) = DS_U8(ds, (uint16_t)(di + 3));
    DS_U8(ds, (uint16_t)(to + 0x0C)) = DS_U8(ds, (uint16_t)(di + 4));
    cx = cx == 0x13 ? 0 : (uint16_t)(cx + 1);
    DS_U16(ds, 0x03FC) = cx;
    r->ax = (uint16_t)(DS_U8(ds, (uint16_t)(di + 3)) << 8 | DS_U8(ds, (uint16_t)(di + 4)));
    r->bx = player;
    r->cx = cx;
    r->si = si;
    r->di = di;
}

/* orig 0000:5A6F   a far wrapper of bytekiller_unpack (B425): DS:SI the block, CX its size,
 * ES:DI the output; AX = 0, or FFFFh on a bad check. BX, CX, DX as B425 leaves them are not
 * modelled. */
void unused_unpack_far(Game *g, CpuRegs *r)
{
    int bad = bytekiller_unpack(far_ptr(g, r->ds, r->si), r->cx, far_ptr(g, r->es, r->di));
    r->ax = bad ? 0xFFFF : 0;
}

/* orig 0000:6479   the four marks at DS:7D08 .. 7D0E: each set one takes its byte of the
 * player (+ 11h ..) back off the word + 2Bh, and is cleared with it */
void unused_marks_undo(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t si = (uint16_t)(DS_U16(ds, DS_PLAYER) + 0x11);
    for (uint16_t i = 0; i < 4; ++i) {
        uint16_t mark = (uint16_t)(0x7D08 + 2 * i);
        if (!DS_U16(ds, mark))
            continue;
        r->ax = (uint16_t)(int16_t)(int8_t)DS_U8(ds, (uint16_t)(si + i));
        DS_U16(ds, (uint16_t)(si + 0x1A)) = (uint16_t)(DS_U16(ds, (uint16_t)(si + 0x1A)) - r->ax);
        DS_U8(ds, (uint16_t)(si + i)) = 0;
        DS_U16(ds, mark) = 0;
    }
    r->si = si;
}

/* orig 0000:79F1   the model BX's vertices (count + 4) at DS:[3CDC] turned by the angles
 * AX, BX, CX (matrix_from_angles), y + 6Eh, z + 320h after, in place; DS:4B6E set when a z
 * is negative. DX as matrix_apply leaves it is not modelled. */
void unused_model_turn(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t model = r->bx;
    matrix_from_angles(ds, r->ax, r->bx, r->cx);
    uint16_t cx = DS_U16(ds, (uint16_t)(model + 4)), si = DS_U16(ds, 0x3CDC), di = si;
    do {
        int16_t x = DS_I16(ds, si), y = DS_I16(ds, (uint16_t)(si + 2)), z = DS_I16(ds, (uint16_t)(si + 4));
        si = (uint16_t)(si + 6);
        y = (int16_t)(y + 0x6E);
        matrix_apply(ds, &x, &y, &z);
        z = (int16_t)(z + 0x320);
        DS_U16(ds, di) = (uint16_t)x;
        DS_U16(ds, (uint16_t)(di + 2)) = (uint16_t)y;
        DS_U16(ds, (uint16_t)(di + 4)) = (uint16_t)z;
        di = (uint16_t)(di + 6);
        if (z < 0)
            DS_U8(ds, 0x4B6E) = 1;
        r->ax = (uint16_t)z;
    } while (--cx);
    r->cx = 0;
    r->bx = model;
    r->si = si;
    r->di = di;
}

/* orig 0000:87E2   DS:11C4 += 50h, CF clear */
void unused_add_50(Game *g, CpuRegs *r)
{
    DS_U16(g->ds, 0x11C4) = (uint16_t)(DS_U16(g->ds, 0x11C4) + 0x50);
    r->flags &= (uint16_t)~FLAG_CF;
}

/* orig 0000:5EEE at the register level: AX the distance, BX the larger difference */
static void distance(CpuRegs *r)
{
    uint16_t ax = (uint16_t)(r->ax - r->cx), bx = (uint16_t)(r->bx - r->dx);
    if (ax & 0x8000)
        ax = (uint16_t)-ax;
    if (bx & 0x8000)
        bx = (uint16_t)-bx;
    if (ax >= bx) {
        uint16_t t = ax;
        ax = bx;
        bx = t;
    }
    r->ax = (uint16_t)((ax >> 2) + bx);
    r->bx = bx;
}

/* orig 0000:950D   the decoy's flicker (DS:AAD0, a countdown AACF and a random nudge of the
 * view centre DS:040A) and its record DS:0B10: while its time runs, a player on foot near it
 * (under C8h) sets the flicker off once; a vehicle far from it is stopped (speed 4, state 1) */
void unused_decoy_step(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0xAAD0)) {
        DS_U8(ds, 0xAACF)--;
        if (!DS_U8(ds, 0xAACF)) {
            r->ax = random_word(ds) & 0x0F;
            DS_U8(ds, 0xAACF) = (uint8_t)r->ax;
            r->ax = (uint16_t)((int16_t)(int8_t)(uint8_t)random_word(ds) >> 5); /* CBW, SAR x5 */
            r->ax = (uint16_t)(r->ax + 3);
            DS_U16(ds, 0x040A) = (uint16_t)(DS_U16(ds, 0x040A) + r->ax);
        }
    }
    uint16_t di = 0x0B10;
    r->di = di;
    if (!DS_U16(ds, (uint16_t)(di + 6)))
        return;
    DS_U16(ds, (uint16_t)(di + 6))--;
    uint16_t si = DS_U16(ds, DS_PLAYER);
    r->ax = DS_U16(ds, si);
    r->bx = DS_U16(ds, (uint16_t)(si + 4));
    r->cx = DS_U16(ds, di);
    r->dx = DS_U16(ds, (uint16_t)(di + 2));
    distance(r);
    if (r->ax >= 0xC8)
        DS_U8(ds, 0xAAD1) = 0;
    else if (!DS_U8(ds, 0xAAD1) && (DS_U8(ds, (uint16_t)(si + 0x0E)) & 2)) {
        DS_U8(ds, 0xAACF) = 1;
        DS_U8(ds, 0xAAD0) = 0xFF;
        DS_U8(ds, 0xAAD1) = 0;
    }
    si = DS_U16(ds, DS_VEHICLE);
    r->ax = DS_U16(ds, si);
    r->bx = DS_U16(ds, (uint16_t)(si + 4));
    r->cx = DS_U16(ds, di);
    r->dx = DS_U16(ds, (uint16_t)(di + 2));
    distance(r);
    r->si = si;
    if (r->ax >= 0xC8 && (DS_U8(ds, (uint16_t)(si + 0x0E)) & 2)) {
        DS_U16(ds, (uint16_t)(si + 0x0A)) = 4;
        DS_U16(ds, (uint16_t)(si + 0x0C)) = 4;
        DS_U8(ds, (uint16_t)(si + 0x0E)) = 1;
    }
}

/* orig 0000:B9C6   the timer vector back from DS:DE48 (DOS 25h, AL 8) */
int unused_timer_restore(Game *g, const MachineServices *mc, CpuRegs *r)
{
    CpuRegs t = *r;
    t.dx = DS_U16(g->ds, 0xDE48);
    t.ds = DS_U16(g->ds, 0xDE4A);
    t.ax = 0x2508;
    if (machine_interrupt(g, mc, 0x21, &t) < 0)
        return -1;
    t.ds = r->ds;
    *r = t;
    return 0;
}

/* orig 0000:CA39   the counter DS:E192 + 2 [E190] raised */
void unused_count_up(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t at = (uint16_t)(0xE192 + 2 * DS_U16(ds, 0xE190));
    DS_U16(ds, at) = (uint16_t)(DS_U16(ds, at) + 1);
}

/* orig 0000:EE0C   the copy protection's failure: when one of the ten words DS:E6E0 is the
 * answer's (DS:E6F6 + 2 [EA34]), text mode, the message DS:E6B1 (DOS 9) and the machine
 * hangs (JMP $): 1; else 0 */
int unused_protection_fail(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    for (uint16_t cx = 0x0A; cx; --cx) {
        r->ax = DS_U16(ds, (uint16_t)(0xE6E0 + 2 * (cx - 1)));
        r->bx = (uint16_t)(DS_U16(ds, 0xEA34) * 2);
        if (r->ax == DS_U16(ds, (uint16_t)(0xE6F6 + r->bx))) {
            r->cx = cx;
            r->ax = 3;
            if (machine_interrupt(g, mc, 0x10, r) < 0)
                return -1;
            r->ax = (uint16_t)(0x0900 | (r->ax & 0xFF));
            r->dx = 0xE6B1;
            return machine_interrupt(g, mc, 0x21, r) < 0 ? -1 : 1;
        }
    }
    r->cx = 0;
    return 0;
}

/* orig 0000:F54C at the register level: the number at DS:SI in base BL: AX its value, SI on
 * the first character that is no digit, the flags of CMP DI,1 (DI: 1 digits, 2 an overflow) */
static void number_parse(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t bx = (uint8_t)r->bx, cx = 0, di = 0;
    for (;;) {
        uint8_t al = DS_U8(ds, r->si);
        r->si = (uint16_t)(r->si + 1);
        if (al < '0')
            break;
        if (al > '9') {
            if (al < 'A')
                break;
            al = (uint8_t)((al & 0xDF) - 7);
        }
        al = (uint8_t)(al - '0');
        if ((uint8_t)bx <= al)
            break;
        uint32_t product = (uint32_t)cx * bx;
        cx = al;
        if (product > 0xFFFF) {
            di |= 2;
            continue;
        }
        uint32_t sum = (uint32_t)cx + (uint16_t)product;
        cx = (uint16_t)sum;
        di |= sum > 0xFFFF ? 2 : 1;
    }
    r->si = (uint16_t)(r->si - 1);
    r->flags = cmp_flags(r->flags, di, 1, 16);
    r->ax = cx;
}

/* orig 0000:F5CD   the decimal number at DS:SI (F54C with BL = 10), BX kept */
void unused_parse_decimal(Game *g, CpuRegs *r)
{
    uint16_t bx = r->bx;
    r->bx = (uint16_t)((r->bx & 0xFF00) | 0x0A);
    number_parse(g, r);
    r->bx = bx;
}

/* orig 0000:FA10   the argument scanner back at the start of the tail */
void unused_args_restart(Game *g, CpuRegs *r)
{
    DS_U16(g->ds, 0xEA6C) = DS_U16(g->ds, 0xEA68);
}

/* orig 0000:FA88   AX in decimal, ending before DS:BX + 5 (a NUL there): BX = its first
 * digit; AX 0 after */
void unused_decimal_backwards(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t bx = (uint16_t)(r->bx + 5), ax = r->ax;
    DS_U8(ds, bx) = 0;
    if (!ax) {
        bx--;
        DS_U8(ds, bx) = '0';
    } else
        do {
            uint8_t digit = (uint8_t)(ax % 10);
            ax = (uint16_t)(ax / 10);
            bx--;
            DS_U8(ds, bx) = (uint8_t)('0' + digit);
        } while (ax);
    r->ax = ax;
    r->bx = bx;
}

/* orig 11BC:110E   AX = the byte DS:[5DC0 + AL] (XLAT) */
void unused_translate(Game *g, CpuRegs *r)
{
    r->ax = DS_U8(g->ds, (uint16_t)(0x5DC0 + (uint8_t)r->ax));
}

/* orig 11BC:1B27   three characters DS:SI in the 8x8 font (DS:7C30, rows 12 bytes apart) in
 * the fill colour at the text cell DI (40 a row: DIV CL) of the mode-13h screen */
void unused_text3_vga(Game *g, uint8_t *screen, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    uint16_t ax = r->di;
    if (ax / 0x28 <= 0xFF) /* DIV CL; an overflow resumes after it */
        ax = (uint16_t)((ax % 0x28) << 8 | (ax / 0x28));
    uint16_t cx = ax;
    ax &= 0xFF;
    uint32_t p = (uint32_t)ax * 0x140;
    uint16_t dx = (uint16_t)(p >> 16);
    ax = (uint16_t)p;
    cx = (uint16_t)((cx >> 8) * 8);
    uint16_t di = (uint16_t)(ax + cx), es = DS_U16(ds, 0xADDC), si = r->si;
    uint8_t colour = DS_U8(ds, 0x468C);
    for (int c = 0; c < 3; ++c) {
        uint16_t font = (uint16_t)(0x7C30 + DS_U8(ds, si));
        si = (uint16_t)(si + 1);
        uint16_t at = di;
        for (int row = 0; row < 8; ++row) {
            uint8_t bits = DS_U8(ds, font);
            font = (uint16_t)(font + 1 + 0x0B);
            for (int b = 0; b < 8; ++b, at = (uint16_t)(at + 1), bits = (uint8_t)(bits << 1))
                if (bits & 0x80) {
                    if (es == 0xA000 && screen)
                        screen[at] = colour;
                    else
                        *far_ptr(g, es, at) = colour;
                }
            at = (uint16_t)(at + 0x138);
        }
        di = (uint16_t)(di + 8);
    }
    r->ax = 0;
    r->cx = 0;
    r->dx = (uint16_t)((dx & 0xFF00) | colour);
    r->si = si;
    r->di = di;
    r->es = es;
}

/* orig 11BC:1E95   the weapon icon CX redrawn: the GC bit mask FFh, the icon buffer
 * (segment 19BA:13B0) cleared (3Ch words FFFFh, BAh words 0), the icon of the slot (DS:8104)
 * at 1C20h + its place, then with DS:1150 or 0366 set, DS:80A9 cleared. AX kept, CX - 1;
 * DX, SI, DI as hud_weapon_icon leaves them are not modelled. */
void unused_weapon_icon_redraw(Game *g, CpuRegs *r)
{
    uint8_t *ds = g->ds;
    ega_gc(g->planes, 8, 0xFF);
    uint16_t es = (uint16_t)(code_segment(g) + 0x19BA);
    for (uint16_t i = 0; i < 0x3C + 0xBA; ++i) {
        uint16_t v = i < 0x3C ? 0xFFFF : 0;
        *far_ptr(g, es, (uint16_t)(0x13B0 + 2 * i)) = (uint8_t)v;
        *far_ptr(g, es, (uint16_t)(0x13B1 + 2 * i)) = (uint8_t)(v >> 8);
    }
    uint16_t slot = (uint16_t)(r->cx - 1);
    uint16_t di = (uint16_t)(0x1C20 + DS_U16(ds, (uint16_t)(0x8104 + 2 * slot)));
    hud_weapon_icon(g, di, 0xFFFF);
    r->bx = 0x570;
    if (DS_U8(ds, 0x1150) || DS_U8(ds, 0x0366)) {
        r->bx = 0x12;
        DS_U8(ds, 0x80A9) = 0;
    }
    r->cx = slot;
}
