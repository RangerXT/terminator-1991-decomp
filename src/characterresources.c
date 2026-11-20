/* CSF model families and CAF animation indexing loaded on leaving a vehicle. */
#include "term.h"

static uint16_t word_at(Game *g, uint16_t seg, uint16_t off)
{
    uint8_t *p = far_ptr(g, seg, off);
    return p[0] | ((uint16_t)p[1] << 8);
}

/* B187/B199/B1AD with common B1C1 and B1DE. kind=0 MANWOM, 1 COP, 2 SOL.
 * The original family-0 parser starts at zero even if its file destination does not.
 * Installed valid CSF assets are required; this is not a malformed-file validator. */
int character_models_load(Game *g, const ImageIO *io, uint8_t kind)
{
    if (kind > 2)
        return -1;
    uint8_t *ds = g->ds;
    uint16_t ptr = kind ? 0x91CC : 0x91C8, seg = DS_U16(ds, ptr + 2), dest = DS_U16(ds, ptr);
    uint16_t filename = kind == 0 ? 0xB66E : kind == 1 ? 0xB681 : 0xB679, table = kind ? 0xB8D0 : 0xB830;
    if (file_load(g, io, filename, seg, dest) == UINT32_MAX)
        return -1;
    uint16_t at = kind ? dest : 0, count = word_at(g, seg, at);
    at += 2;
    do {
        uint16_t size = word_at(g, seg, at);
        DS_U16(ds, table) = at;
        table += 2;
        at += 2;
        uint16_t faces = word_at(g, seg, (uint16_t)(at + 2)), flags = at + word_at(g, seg, (uint16_t)(at + 10));
        for (unsigned i = 0; i < faces; ++i)
            *far_ptr(g, seg, (uint16_t)(flags + i)) = 255;
        at += size;
    } while (--count);
    return 0;
}

/* 70FB: the concatenated CAF files contain groups of entries. Each entry has
 * four length-prefixed planes followed by another counted set of blocks. */
void character_animations_index(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_WORK_BUFFER_SEG), at = DS_U16(ds, DS_WORK_BUFFER), table = 0x7A8C;
    do {
        uint16_t count = word_at(g, seg, at);
        at += 2;
        do {
            DS_U16(ds, table) = at;
            table += 2;
            for (unsigned i = 0; i < 4; ++i) {
                uint16_t size = word_at(g, seg, at);
                at += 2;
                at += size;
            }
            uint16_t blocks = word_at(g, seg, at);
            at += 2;
            do {
                uint16_t size = word_at(g, seg, at);
                at += 2;
                at += size;
            } while (--blocks);
        } while (--count);
    } while (at < DS_U16(ds, 0x8542));
}

/* 712B appends COP/SOL.CAF at 8540 and then reindexes both CAF families. */
int character_animations_append(Game *g, const ImageIO *io, uint16_t filename)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_WORK_BUFFER_SEG), at = DS_U16(ds, 0x8540);
    uint32_t read = file_load(g, io, filename, seg, at);
    if (read == UINT32_MAX)
        return -1;
    uint16_t count = word_at(g, seg, at);
    DS_U16(ds, 0x7A8A) = count;
    if (DS_U16(ds, 0x7A84) >= count)
        DS_U16(ds, 0x7A84) = 0;
    DS_U16(ds, 0x8542) = at + (uint16_t)read;
    character_animations_index(g);
    return 0;
}

/* AE13: only the low byte of 11CD selects the armed figure/CAF family. */
int character_resources_variant(Game *g, const ImageIO *io)
{
    uint8_t cop = DS_U8(g->ds, 0x11CD) != 0;
    if (character_models_load(g, io, cop ? 1 : 2))
        return -1;
    return character_animations_append(g, io, cop ? 0xB691 : 0xB689);
}

/* 70DF: MANWOM.CAF base followed by the current COP/SOL model and animation. */
int character_resources_load(Game *g, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    uint32_t read = file_load(g, io, 0x843C, DS_U16(ds, DS_WORK_BUFFER_SEG), DS_U16(ds, DS_WORK_BUFFER));
    if (read == UINT32_MAX)
        return -1;
    DS_U16(ds, 0x8540) = DS_U16(ds, 0x8542) = (uint16_t)read;
    return character_resources_variant(g, io);
}
