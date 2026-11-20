/* Figure position selection and spawning, translated from 0000:A840 onward. */
#include "term.h"

/* A987. The byte-sized MUL in the block-row term is intentional. */
static uint16_t grid_address(const uint8_t *ds)
{
    uint16_t row = DS_U16(ds, 0xB81C);
    return (uint16_t)(0xB740 + (row & 3) * 36 + (uint8_t)(row >> 2) * 12 + DS_U16(ds, 0xB818));
}

/* AA3B. The source subtracts one from the address BEFORE unpacking it. */
void figure_grid_to_world(uint8_t *ds, uint16_t address)
{
    int16_t offset = (uint16_t)(address - 1 - 0xB740);
    uint16_t row = 0;
    while (offset >= 36) {
        offset -= 36;
        row++;
    }
    while (offset >= 12) {
        offset -= 12;
        row += 4;
    }
    row++;
    uint16_t x = (uint16_t)(((uint8_t)offset << 8) + 256 - 0x0380);
    uint16_t z = (uint16_t)(-(uint16_t)((uint8_t)row << 8) + 256 + 0x0780);
    DS_U16(ds, DS_POINT_X) = x;
    DS_U16(ds, DS_POINT_Z) = z;
}

/* A9B4. 9136/9138 are grid indices here, even though the other inputs are world units. */
static void consider(uint8_t *ds, uint16_t address, uint16_t *dx)
{
    DS_U8(ds, 0xB734)++;
    uint16_t old_x = DS_U16(ds, DS_POINT_X), old_z = DS_U16(ds, DS_POINT_Z);
    figure_grid_to_world(ds, address);
    *dx = DS_U16(ds, DS_STAMP_Z);
    uint16_t distance =
        approx_distance(DS_I16(ds, DS_POINT_X), DS_I16(ds, DS_POINT_Z), DS_I16(ds, DS_STAMP_X), DS_I16(ds, DS_STAMP_Z));
    DS_U16(ds, DS_POINT_X) = old_x;
    DS_U16(ds, DS_POINT_Z) = old_z;
    if (DS_U16(ds, 0xB822) < distance)
        return;
    DS_U16(ds, 0xB822) = distance;
    figure_grid_to_world(ds, address);
    DS_U8(ds, 0x7A18) = 255;
}

/* A840. Return original carry: 1 means no position, 0 means accepted.
 * random_start corresponds to nonzero SI, wanted to BP (only its low byte is tested). */
static uint8_t select_position(uint8_t *ds, uint16_t random_start, uint16_t wanted, uint16_t *dx)
{
    if (!random_start
        && (DS_I16(ds, DS_PEN_X) < -1024 || DS_I16(ds, DS_PEN_X) > 2048 || DS_I16(ds, DS_PROBE_Z) < -1024
            || DS_I16(ds, DS_PROBE_Z) > 2048))
        return 1;
    if (random_start) {
        uint16_t r = random_word(ds), index = (r & 7) + ((r >> 15) & 1);
        DS_U16(ds, DS_PEN_X) = DS_U16(ds, 0xB7F4 + index * 4);
        DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, 0xB7F6 + index * 4);
    }
    DS_U8(ds, 0xB734) = 0;
    DS_U8(ds, 0xB736) = 255;
    DS_U8(ds, 0x7A18) = 0;
    DS_U16(ds, 0xB822) = 65535;
    uint16_t row = (uint16_t)(8 - (int8_t)(DS_U16(ds, DS_PROBE_Z) >> 8));
    uint16_t col = (uint16_t)(4 + (int8_t)(DS_U16(ds, DS_PEN_X) >> 8));
    DS_U16(ds, DS_STAMP_Z) = DS_U16(ds, 0xB81C) = DS_U16(ds, 0xB81E) = row;
    DS_U16(ds, DS_STAMP_X) = DS_U16(ds, 0xB818) = DS_U16(ds, 0xB81A) = col;
    uint16_t address = grid_address(ds);
    figure_grid_to_world(ds, address);
    if (!DS_U8(ds, 0xB735) && DS_U8(ds, address) == (uint8_t)wanted)
        return 0;
    for (;;) {
        unsigned changed = 0;
        if (DS_U16(ds, 0xB818)) {
            DS_U16(ds, 0xB818)--;
            changed++;
        }
        if (DS_U16(ds, 0xB81A) != 12) {
            DS_U16(ds, 0xB81A)++;
            changed++;
        }
        if (DS_U16(ds, 0xB81C)) {
            DS_U16(ds, 0xB81C)--;
            changed++;
        }
        if (DS_U16(ds, 0xB81E) != 12) {
            DS_U16(ds, 0xB81E)++;
            changed++;
        }
        if (!changed)
            return 1;
        uint16_t first = DS_U16(ds, 0xB818);
        uint16_t n = DS_U16(ds, 0xB81A) - first + 1;
        do {
            address = grid_address(ds);
            if (DS_U8(ds, address) == (uint8_t)wanted)
                consider(ds, address, dx);
            else {
                uint16_t top = DS_U16(ds, 0xB81C);
                DS_U16(ds, 0xB81C) = DS_U16(ds, 0xB81E);
                address = grid_address(ds);
                DS_U16(ds, 0xB81C) = top;
                if (DS_U8(ds, address) == (uint8_t)wanted)
                    consider(ds, address, dx);
            }
            DS_U16(ds, 0xB818)++;
        } while (--n);
        DS_U16(ds, 0xB818) = first;
        n = DS_U16(ds, 0xB81E) - DS_U16(ds, 0xB81C);
        if (n != 1)
            n--;
        first = DS_U16(ds, 0xB81C);
        DS_U16(ds, 0xB81C)++;
        do {
            address = grid_address(ds);
            if (DS_U8(ds, address) == (uint8_t)wanted)
                consider(ds, address, dx);
            else {
                uint16_t left = DS_U16(ds, 0xB818);
                DS_U16(ds, 0xB818) = DS_U16(ds, 0xB81A);
                address = grid_address(ds);
                DS_U16(ds, 0xB818) = left;
                if (DS_U8(ds, address) == (uint8_t)wanted)
                    consider(ds, address, dx);
            }
            DS_U16(ds, 0xB81C)++;
        } while (--n);
        DS_U16(ds, 0xB81C) = first;
        DS_U8(ds, 0xB736) = 0;
        if (DS_U8(ds, 0x7A18))
            return 0;
    }
}

uint8_t figure_select_position(uint8_t *ds, uint16_t random_start, uint16_t wanted)
{
    uint16_t dx = 0;
    return select_position(ds, random_start, wanted, &dx);
}

/* B05E: initialize one figure's movement/animation state. */
static uint8_t init_movement(uint8_t *ds, uint16_t figure, uint16_t record, uint16_t *dx)
{
    uint8_t delay = DS_U16(ds, figure + 10) == 3 ? 3 : 2;
    DS_U8(ds, figure + 16) = DS_U8(ds, figure + 17) = delay;
    DS_U16(ds, figure + 18) = 0;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, record);
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, record + 4);
    uint8_t carry = select_position(ds, 0, 0, dx);
    if (!carry) {
        DS_U16(ds, figure + 2) = DS_U16(ds, DS_POINT_X);
        DS_U16(ds, figure + 4) = DS_U16(ds, DS_POINT_Z);
        int16_t diff_x = (uint16_t)(DS_U16(ds, record) - DS_U16(ds, DS_POINT_X));
        int16_t diff_z = (uint16_t)(DS_U16(ds, record + 4) - DS_U16(ds, DS_POINT_Z));
        uint16_t ux = diff_x < 0 ? -diff_x : diff_x, uz = diff_z < 0 ? -diff_z : diff_z;
        uint16_t small = ux < uz ? ux : uz, large = ux < uz ? uz : ux;
        *dx = (uint16_t)(((uint32_t)small * 64) % (large ? large : 1));
        DS_U16(ds, figure + 6) = angle_between(ds, DS_I16(ds, record), DS_I16(ds, record + 4), DS_I16(ds, DS_POINT_X),
                                               DS_I16(ds, DS_POINT_Z));
    }
    return carry;
}

uint8_t figure_init_movement(uint8_t *ds, uint16_t figure, uint16_t record)
{
    uint16_t dx = 0;
    return init_movement(ds, figure, record, &dx);
}

/* B0A6 / B0D7 / B13D. Figure animation lives in the 22-byte record itself;
 * companion animation in framelist.c uses a different record layout. */
void figure_select_frames(uint8_t *ds)
{
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT);
    for (uint16_t i = 0; i < count; ++i) {
        uint16_t figure = (uint16_t)(0x0B30 + i * 22);
        uint8_t flags = DS_U8(ds, figure);
        uint16_t pose = (8 - (((DS_U16(ds, figure + 14) - DS_U16(ds, figure + 6)) & 511) >> 6)) & 7;
        uint16_t table = flags & 2 ? 0xB830 : 0xB880;
        uint8_t armed = !(flags & 6);
        if (armed) {
            table = 0xB8D0;
            if (pose > 2)
                pose = pose >= 6 ? pose - 3 : DS_U8(ds, 0xB69A + pose - 3);
        }
        uint16_t offset = pose * 2;
        if (DS_U16(ds, figure + 10)) {
            offset = offset * 4 + (armed ? 10 : 16);
            if (!--DS_U8(ds, figure + 16)) {
                DS_U8(ds, figure + 16) = DS_U8(ds, figure + 17);
                uint16_t step = DS_U16(ds, figure + 18) + 2;
                DS_U16(ds, figure + 18) = armed ? (step & 0xFF07) : (step & 7);
            }
            offset += DS_U16(ds, figure + 18);
        }
        DS_U16(ds, figure + 20) = DS_U16(ds, table + offset);
    }
}

/* AD00 (civilian=0) / AD37 (civilian!=0). ES=main DS. */
static uint16_t spawn_dx(Game *g, uint16_t requested, uint8_t civilian, uint16_t dx, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if (!requested)
        return dx;
    if (screen)
        figure_spawn_grid_display(g, screen);
    else
        figure_spawn_grid(g);
    /* A480 leaves collision's minor grid delta in DX when the last map sample
     * was skipped, otherwise the pixel sampler leaves port 03CE. */
    if (DS_U8(ds, 0x8682)) {
        uint16_t last_x = DS_U16(ds, DS_PEN_X) + 768, last_z = DS_U16(ds, DS_PROBE_Z) + 256;
        int16_t x0 = (int16_t)(uint16_t)(last_x + 8) >> 4;
        int16_t z0 = (int16_t)(uint16_t)(last_z + 8) >> 4;
        int16_t x1 = (int16_t)(uint16_t)(DS_U16(ds, DS_POINT_X) + 8) >> 4;
        int16_t z1 = (int16_t)(uint16_t)(DS_U16(ds, DS_POINT_Z) + 8) >> 4;
        int16_t vx = (uint16_t)(x0 - x1), vz = (uint16_t)(z0 - z1);
        uint16_t ax = vx < 0 ? -vx : vx, az = vz < 0 ? -vz : vz;
        dx = ax < az ? ax : az;
    } else
        dx = 0x03CE;
    if (!DS_U16(ds, 0xB82A)) {
        DS_U16(ds, civilian ? 0x116E : 0x1170) += requested;
        return dx;
    }
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT);
    if (!civilian) {
        if ((uint16_t)(count + requested) >= 31) {
            requested = (uint16_t)(30 - count);
            if (!requested)
                return dx;
        }
    } else
        DS_U16(ds, 0x119C) += requested;
    DS_U16(ds, 0xB828) = requested;
    if (civilian) {
        dx = (uint32_t)count * 22 >> 16;
        uint16_t figure = (uint16_t)(0x0B30 + count * 22), bits = random_word(ds);
        for (uint32_t i = 0; i < requested; ++i, figure += 22) {
            uint8_t first = bits & 1;
            bits = (bits >> 1) | (bits << 15);
            DS_U8(ds, figure) = first ? 4 : 2;
            uint8_t second = bits & 1;
            bits = (bits >> 1) | (bits << 15);
            if (second)
                DS_U8(ds, figure) |= 8;
            uint16_t r = random_word(ds);
            uint16_t rotated = (r >> 1) | (r << 15);
            DS_U16(ds, figure + 10) = 2 + !(r & 1);
            DS_U16(ds, figure + 6) = rotated & 0x1C0;
        }
    }
    uint16_t dest = DS_U16(ds, 0x03A4), id = count * 2;
    for (uint32_t i = 0; i < requested; ++i, dest += 12, id += 2) {
        select_position(ds, 65535, 1, &dx);
        DS_U16(ds, dest) = DS_U16(ds, DS_POINT_X);
        DS_U16(ds, dest + 4) = DS_U16(ds, DS_POINT_Z);
        DS_U16(ds, dest + 10) = 2 + DS_U16(ds, DS_DIFFICULTY);
        DS_U16(ds, dest + 2) = 0;
        DS_U16(ds, dest + 8) = id;
        DS_U16(ds, dest + 6) = 0x4000;
        DS_U16(ds, DS_FIGURE_COUNT)++;
    }
    DS_U16(ds, 0x03A4) = dest;
    count = DS_U16(ds, DS_FIGURE_COUNT);
    for (uint16_t i = 0; i < count; ++i) {
        uint16_t figure = (uint16_t)(0x0B30 + i * 22);
        if (!(DS_U8(ds, figure) & 16))
            init_movement(ds, figure, (uint16_t)(0x0DF0 + i * 12), &dx);
    }
    if (count)
        figure_select_frames(ds);
    return dx;
}

uint16_t figure_spawn_dx(Game *g, uint16_t requested, uint8_t civilian, uint16_t dx)
{
    return spawn_dx(g, requested, civilian, dx, NULL);
}

int figure_spawn_display(Game *g, uint16_t requested, uint8_t civilian, uint8_t *screen)
{
    if (!requested)
        return 0;
    if (DS_U8(g->ds, DS_FACILITY_SCREEN) && !screen)
        return -1;
    spawn_dx(g, requested, civilian, 0, DS_U8(g->ds, DS_FACILITY_SCREEN) ? screen : NULL);
    return 0;
}

void figure_spawn(Game *g, uint16_t requested, uint8_t civilian)
{
    figure_spawn_dx(g, requested, civilian, 0);
}

/* AFD0 including its conditional AD37 replacement call. */
void figure_remove_complete(Game *g, uint16_t record)
{
    if (figure_remove(g->ds, record))
        figure_spawn(g, 1, 1);
}
