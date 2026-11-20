/* Figure removal, original 0000:AFD0. ES must equal main DS in this interface.
 * Returns 1 when the caller must perform AD37(AX=1), otherwise 0.
 * Does not integrate into existing event-only blast callers yet. */
#include "term.h"

static void copy_words(uint8_t *ds, uint16_t *dest, uint16_t *source, unsigned n)
{
    while (n--) {
        uint16_t word = DS_U16(ds, *source);
        DS_U16(ds, *dest) = word;
        *source += 2;
        *dest += 2;
    }
}

int figure_remove(uint8_t *ds, uint16_t record)
{
    DS_U8(ds, 0xB6A1) = 255;
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT);
    if (!count)
        return 0;
    uint16_t index = DS_U16(ds, record + 8) >> 1;
    int16_t remaining = (uint16_t)(count - index);
    if (remaining <= 0)
        return 0;
    /* MUL CL uses only AL, despite the preceding word-sized range check. */
    uint16_t figure = (uint16_t)(0x0B30 + (uint8_t)index * 22);
    uint16_t kind = DS_U16(ds, figure) & 14;
    uint16_t dest = record, source = record + 12;
    for (int i = 0; i < remaining; ++i) {
        copy_words(ds, &dest, &source, 4);
        source += 2;
        dest += 2; /* retain each destination record's ID */
        copy_words(ds, &dest, &source, 1);
    }
    for (unsigned i = 0; i < 6; ++i, dest += 2)
        DS_U16(ds, dest) = 0;
    dest = figure;
    source = figure + 22;
    for (int i = 0; i < remaining; ++i)
        copy_words(ds, &dest, &source, 11);
    for (unsigned i = 0; i < 11; ++i, dest += 2)
        DS_U16(ds, dest) = 0;
    DS_U16(ds, DS_FIGURE_COUNT)--;
    DS_U16(ds, 0x03A4) -= 12;
    if (!kind)
        return 0;
    DS_U16(ds, 0x119C)--;
    if (DS_U8(ds, 0xB69F) || DS_U8(ds, DS_IN_BATTLE)) {
        DS_U16(ds, 0x116E)++;
        return 0;
    }
    return 1;
}

/* 5CFA: sample the four EGA planes of the overhead-map page. AX ends FFxx. */
static uint16_t map_sample(Game *g, uint16_t x, uint16_t z, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    int16_t px = x, py = z;
    project_point(ds, &px, &py, 12000);
    x = (uint16_t)(px + 160);
    uint16_t y = (uint16_t)(92 - py);
    uint16_t off = (uint16_t)(DS_U16(ds, 0x1252 + (uint16_t)(y * 2)) + (x >> 3) + 0x6000);
    uint32_t addr = (((uint32_t)DS_U16(ds, DS_SEG_SCREEN) << 4) + off) & 0xFFFFF;
    uint8_t colour = 0, shift = 7 - (x & 7);
    for (int plane = 3; plane >= 0; --plane) {
        ega_gc(g->planes, 4, plane);
        uint8_t byte = addr >= 0xA0000 && addr < 0xB0000
                           ? (screen ? screen[(uint16_t)addr] : ega_load(g->planes, (uint16_t)addr))
                           : g->mem[addr];
        colour = (uint8_t)(colour * 2 + ((byte >> shift) & 1));
    }
    return 0xFF00u | colour;
}

uint16_t figure_map_sample(Game *g, uint16_t x, uint16_t z)
{
    return map_sample(g, x, z, NULL);
}

/* During a VGA shop alarm the original still selects EGA read planes, but each
 * read returns the same indexed byte and does not load the planar latches. */
uint16_t figure_map_sample_display(Game *g, uint16_t x, uint16_t z, uint8_t *screen)
{
    return map_sample(g, x, z, DS_U8(g->ds, DS_FACILITY_SCREEN) ? screen : NULL);
}

/* A480: one 4x4 block of the nine-block candidate grid. */
static void spawn_grid_block(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER), index = DS_U16(ds, 0xB73E);
    DS_U16(ds, DS_POINT_X) = DS_U16(ds, player);
    DS_U16(ds, DS_POINT_Z) = DS_U16(ds, player + 4);
    DS_U16(ds, DS_PEN_X) = DS_U16(ds, 0xB7D0 + (uint16_t)(index * 4));
    DS_U16(ds, DS_PROBE_Z) = DS_U16(ds, 0xB7D2 + (uint16_t)(index * 4));
    uint16_t dest = (uint16_t)(0xB740 + index * 4);
    for (unsigned row = 0; row < 4; ++row) {
        uint16_t start_x = DS_U16(ds, DS_PEN_X);
        for (unsigned col = 0; col < 4; ++col) {
            uint16_t x = DS_U16(ds, DS_PEN_X), z = DS_U16(ds, DS_PROBE_Z);
            uint16_t player_x = DS_U16(ds, DS_POINT_X), player_z = DS_U16(ds, DS_POINT_Z);
            uint16_t value = collision_line_blocker(g) ? 1 : 0;
            DS_U16(ds, DS_PEN_X) = x;
            DS_U16(ds, DS_PROBE_Z) = z;
            DS_U16(ds, DS_POINT_X) = player_x;
            DS_U16(ds, DS_POINT_Z) = player_z;
            if (DS_U8(ds, 0x8682) || (uint8_t)map_sample(g, x, z, screen) == 1)
                value = 255;
            if (value == 1)
                DS_U16(ds, 0xB82A)++;
            DS_U8(ds, dest + col) = value;
            DS_U16(ds, DS_PEN_X) += 256;
        }
        DS_U16(ds, DS_PROBE_Z) -= 256;
        DS_U16(ds, DS_PEN_X) = start_x;
        dest += 36;
    }
    DS_U16(ds, 0xB73E)++;
    if (DS_I16(ds, 0xB73E) >= 9)
        DS_U16(ds, 0xB73E) = 0;
}

void figure_spawn_grid_block(Game *g)
{
    spawn_grid_block(g, NULL);
}

/* A46F: cover all nine blocks, starting at the saved block index. */
void figure_spawn_grid(Game *g)
{
    DS_U16(g->ds, 0xB82A) = 0;
    for (unsigned i = 0; i < 9; ++i)
        spawn_grid_block(g, NULL);
}

int figure_spawn_grid_display(Game *g, uint8_t *screen)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN) && !screen)
        return -1;
    DS_U16(g->ds, 0xB82A) = 0;
    for (unsigned i = 0; i < 9; ++i)
        spawn_grid_block(g, DS_U8(g->ds, DS_FACILITY_SCREEN) ? screen : NULL);
    return 0;
}

static uint16_t feedback_word(Game *g, uint16_t seg, uint16_t off)
{
    uint8_t *p = far_ptr(g, seg, off);
    return (uint16_t)(p[0] | (p[1] << 8));
}

/* C9A5: four length-prefixed ByteKiller planes, 96x49 pixels.
 * 5A4D is a relocated scratch segment, 01DA paragraphs before main DS. */
uint16_t figure_feedback_draw(Game *g, uint16_t source_seg, uint16_t source)
{
    uint16_t work_seg = g->ds_seg - 0x01DA;
    for (unsigned plane = 0; plane < 4; ++plane) {
        uint16_t packed = feedback_word(g, source_seg, source);
        source += 2;
        unpack_block(g, source_seg, source, work_seg, plane * 0x024C, packed, 4);
        source += packed;
    }
    uint16_t from = 0;
    for (unsigned plane = 0; plane < 4; ++plane) {
        ega_seq_mask(g->planes, 1 << plane);
        uint16_t to = 0x12C1;
        for (unsigned row = 0; row < 49; ++row) {
            for (unsigned word = 0; word < 6; ++word) {
                uint16_t value = feedback_word(g, work_seg, from);
                from += 2;
                ega_store(g->planes, to++, (uint8_t)value);
                ega_store(g->planes, to++, (uint8_t)(value >> 8));
            }
            to += 28;
        }
    }
    if (DS_U16(g->ds, DS_DRAW_PAGE))
        screen_copy_rect(g, 0x12C1, (uint16_t)(0x12C1 + DS_U16(g->ds, DS_DRAW_PAGE)), 12, 49);
    return source;
}

/* 5BDB: cycle the requested feedback family, then display its first frame. */
void figure_feedback(Game *g, uint16_t family)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, player + 14) & 1) || DS_U8(ds, DS_CAMERA_MODE))
        return;
    DS_U8(ds, 0x7AC6) = 255;
    uint16_t slot = family == 0 ? 0 : family == 4 ? 2 : 4;
    DS_U16(ds, 0x7A80 + slot)++;
    uint16_t count = DS_U16(ds, 0x7A86 + slot);
    if (DS_U16(ds, 0x7A80 + slot) >= count)
        DS_U16(ds, 0x7A80 + slot) -= count;
    uint16_t frame = (uint16_t)((family + DS_U16(ds, 0x7A80 + slot)) * 2);
    uint16_t source = DS_U16(ds, 0x7A8C + frame);
    DS_U16(ds, 0x7A7E) = figure_feedback_draw(g, DS_U16(ds, DS_WORK_BUFFER_SEG), source) + 2;
    DS_U16(ds, 0x117C) = 6;
}

/* 5C40: six CAF deltas on the base EGA page, then hold or hide the last frame. */
void figure_feedback_step(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) != 1)
        return;
    uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
    if (DS_U16(ds, 0x117C)) {
        DS_U8(ds, 0x7A3F) = (uint8_t)-DS_U8(ds, 0x7A3F);
        if (DS_U8(ds, 0x7A3F))
            return;
        --DS_U16(ds, 0x117C);
        uint16_t seg = DS_U16(ds, DS_WORK_BUFFER_SEG), at = DS_U16(ds, 0x7A7E);
        uint16_t packed = feedback_word(g, seg, at), work = DS_U16(ds, 0xE16E);
        unpack_block(g, seg, at + 2, work, DS_U16(ds, 0xE16C), packed, 4);
        DS_U16(far_ptr(g, g->ds_seg - 0x5C27, 0xB423), 0) = 39;
        cutscene_ega_runs(g, far_ptr(g, work, 0), 40);
        if (page)
            screen_copy_rect(g, 0x12C1, (uint16_t)(0x12C1 + page), 12, 49);
        DS_U16(ds, 0x7A7E) = at + 2 + packed;
        if (!DS_U16(ds, 0x117C))
            DS_U8(ds, 0x7A3E) = 150;
        return;
    }
    DS_U8(ds, 0x7AC6) = 0;
    if (!DS_U8(ds, 0x7A3E))
        return;
    if (!--DS_U8(ds, 0x7A3E))
        hud_message_hide(g);
    else if (page)
        screen_copy_rect(g, 0x12C1, (uint16_t)(0x12C1 + page), 12, 49);
}
