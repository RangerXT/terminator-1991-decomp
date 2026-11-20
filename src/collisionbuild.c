/* Collision-map construction 11BC:2251/233F/239D/2491. */
#include "term.h"

static uint16_t far_word(Game *g, uint16_t seg, uint16_t off)
{
    uint8_t *p = far_ptr(g, seg, off);
    return (uint16_t)(p[0] | (p[1] << 8));
}

void collision_stamp_setup(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, DS_STAMP_X) = DS_U16(ds, DS_STAMP_Z) = 0;
    uint16_t from = DS_U16(ds, 0x8FEC + (uint16_t)(DS_U16(ds, 0x912E) * 2)) + 2;
    uint16_t seg = DS_U16(ds, 0x91B0);
    DS_U16(ds, DS_STAMP_HALF_W) = far_word(g, seg, from + 2);
    DS_U16(ds, DS_STAMP_HALF_H) = far_word(g, seg, from + 4);
    DS_U16(ds, DS_STAMP_W) = far_word(g, seg, from + 6);
    DS_U16(ds, 0x914A) = DS_U16(ds, DS_STAMP_W) - DS_U16(ds, DS_STAMP_HALF_W) * 2;
    DS_U16(ds, DS_STAMP_H) = far_word(g, seg, from + 8);
    DS_U16(ds, 0x914C) = DS_U16(ds, DS_STAMP_H) - DS_U16(ds, DS_STAMP_HALF_H) * 2;
    if (DS_U16(ds, 0x9140) & 1) {
        uint16_t t = DS_U16(ds, DS_STAMP_HALF_W);
        DS_U16(ds, DS_STAMP_HALF_W) = DS_U16(ds, DS_STAMP_HALF_H);
        DS_U16(ds, DS_STAMP_HALF_H) = t;
        t = DS_U16(ds, DS_STAMP_W);
        DS_U16(ds, DS_STAMP_W) = DS_U16(ds, DS_STAMP_H);
        DS_U16(ds, DS_STAMP_H) = t;
    }
    uint16_t x = DS_U16(ds, DS_GRID_X) - DS_U16(ds, DS_STAMP_HALF_W);
    if ((int16_t)x < 0)
        DS_U16(ds, DS_STAMP_W) -= (uint16_t)(DS_U16(ds, DS_STAMP_HALF_W) - DS_U16(ds, DS_GRID_X));
    else {
        DS_U16(ds, DS_STAMP_X) = x;
        if ((uint16_t)(x + DS_U16(ds, DS_STAMP_W)) > 192)
            DS_U16(ds, DS_STAMP_W) = 192 - DS_U16(ds, DS_GRID_X) + DS_U16(ds, DS_STAMP_HALF_W);
    }
    uint16_t z = DS_U16(ds, DS_GRID_Z) - DS_U16(ds, DS_STAMP_HALF_H);
    if ((int16_t)z < 0)
        DS_U16(ds, DS_STAMP_H) -= (uint16_t)(DS_U16(ds, DS_STAMP_HALF_H) - DS_U16(ds, DS_GRID_Z));
    else {
        DS_U16(ds, DS_STAMP_Z) = z;
        if ((uint16_t)(z + DS_U16(ds, DS_STAMP_H)) > 192)
            DS_U16(ds, DS_STAMP_H) = 192 - DS_U16(ds, DS_GRID_Z) + DS_U16(ds, DS_STAMP_HALF_H);
    }
    DS_U16(ds, 0x913A) = 192 * (uint8_t)DS_U16(ds, DS_STAMP_Z) + DS_U16(ds, DS_STAMP_X);
}

/* Negative entries deliberately return unchanged SI, as the executable does. */
uint16_t collision_stamp_object(Game *g, uint16_t seg, uint16_t source)
{
    uint8_t *ds = g->ds;
    if ((int16_t)far_word(g, seg, source + 10) < 0)
        return source;
    uint16_t ptr = DS_U16(ds, 0x8816);
    DS_U16(ds, ptr) = source;
    DS_U16(ds, 0x8816) += 2;
    ptr = DS_U16(ds, 0x8B38);
    DS_U16(ds, ptr) = DS_U16(ds, DS_GRID_CELL_X);
    DS_U16(ds, ptr + 2) = DS_U16(ds, DS_GRID_CELL_Z);
    DS_U16(ds, 0x8B38) += 4;
    uint16_t record = 0x8B3A + DS_U16(ds, 0x8FEA), x = far_word(g, seg, source), z = far_word(g, seg, source + 4);
    DS_U16(ds, record) = x + DS_U16(ds, DS_GRID_CELL_X);
    DS_U16(ds, DS_GRID_X) = (int16_t)(uint16_t)(x + 8) >> 4;
    DS_U16(ds, DS_GRID_X) += 64 * (uint8_t)(DS_U16(ds, DS_PEN_X) - DS_U16(ds, 0x9130));
    DS_U16(ds, record + 2) = far_word(g, seg, source + 2);
    DS_U16(ds, record + 4) = z + DS_U16(ds, DS_GRID_CELL_Z);
    DS_U16(ds, DS_GRID_Z) = (int16_t)(uint16_t)(z + 8) >> 4;
    DS_U16(ds, DS_GRID_Z) = 64 * (uint8_t)(DS_U16(ds, DS_PROBE_Z) - DS_U16(ds, 0x9132)) + 64 - DS_U16(ds, DS_GRID_Z);
    DS_U16(ds, record + 6) = DS_U16(ds, 0x9140) = far_word(g, seg, source + 6) & 3;
    DS_U16(ds, record + 8) = DS_U16(ds, 0x912E) = far_word(g, seg, source + 8);
    DS_U16(ds, record + 10) = far_word(g, seg, source + 10);
    source += 12;
    DS_U16(ds, 0x8FEA) += 12;
    collision_stamp_setup(g);
    uint16_t height = DS_U16(ds, DS_STAMP_H), width = DS_U16(ds, DS_STAMP_W);
    if (height && width) {
        uint16_t dest = DS_U16(ds, 0x913A), out_seg = DS_U16(ds, DS_SEG_COLLISION);
        uint8_t value = DS_U16(ds, DS_STAMP_VALUE);
        for (uint32_t row = 0; row < height; ++row, dest += 192)
            for (uint32_t col = 0; col < width; ++col)
                *far_ptr(g, out_seg, (uint16_t)(dest + col)) = value;
    }
    return source;
}

static void stamp_extras(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t old_count = DS_U16(ds, DS_VISIBLE_COUNT);
    if (DS_U16(ds, DS_EXTRA_COUNT)) {
        DS_U8(ds, 0x5EDF) = DS_U16(ds, DS_PEN_X);
        DS_U8(ds, 0x5EE1) = DS_U16(ds, DS_PROBE_Z);
        DS_U16(ds, DS_VISIBLE_COUNT) = 0;
        DS_U8(ds, 0x7A18) = 255;
        collect_cell_extras(g, 0x50B2);
        uint16_t count = DS_U16(ds, DS_VISIBLE_COUNT);
        if (count) {
            uint16_t x = DS_U16(ds, DS_GRID_CELL_X), z = DS_U16(ds, DS_GRID_CELL_Z), source = 0x50B2;
            DS_U16(ds, DS_GRID_CELL_X) = DS_U16(ds, DS_GRID_CELL_Z) = 0;
            for (uint32_t i = 0; i < count; ++i)
                source = collision_stamp_object(g, g->ds_seg, source);
            DS_U16(ds, DS_GRID_CELL_X) = x;
            DS_U16(ds, DS_GRID_CELL_Z) = z;
        }
    }
    DS_U16(ds, DS_VISIBLE_COUNT) = old_count;
}

void collision_map_build(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x8685))
        return;
    DS_U16(ds, 0x8816) = 0x8686;
    DS_U16(ds, 0x8B38) = 0x8818;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint16_t col = DS_U16(ds, player + 30) - DS_U16(ds, 0x7272) - 1;
    uint16_t row = DS_U16(ds, player + 32) - DS_U16(ds, 0x7274) - 1;
    uint16_t out_seg = DS_U16(ds, DS_SEG_COLLISION);
    for (uint32_t i = 0; i < 0x9000; ++i)
        *far_ptr(g, out_seg, (uint16_t)i) = 0;
    DS_U16(ds, 0x9134) = 42;
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, 0x9132) = row;
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, 0x9130) = col;
    uint16_t table = (uint16_t)((24 * (uint8_t)row + col) * 2), seg = DS_U16(ds, DS_SEG_CELLS);
    DS_U16(ds, DS_GRID_CELL_X) = 0xFC00;
    DS_U16(ds, DS_GRID_CELL_Z) = 0x0400;
    DS_U16(ds, 0x8FEA) = 0;
    DS_U16(ds, DS_STAMP_VALUE) = 1;
    for (unsigned cell = 0; cell < 9; ++cell) {
        stamp_extras(g);
        uint16_t source = far_word(g, seg, table);
        if (source) {
            uint16_t count = far_word(g, seg, source);
            source += 2;
            do {
                if (DS_U16(ds, 0x913C) == DS_U16(ds, DS_STAMP_VALUE)) {
                    uint8_t *at = far_ptr(g, seg, (uint16_t)(source + 10));
                    at[0] = at[1] = 255;
                    if (--count)
                        continue;
                }
                source = collision_stamp_object(g, seg, source);
                DS_U16(ds, DS_STAMP_VALUE)++;
            } while (--count);
        }
        DS_U16(ds, DS_GRID_CELL_X) += 1024;
        DS_U16(ds, DS_PEN_X)++;
        if (DS_U16(ds, DS_PEN_X) >= (uint16_t)(DS_U16(ds, 0x9130) + 3)) {
            DS_U16(ds, DS_GRID_CELL_X) = 0xFC00;
            DS_U16(ds, DS_GRID_CELL_Z) -= 1024;
            DS_U16(ds, DS_PEN_X) = DS_U16(ds, 0x9130);
            DS_U16(ds, DS_PROBE_Z)++;
            table += DS_U16(ds, 0x9134);
        }
        table += 2;
    }
}
