/* The routines that talk to the hardware, the BIOS and DOS directly, translated against the
 * machine interface (MachineServices: port in / out and software interrupts with a register
 * block). A host can implement that interface with emulated devices, or skip these
 * routines and serve the higher-level operations (MS_*, MM_*) itself. CLI / STI are not
 * modelled: the C runs without interrupts in between.
 */
#include "term.h"

static uint16_t port_in(Game *g, const MachineServices *mc, uint16_t port)
{
    return mc && mc->in ? mc->in(g, port, 1, mc->user) : 0xFF;
}

static void port_out(Game *g, const MachineServices *mc, uint16_t port, uint8_t value)
{
    if (mc && mc->out)
        mc->out(g, port, 1, value, mc->user);
}

int machine_interrupt(Game *g, const MachineServices *mc, uint8_t vector, CpuRegs *regs)
{
    return mc && mc->interrupt && !mc->interrupt(g, vector, regs, mc->user) ? 0 : -1;
}

static uint16_t bda_word(const Game *g, uint16_t at)
{
    return (uint16_t)(g->mem[0x400 + at] | g->mem[0x401 + at] << 8);
}

static uint16_t code_segment(const Game *g)
{
    return (uint16_t)(g->ds_seg - 0x5C27);
}

/* orig 0000:0D8D   until vertical retrace (the CRTC status port: BIOS 0:463 + 6, ADD DL,6) */
void retrace_wait_start(Game *g, const MachineServices *mc)
{
    uint16_t port = bda_word(g, 0x63);
    port = (uint16_t)((port & 0xFF00) | (uint8_t)(port + 6));
    while (!(port_in(g, mc, port) & 8))
        ;
}

/* orig 0000:0DAA   until vertical retrace is over */
void retrace_wait_end(Game *g, const MachineServices *mc)
{
    uint16_t port = bda_word(g, 0x63);
    port = (uint16_t)((port & 0xFF00) | (uint8_t)(port + 6));
    while (port_in(g, mc, port) & 8)
        ;
}

/* orig 5776:02C6 (with the thunks 0000:EF83 / EF87)   CX frames; CX = 0 means 65536 (LOOP) */
void pause_frames(Game *g, const MachineServices *mc, uint16_t frames)
{
    do {
        retrace_wait_start(g, mc);
        retrace_wait_end(g, mc);
    } while (--frames);
}

/* orig 0000:C571   the CRTC's start address (registers 0Ch, 0Dh) */
void crtc_display_start(Game *g, const MachineServices *mc, uint16_t start)
{
    port_out(g, mc, 0x3D4, 0x0C);
    port_out(g, mc, 0x3D5, (uint8_t)(start >> 8));
    port_out(g, mc, 0x3D4, 0x0D);
    port_out(g, mc, 0x3D5, (uint8_t)start);
}

/* orig 0000:0BE5   INT 10h with the caller's registers */
int bios_video_call(Game *g, const MachineServices *mc, CpuRegs *regs)
{
    return machine_interrupt(g, mc, 0x10, regs);
}

/* orig 0000:0BE8   the 16 EGA palette registers from DS:table (attribute controller), then
 * the display on again (20h); 7AAF passes DS:1521, 7AB6 DS:1510 */
void palette_registers(Game *g, const MachineServices *mc, uint16_t table)
{
    port_in(g, mc, (uint16_t)(bda_word(g, 0x63) + 6)); /* reset the flip-flop */
    for (uint8_t i = 0; i < 16; ++i) {
        port_out(g, mc, 0x3C0, i);
        port_out(g, mc, 0x3C0, DS_U8(g->ds, (uint16_t)(table + i)));
    }
    port_out(g, mc, 0x3C0, 0x20);
}

/* orig 0000:9FA4   INT 10h 1012h: the 256 DAC registers from ES:table */
int dac_block(Game *g, const MachineServices *mc, uint16_t table, uint16_t es)
{
    CpuRegs r = {0};
    r.ax = 0x1012;
    r.bx = 0;
    r.cx = 0x100;
    r.dx = table;
    r.ds = g->ds_seg;
    r.es = es;
    return machine_interrupt(g, mc, 0x10, &r);
}

/* orig 0000:F654   the BIOS tick count 0:46C */
uint32_t bios_ticks(const Game *g)
{
    return (uint32_t)bda_word(g, 0x6C) | (uint32_t)bda_word(g, 0x6E) << 16;
}

/* orig 0000:F008 / F01D   an interrupt vector (BX = its number, the address shifted as a word) */
void vector_set(Game *g, uint16_t number, uint16_t off, uint16_t seg)
{
    uint16_t at = (uint16_t)(number << 2);
    g->mem[at] = (uint8_t)off;
    g->mem[(uint16_t)(at + 1)] = (uint8_t)(off >> 8);
    g->mem[(uint16_t)(at + 2)] = (uint8_t)seg;
    g->mem[(uint16_t)(at + 3)] = (uint8_t)(seg >> 8);
}

uint32_t vector_get(const Game *g, uint16_t number)
{
    uint16_t at = (uint16_t)(number << 2);
    return (uint32_t)(g->mem[at] | g->mem[(uint16_t)(at + 1)] << 8)
           | (uint32_t)(g->mem[(uint16_t)(at + 2)] | g->mem[(uint16_t)(at + 3)] << 8) << 16;
}

/* orig 0000:03D1   the divide-error vector kept at DS:0202 and pointed at 0407 */
void divide_handler_install(Game *g)
{
    uint32_t old = vector_get(g, 0);
    DS_U16(g->ds, 0x0202) = (uint16_t)old;
    DS_U16(g->ds, 0x0204) = (uint16_t)(old >> 16);
    vector_set(g, 0, 0x0407, code_segment(g));
}

/* orig 0000:03F2 */
void divide_handler_remove(Game *g)
{
    vector_set(g, 0, DS_U16(g->ds, 0x0202), DS_U16(g->ds, 0x0204));
}

/* orig 0000:0407   the divide-error handler: the interrupted IP (at SS:SP on entry) + 2 */
void divide_error_resume(Game *g, uint16_t ss, uint16_t sp)
{
    uint8_t *ip = far_ptr(g, ss, 0);
    uint16_t value = (uint16_t)(ip[sp] | ip[(uint16_t)(sp + 1)] << 8);
    value = (uint16_t)(value + 2);
    ip[sp] = (uint8_t)value;
    ip[(uint16_t)(sp + 1)] = (uint8_t)(value >> 8);
}

/* orig 0000:3756   the shift flags 0:417 cleared, INT 9 once, the old vector kept at CS:3B83,
 * the keyboard interrupt pointed at 37E3 */
int keyboard_install(Game *g, const MachineServices *mc)
{
    g->mem[0x417] = 0;
    CpuRegs r = {0};
    r.ds = g->ds_seg;
    if (machine_interrupt(g, mc, 0x09, &r) < 0)
        return -1;
    r.ax = 0x3509;
    if (machine_interrupt(g, mc, 0x21, &r) < 0)
        return -1;
    uint8_t *code = far_ptr(g, code_segment(g), 0);
    code[0x3B83] = (uint8_t)r.bx;
    code[0x3B84] = (uint8_t)(r.bx >> 8);
    code[0x3B85] = (uint8_t)r.es;
    code[0x3B86] = (uint8_t)(r.es >> 8);
    r.ds = code_segment(g);
    r.dx = 0x37E3;
    r.ax = 0x2509;
    return machine_interrupt(g, mc, 0x21, &r);
}

/* orig 0000:3783   the old keyboard vector back */
int keyboard_remove(Game *g, const MachineServices *mc)
{
    const uint8_t *code = far_ptr(g, code_segment(g), 0);
    CpuRegs r = {0};
    r.dx = (uint16_t)(code[0x3B83] | code[0x3B84] << 8);
    r.ds = (uint16_t)(code[0x3B85] | code[0x3B86] << 8);
    r.ax = 0x2509;
    return machine_interrupt(g, mc, 0x21, &r);
}

/* orig 0000:3A12   1 when no joystick answers on port 201h within 6000 reads (the carry) */
int joystick_absent(Game *g, const MachineServices *mc)
{
    port_out(g, mc, 0x201, 0xFF);
    for (uint16_t n = 0;;) {
        if ((port_in(g, mc, 0x201) & 1) != 1)
            return 0;
        if (++n >= 0x1770)
            return 1;
    }
}

/* orig 0000:3A33   AL to port 201h, then count reads until both axis bits drop; the buttons
 * set Enter / Space. Returns AX (across) | BX (down) << 16. */
uint32_t joystick_read_port(Game *g, const MachineServices *mc, uint8_t al)
{
    port_out(g, mc, 0x201, al);
    uint16_t across = 0, down = 0;
    uint8_t value;
    for (;;) {
        value = (uint8_t)port_in(g, mc, 0x201);
        unsigned clear = 2;
        if (value & 1) {
            clear--;
            across++;
        }
        if (value & 2) {
            clear--;
            down++;
        }
        if (clear == 2)
            break;
    }
    if (!(value & 0x10))
        DS_U8(g->ds, KEY_DOWN(SC_ENTER)) = 0xFF;
    if (!(value & 0x20))
        DS_U8(g->ds, KEY_DOWN(SC_SPACE)) = 0xFF;
    return across | (uint32_t)down << 16;
}

static int ems(Game *g, const MachineServices *mc, CpuRegs *r, uint8_t function)
{
    r->ax = (uint16_t)(function << 8 | (r->ax & 0xFF));
    return machine_interrupt(g, mc, 0x67, r);
}

static int message(Game *g, const MachineServices *mc, CpuRegs *r, uint16_t text)
{
    r->dx = text;
    r->ax = (uint16_t)(0x0900 | (r->ax & 0xFF));
    return machine_interrupt(g, mc, 0x21, r);
}

/* orig 0000:5D52   EMS: the driver's name at the INT 67h segment:000A, version 3.0 or more, 4
 * free pages allocated (handle DS:7B80) and mapped, the page frame DS:7B84 (also 0208);
 * DS:7ABF set and message 7A52. Returns 1 (carry) without EMS (message 7A6B and 90 frames)
 * or when the mapping fails (the pages released). Registers carry over between the calls
 * as in the original (AL from the last result). */
int ems_setup(Game *g, const MachineServices *mc)
{
    uint8_t *ds = g->ds;
    CpuRegs r = {0};
    r.ax = 0x3567;
    r.ds = g->ds_seg;
    if (machine_interrupt(g, mc, 0x21, &r) < 0)
        return -1;
    const uint8_t *driver = far_ptr(g, r.es, 0);
    int named = 1;
    for (uint16_t i = 0; i < 8; ++i)
        if (DS_U8(ds, (uint16_t)(0x7AB7 + i)) != driver[(uint16_t)(0x0A + i)]) {
            named = 0;
            break;
        }
    int ok = named;
    if (ok) {
        if (ems(g, mc, &r, 0x40) < 0)
            return -1;
        ok = !(r.ax >> 8);
    }
    if (ok) {
        if (ems(g, mc, &r, 0x46) < 0)
            return -1;
        ok = !(r.ax >> 8) && (uint8_t)r.ax >= 0x30;
    }
    if (ok) {
        if (ems(g, mc, &r, 0x41) < 0)
            return -1;
        ok = !(r.ax >> 8);
        if (ok)
            DS_U16(ds, 0x7B84) = r.bx;
    }
    if (ok) {
        if (ems(g, mc, &r, 0x42) < 0)
            return -1;
        ok = !(r.ax >> 8) && r.bx >= 4;
    }
    if (ok) {
        r.bx = 4;
        if (ems(g, mc, &r, 0x43) < 0)
            return -1;
        ok = !(r.ax >> 8);
        if (ok)
            DS_U16(ds, 0x7B80) = r.dx;
    }
    if (!ok) { /* 5DFC */
        if (message(g, mc, &r, 0x7A6B) < 0)
            return -1;
        pause_frames(g, mc, 0x5A);
        return 1;
    }
    r.cx = 4;
    r.bx = 0;
    r.ax &= 0xFF00;
    do { /* LOOP */
        r.dx = DS_U16(ds, 0x7B80);
        CpuRegs saved = r;
        if (ems(g, mc, &r, 0x44) < 0)
            return -1;
        uint8_t status = (uint8_t)(r.ax >> 8);
        r.ax = saved.ax;
        r.bx = saved.bx;
        r.cx = saved.cx;
        if (status) { /* 5DF1 */
            r.dx = DS_U16(ds, 0x7B80);
            if (ems(g, mc, &r, 0x45) < 0)
                return -1;
            return 1;
        }
        r.ax = (uint16_t)((r.ax & 0xFF00) | (uint8_t)(r.ax + 1));
        r.bx++;
    } while (--r.cx);
    r.dx = DS_U16(ds, 0x7B80);
    if (ems(g, mc, &r, 0x47) < 0)
        return -1;
    r.dx = DS_U16(ds, 0x7B80);
    DS_U16(ds, 0x7B7E) = r.dx;
    if (ems(g, mc, &r, 0x48) < 0)
        return -1;
    r.ax = DS_U16(ds, 0x0208) = DS_U16(ds, 0x7B84); /* through AX, whose AL the message call keeps */
    DS_U8(ds, 0x7ABF) = 0xFF;
    return message(g, mc, &r, 0x7A52) < 0 ? -1 : 0;
}

/* orig 0000:5E0E   the EMS pages released */
int ems_release(Game *g, const MachineServices *mc)
{
    if (!DS_U8(g->ds, 0x7ABF))
        return 0;
    CpuRegs r = {0};
    r.dx = DS_U16(g->ds, 0x7B80);
    r.ax = 0x4500;
    return machine_interrupt(g, mc, 0x67, &r);
}

/* orig 0000:F4E5   the display adapter: AL = 4 VGA, 3 MCGA, 2 EGA, 1 CGA, 0 monochrome (AH as
 * the caller had it) */
int adapter_detect(Game *g, const MachineServices *mc, uint16_t ax, uint16_t *result)
{
    uint8_t code = 4;
    CpuRegs r = {0};
    r.ax = 0x1A00;
    r.es = 0;
    r.ds = g->ds_seg;
    if (machine_interrupt(g, mc, 0x10, &r) < 0)
        return -1;
    int ega = 1;
    if ((uint8_t)r.ax == 0x1A) {
        uint16_t t = r.ax; /* XCHG BX,AX: AL = the active display code */
        r.ax = r.bx;
        r.bx = t;
        uint8_t active = (uint8_t)r.ax;
        if (active == 8 || active == 7)
            ega = 0;
        else {
            code = 3;
            if (active >= 0x0A && active <= 0x0C)
                ega = 0;
        }
    }
    if (ega) {
        code = 2;
        r.ax = (uint16_t)(0x1200 | (uint8_t)r.ax);
        r.bx = (uint16_t)((r.bx & 0xFF00) | 0x10);
        if (machine_interrupt(g, mc, 0x10, &r) < 0)
            return -1;
        if ((uint8_t)r.bx >= 0x10) {
            code = 1;
            if (bda_word(g, 0x63) == 0x3B4)
                code = 0;
        }
    }
    *result = (uint16_t)((ax & 0xFF00) | code);
    return 0;
}
