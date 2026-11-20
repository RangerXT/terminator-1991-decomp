/* Shared four-plane image service, cached and DOS-file paths (6962..6AFA). */
#include "term.h"

static uint32_t address(uint16_t seg, uint16_t off)
{
    return (((uint32_t)seg << 4) + off) & 0xFFFFF;
}

static uint8_t read_at(Game *g, uint32_t at)
{
    at &= 0xFFFFF;
    return at >= 0xA0000 && at < 0xB0000 ? ega_load(g->planes, (uint16_t)at) : g->mem[at];
}

static void write_at(Game *g, uint32_t at, uint8_t value)
{
    at &= 0xFFFFF;
    if (at >= 0xA0000 && at < 0xB0000)
        ega_store(g->planes, (uint16_t)at, value);
    else
        g->mem[at] = value;
}

static void copy_bytes(Game *g, uint16_t src_seg, uint16_t src, uint16_t dst_seg, uint16_t dst, unsigned count,
                       int words)
{
    for (unsigned i = 0; i < count; ++i) {
        uint32_t from = address(src_seg, src), to = address(dst_seg, dst);
        uint8_t lo = read_at(g, from);
        if (words) {
            /* MOVSW reads both bytes before either destination byte is written. */
            uint8_t hi = read_at(g, from + 1);
            write_at(g, to, lo);
            write_at(g, to + 1, hi);
        } else
            write_at(g, to, lo);
        src += words ? 2 : 1;
        dst += words ? 2 : 1;
    }
}

static uint32_t io_call(Game *g, const ImageIO *io, uint16_t op, uint16_t handle, uint16_t seg, uint16_t off,
                        uint16_t count)
{
    return io && io->call ? io->call(g, op, handle, seg, off, count, io->user) : UINT32_MAX;
}

/* orig 6AAE. Cached header copy uses the incoming ES, supplied explicitly here.
 * The normal full-screen service requires header_segment == g->ds_seg. */
int image_prepare(Game *g, const ImageIO *io, uint16_t filename, uint16_t header_segment)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x8087)) {
        uint16_t source = DS_U16(ds, 0x009D + DS_U16(ds, 0xC4AE));
        uint16_t seg = DS_U16(ds, 0x0208);
        copy_bytes(g, seg, source, header_segment, 0x805E, 16, 1);
        DS_U16(ds, 0x807E) = 0x806E;
        DS_U16(ds, 0x8084) = (uint16_t)(source + 32);
        return 0;
    }
    uint32_t result = io_call(g, io, IMG_OPEN, 2, g->ds_seg, filename, 0);
    if (result == UINT32_MAX)
        return -1;
    uint16_t handle = (uint16_t)result;
    DS_U16(ds, 0x8080) = handle;
    result = io_call(g, io, IMG_READ, handle, g->ds_seg, 0x805E, 32);
    if (result == UINT32_MAX)
        return -1;
    DS_U16(ds, 0x807E) = 0x806E;
    return 0;
}

/* orig 6A0F. Decode one plane. Checksums and DOS carry are ignored by the original;
 * UINT32_MAX is only the host interface's explicit "unavailable" result. */
int image_next_plane(Game *g, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    uint16_t table = DS_U16(ds, 0x807E);
    uint16_t packed = DS_U16(ds, table);
    DS_U16(ds, 0x807E) += 2;
    if (DS_U8(ds, 0x8087)) {
        uint16_t source = DS_U16(ds, 0x8084), seg = DS_U16(ds, 0x0208);
        uint16_t dest_seg = DS_U16(ds, 0x7B8C), dest = DS_U16(ds, 0x7B8A);
        uint16_t type = DS_U16(ds, 0x806A);
        if (type & 4)
            dest = 0; /* cached ByteKiller ignores the pointer's offset */
        unpack_block(g, seg, source, dest_seg, dest, packed, type);
        DS_U16(ds, 0x8084) += packed;
        return 0;
    }
    uint32_t result = io_call(g, io, IMG_READ, DS_U16(ds, 0x8080), DS_U16(ds, DS_FILE_BUFFER_SEG),
                              DS_U16(ds, DS_FILE_BUFFER), packed);
    if (result == UINT32_MAX)
        return -1;
    uint16_t type = DS_U16(ds, 0x806A);
    if (!(type & 4)) {
        DS_U16(ds, 0x805A) = (uint16_t)result;
        uint16_t source = DS_U16(ds, DS_FILE_BUFFER), seg = DS_U16(ds, DS_FILE_BUFFER_SEG);
        /* The file path passes plane_bytes as the LZHUF input budget. */
        unpack_block(g, seg, source, seg, (uint16_t)(source + (uint16_t)result), DS_U16(ds, 0x806C), type);
    } else {
        DS_U16(ds, 0x805A) = 0;
        uint16_t seg = DS_U16(ds, 0xDE20);
        unpack_block(g, seg, 0, seg, 0, packed, type);
    }
    return 0;
}

/* orig 6994. Row mode copies width bytes per row; linear mode copies 805C words.
 * The selected EGA plane and inherited graphics registers remain observable. */
int image_draw_loaded(Game *g, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0x8086) = 1;
    for (unsigned plane = 0; plane < 4; ++plane) {
        ega_seq_mask(g->planes, DS_U8(ds, 0x8086));
        DS_U8(ds, 0x8086) <<= 1;
        if (image_next_plane(g, io))
            return -1;
        uint16_t dest = (uint16_t)(DS_U16(ds, 0x8082) + DS_U16(ds, DS_DRAW_PAGE));
        uint16_t words = DS_U16(ds, 0x805C);
        uint16_t width = (uint16_t)(DS_U16(ds, 0x8062) + 7) >> 3;
        uint16_t stride = DS_U16(ds, 0x1228), rows = DS_U16(ds, 0x8064);
        uint16_t dest_seg = DS_U16(ds, DS_SEG_SCREEN);
        uint16_t source, source_seg;
        if (DS_U8(ds, 0x8087)) {
            source = DS_U16(ds, 0x7B8A);
            source_seg = DS_U16(ds, 0x7B8C);
        } else {
            source = DS_U16(ds, 0x805A);
            source_seg = DS_U16(ds, DS_FILE_BUFFER_SEG);
        }
        if (DS_U8(ds, 0x8088)) {
            unsigned height = rows ? rows : 65536;
            for (unsigned row = 0; row < height; ++row) {
                copy_bytes(g, source_seg, source, dest_seg, dest, width, 0);
                source += width;
                dest += stride;
            }
        } else
            copy_bytes(g, source_seg, source, dest_seg, dest, words, 1);
    }
    ega_seq_mask(g->planes, 15);
    return 0;
}

/* orig 6962. Valid four-plane compressed assets; cached ES-on-entry is main DS. */
int image_load_screen(Game *g, const ImageIO *io, uint16_t filename)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0x8087) = DS_U16(ds, 0x0208) && DS_U16(ds, 0xC4AE) ? 255 : 0;
    if (image_prepare(g, io, filename, g->ds_seg) || image_draw_loaded(g, io))
        return -1;
    if (!DS_U8(ds, 0x8087) && io_call(g, io, IMG_CLOSE, DS_U16(ds, 0x8080), 0, 0, 0) == UINT32_MAX)
        return -1;
    return 0;
}

/* orig FACE (far buffer) and FAAF (main-DS buffer). Return AX plus carry in bit 16.
 * On a read failure the original returns without closing its handle; retain that
 * behavior. On success AX is the read count, while carry comes from CLOSE. */
uint32_t file_load(Game *g, const ImageIO *io, uint16_t filename, uint16_t dest_seg, uint16_t dest)
{
    uint32_t opened = io_call(g, io, IMG_OPEN, 0, g->ds_seg, filename, 0);
    if (opened == UINT32_MAX)
        return opened;
    /* Failed OPEN takes an ADD SP cleanup branch, clearing carry on the normal
     * non-wrapping DOS stack. The error number remains in AX. */
    if (opened & 0x10000)
        return opened & 65535;
    uint16_t handle = (uint16_t)opened;
    uint32_t read = io_call(g, io, IMG_READ, handle, dest_seg, dest, 65535);
    if (read == UINT32_MAX || (read & 0x10000))
        return read;
    uint32_t closed = io_call(g, io, IMG_CLOSE, handle, 0, 0, 0);
    if (closed == UINT32_MAX)
        return closed;
    return (read & 65535) | (closed & 0x10000);
}

/* Ready-to-use HudServices callback. user points to an ImageIO. No game-state or
 * rendering effects are supplied by the host, only DOS-style file bytes/results. */
uint32_t image_hud_service(Game *g, uint16_t service, uint16_t filename, void *user)
{
    const ImageIO *io = (const ImageIO *)user;
    if (service == HS_LOAD_IMAGE)
        return image_load_screen(g, io, filename) ? UINT32_MAX : 0;
    if (service == HS_LOAD_FILE)
        return file_load(g, io, filename, DS_U16(g->ds, 0x91C2), DS_U16(g->ds, DS_LOAD_BUFFER));
    return UINT32_MAX;
}

/* Resource half of MapResources. The caller retains BIOS/palette/page services. */
int image_map_service(Game *g, uint16_t service, uint16_t filename, uint16_t dest, void *user)
{
    const ImageIO *io = (const ImageIO *)user;
    if (service == MS_LOAD_IMAGE)
        return image_load_screen(g, io, filename);
    uint32_t result;
    if (service == MS_READ_FILE)
        result = file_load(g, io, filename, g->ds_seg, dest);
    else if (service == MS_READ_FAR_FILE)
        result = file_load(g, io, filename, DS_U16(g->ds, DS_FILE_BUFFER_SEG), dest);
    else
        return -1;
    return result == UINT32_MAX || (result & 0x10000) ? -1 : 0;
}

/* F7AD with incoming AX=0 only: attributes probe, read-only open, errno.
 * Other create/access/share flags in the original wrapper are not covered. */
uint32_t file_open_existing(Game *g, const ImageIO *io, uint16_t filename)
{
    uint32_t result = io_call(g, io, IMG_ATTR, 0, g->ds_seg, filename, 0);
    if (result == UINT32_MAX)
        return result;
    if (!(result & 0x10000))
        result = io_call(g, io, IMG_OPEN, 0, g->ds_seg, filename, 0);
    if (result != UINT32_MAX && (result & 0x10000))
        DS_U16(g->ds, 0xEA50) = (uint16_t)result;
    return result;
}
