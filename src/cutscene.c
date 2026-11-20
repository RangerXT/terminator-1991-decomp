/* VGA DFB background and DFF frame application, original B558 and B519.
 * The host owns the 320x200 indexed framebuffer and 256x3 six-bit palette.
 * Buffers must be 64 KB and asset streams valid, matching original assumptions. */
#include "term.h"

void cutscene_background(uint8_t *ds, const uint8_t *dfb, uint8_t *screen, uint8_t *palette)
{
    uint16_t packed = DS_U16(dfb, 0);
    memcpy(palette, dfb + 2 + packed, 768);
    bytekiller_unpack(dfb + 2, packed, screen);
    map_clear_key_buffer(ds);
}

void cutscene_apply_frame(const uint8_t *frame, uint8_t *work, uint8_t *screen)
{
    uint16_t packed = DS_U16(frame, 0);
    if (!packed)
        return;
    bytekiller_unpack(frame + 2, packed, work);
    uint16_t at = 2, end = 2 + DS_U16(work, 0);
    while (at < end) {
        uint16_t count = DS_U16(work, at);
        at += 2;
        uint16_t dest = DS_U16(work, at);
        at += 2;
        for (unsigned i = 0; i < count; ++i) {
            screen[dest++] = work[at++];
        }
    }
}

/* B36D: four EGA backgrounds. The source copies 16000 bytes per plane even
 * when a 320x200 asset decodes only 8000; preserve the caller's scratch tail. */
void cutscene_ega_background(Game *g, const uint8_t *dbi, uint8_t *work)
{
    uint16_t at = 0;
    for (unsigned plane = 0; plane < 4; ++plane) {
        ega_seq_mask(g->planes, 1u << plane);
        uint16_t packed = DS_U16(dbi, at);
        at += 2;
        bytekiller_unpack(dbi + at, packed, work);
        for (unsigned i = 0; i < 16000; ++i)
            ega_store(g->planes, (uint16_t)i, work[i]);
        at += packed;
    }
}

/* B3E4: decoded plane sections contain vertical runs. B423 stores stride-1
 * because the original MOVSB already advances DI by one. Valid packets only. */
void cutscene_ega_runs(Game *g, const uint8_t *work, uint16_t stride)
{
    uint16_t at = 0;
    for (unsigned plane = 0; plane < 4; ++plane) {
        ega_seq_mask(g->planes, 1u << plane);
        uint16_t end = at + DS_U16(work, at);
        at += 2;
        while (at != end) {
            uint16_t dest = DS_U16(work, at);
            at += 2;
            uint16_t count = work[at++];
            do {
                ega_store(g->planes, dest, work[at++]);
                dest += stride;
            } while (--count);
        }
    }
}

/* B3BC: decompress one cinematic frame before applying its runs. */
void cutscene_ega_frame(Game *g, const uint8_t *frame, uint8_t *work, uint16_t stride)
{
    bytekiller_unpack(frame + 2, DS_U16(frame, 0), work);
    cutscene_ega_runs(g, work, stride);
}

/* B31C..B365: EGA DCF sequence after background/setup. DB61 extra repeats,
 * DBB3 retraces per frame; buffered key low byte stops after drawing a frame.
 * The platform supplies 0D8D retrace-start and 0DAA retrace-end only. */
int cutscene_ega_sequence(Game *g, const MapResources *platform)
{
    if (!platform || !platform->call)
        return -1;
    uint8_t *ds = g->ds;
    for (;;) {
        uint16_t seg = DS_U16(ds, 0x91BA), at = 2;
        uint16_t count = DS_U16(far_ptr(g, seg, 0), 0);
        do {
            seg = DS_U16(ds, 0x91BA);
            uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
            uint16_t stride = DS_U16(far_ptr(g, code, 0xB423), 0) + 1;
            cutscene_ega_frame(g, far_ptr(g, seg, at), far_ptr(g, DS_U16(ds, DS_WORK_BUFFER_SEG), 0), stride);
            seg = DS_U16(ds, 0x91BA);
            at += DS_U16(far_ptr(g, seg, at), 0) + 2;
            if (DS_U8(ds, DS_KEYBUF_COUNT))
                return 0;
            uint16_t delay = DS_U16(ds, 0xDBB3);
            do {
                if (platform->call(g, 0x0D8D, 0, 0, platform->user) || platform->call(g, 0x0DAA, 0, 0, platform->user))
                    return -1;
            } while (--delay);
        } while (--count);
        if (!DS_U8(ds, 0xDB61))
            return 0;
        DS_U8(ds, 0xDB61)--;
    }
}

/* FA4B copies the terminator and returns its destination address. */
static uint16_t movie_copy_name(uint8_t *ds, uint16_t source, uint16_t dest)
{
    uint8_t ch;
    do {
        ch = DS_U8(ds, source++);
        DS_U8(ds, dest++) = ch;
    } while (ch);
    return dest - 1;
}

static int movie_platform(Game *g, const MapResources *platform, uint16_t op, uint16_t a)
{
    return platform->call(g, op, a, 0, platform->user) ? -1 : 0;
}

/* B210 EGA branch, including filename construction, background, optional ATF
 * overlay and full DCF sequence. Source/work segment offsets must be zero, as
 * required by the original decoder. Valid installed required DBI/DCF files only.
 * The VGA branch is separate. All IO is read-only; palette/retrace are host ops. */
int cutscene_ega_play(Game *g, uint16_t filename, uint16_t width, uint16_t delay, uint16_t variant,
                      const ImageIO *files, const MapResources *platform)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0xADD0) || !files || !files->call || !platform || !platform->call || DS_U16(ds, 0x91B8)
        || DS_U16(ds, DS_WORK_BUFFER))
        return -1;
    map_clear_key_buffer(ds);
    uint16_t at = movie_copy_name(ds, filename, 0xDB8A);
    movie_copy_name(ds, 0xDB62, at);
    at = movie_copy_name(ds, filename, 0xDB97);
    movie_copy_name(ds, 0xDB67, at);
    at = 0xDBA4;
    uint16_t prefix = DS_U16(ds, 0xDB8A);
    if (variant && prefix != 0x796E && prefix != 0x656E && prefix != 0x7374)
        DS_U8(ds, at++) = 't';
    at = movie_copy_name(ds, filename, at);
    movie_copy_name(ds, 0xDB6C, at);
    DS_U16(ds, 0xDBB3) = delay;
    uint16_t mode = 14, stride = 79;
    if (width != 80) {
        width = 40;
        mode = 13;
        stride = 39;
    }
    DS_U16(ds, 0xDBB1) = width;
    DS_U16(far_ptr(g, (uint16_t)(g->ds_seg - 0x5C27), 0xB423), 0) = stride;
    if (movie_platform(g, platform, MS_VIDEO_MODE, mode) || movie_platform(g, platform, MS_DEFAULT_PALETTE, 0))
        return -1;
    uint16_t palette = width == 80 && DS_U8(ds, 0xDB8A) != 'i' ? 0xDB50 : 0x1510;
    if (file_load(g, files, 0xDB8A, DS_U16(ds, 0x91BA), DS_U16(ds, 0x91B8)) == UINT32_MAX)
        return -1;
    cutscene_ega_background(g, far_ptr(g, DS_U16(ds, 0x91BA), 0), far_ptr(g, DS_U16(ds, 0xDE20), 0));
    if (movie_platform(g, platform, 0x0BE8, palette))
        return -1;
    uint32_t opened = file_open_existing(g, files, 0xDBA4);
    if (opened == UINT32_MAX)
        return -1;
    if (!(opened & 0x10000)) {
        uint16_t handle = (uint16_t)opened;
        uint32_t read = files->call(g, IMG_READ, handle, DS_U16(ds, DS_WORK_BUFFER_SEG), DS_U16(ds, DS_WORK_BUFFER),
                                    10000, files->user);
        if (read == UINT32_MAX)
            return -1;
        if (read & 0x10000)
            DS_U16(ds, 0xEA50) = (uint16_t)read;
        uint32_t closed = files->call(g, IMG_CLOSE, handle, 0, 0, 0, files->user);
        if (closed == UINT32_MAX)
            return -1;
        if (closed & 0x10000)
            DS_U16(ds, 0xEA50) = (uint16_t)closed;
        uint16_t saved_source = DS_U16(ds, DS_UNPACK_SRC_SEG), saved_dest = DS_U16(ds, DS_UNPACK_DST_SEG);
        DS_U16(ds, DS_UNPACK_DST_SEG) = DS_U16(ds, 0x91BA);
        DS_U16(ds, DS_UNPACK_SRC_SEG) = DS_U16(ds, DS_WORK_BUFFER_SEG);
        if (image_unpack_shared(g, DS_U16(ds, DS_WORK_BUFFER), DS_U16(ds, 0x91B8), 0) == UINT64_MAX)
            return -1;
        screen_blit_five_planes(g, DS_U16(ds, 0x91BA), DS_U16(ds, 0x91B8), 0x16A8, 20, 55, 40);
        DS_U16(ds, DS_UNPACK_SRC_SEG) = saved_source;
        DS_U16(ds, DS_UNPACK_DST_SEG) = saved_dest;
        map_clear_key_buffer(ds);
    }
    if (file_load(g, files, 0xDB97, DS_U16(ds, 0x91BA), DS_U16(ds, 0x91B8)) == UINT32_MAX)
        return -1;
    return cutscene_ega_sequence(g, platform);
}

/* 14B5:018A: load a whole large file in 65535+1-byte chunks. Preserve the
 * original's FFFF offset for the one-byte read, even with nonzero first offset.
 * Required valid assets only; no file writes occur. */
int movie_load_large(Game *g, const ImageIO *files, uint16_t filename, uint16_t seg, uint16_t offset)
{
    if (!files || !files->call)
        return -1;
    uint32_t result = files->call(g, IMG_OPEN, 2, g->ds_seg, filename, 0, files->user);
    if (result == UINT32_MAX || (result & 0x10000))
        return -1;
    uint16_t handle = (uint16_t)result;
    for (;;) {
        result = files->call(g, IMG_READ, handle, seg, offset, 65535, files->user);
        if (result == UINT32_MAX)
            return -1;
        if ((uint16_t)result != 65535)
            break;
        result = files->call(g, IMG_READ, handle, seg, 65535, 1, files->user);
        if (result == UINT32_MAX)
            return -1;
        if ((uint16_t)result != 1)
            break;
        seg += 0x1000;
        offset = 0;
    }
    return files->call(g, IMG_CLOSE, handle, 0, 0, 0, files->user) == UINT32_MAX ? -1 : 0;
}

/* 14B5:01C2: only ATF's first planar bitmap is used, in palette index FE.
 * Skip three rows and a byte at each side; return original SI | DI<<16. */
uint32_t cutscene_vga_overlay(const uint8_t *mask, uint8_t *screen, uint16_t source, uint16_t dest, uint16_t rows)
{
    source += 120;
    dest += 960;
    rows -= 6;
    unsigned left = rows ? rows : 65536;
    do {
        ++source;
        dest += 8;
        for (unsigned col = 0; col < 38; ++col) {
            uint8_t bits = mask[source++];
            for (unsigned bit = 0; bit < 8; ++bit) {
                if (bits & 128)
                    screen[dest] = 254;
                bits <<= 1;
                ++dest;
            }
        }
        dest += 8;
        ++source;
    } while (--left);
    return source | ((uint32_t)dest << 16);
}

/* 14B5:0093..00E6 only: sequence/repeat/key loop. Normalize the segmented
 * packet pointer before each frame so DFF streams may exceed 64 KB. Final
 * intro bitmap/7242 bookkeeping is outside this entry. */
int cutscene_vga_sequence(Game *g, uint8_t *screen, const MapResources *platform)
{
    if (!platform || !platform->call)
        return -1;
    uint8_t *ds = g->ds;
    for (;;) {
        uint16_t seg = DS_U16(ds, 0x91BA), at = 2;
        uint16_t count = DS_U16(far_ptr(g, seg, 0), 0);
        do {
            seg += (at >> 4);
            at &= 15;
            const uint8_t *frame = far_ptr(g, seg, at);
            cutscene_apply_frame(frame, far_ptr(g, DS_U16(ds, DS_WORK_BUFFER_SEG), 0), screen);
            at += DS_U16(far_ptr(g, seg, at), 0) + 2;
            if (DS_U8(ds, DS_KEYBUF_COUNT))
                return 0;
            uint16_t delay = DS_U16(ds, 0xDBB3);
            do {
                if (platform->call(g, 0x0D8D, 0, 0, platform->user) || platform->call(g, 0x0DAA, 0, 0, platform->user))
                    return -1;
            } while (--delay);
        } while (--count);
        if (!DS_U8(ds, 0xDB61))
            return 0;
        DS_U8(ds, 0xDB61)--;
    }
}

/* 9F17: native VGA full-screen image, with optional in-place 8-to-6-bit palette.
 * The source accepts a loaded LZHUF IMG and always decodes from its +32 bytes. */
int image_vga_load(Game *g, const ImageIO *files, uint16_t filename, uint8_t *screen, uint8_t *palette)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0x7B8C), offset = DS_U16(ds, 0x7B8A);
    if (!seg) {
        seg = DS_U16(ds, DS_FILE_BUFFER_SEG);
        offset = DS_U16(ds, DS_FILE_BUFFER);
    }
    if (file_load(g, files, filename, seg, offset) == UINT32_MAX)
        return -1;
    if (!DS_U8(ds, 0xABC8)) {
        uint16_t at = offset + 32 + DS_U16(far_ptr(g, seg, (uint16_t)(offset + 16)), 0);
        for (unsigned i = 0; i < 768; ++i) {
            uint8_t *value = far_ptr(g, seg, at++);
            *value >>= 2;
            palette[i] = *value;
        }
    }
    uint16_t packed = DS_U16(far_ptr(g, seg, (uint16_t)(offset + 16)), 0);
    unpack_block_linear(g, seg, (uint16_t)(offset + 32), screen, 0, packed, 0);
    return 0;
}

/* Complete 14B5:000A VGA movie path. Mode/presentation and retrace timing are
 * platform services. The host owns 64 KB indexed pixels and the 768-byte DAC.
 * Mode service must initialize its DAC buffer consistently with BIOS mode 13h.
 * Valid installed DFB/DFF/ATF streams and sufficiently large source arena required. */
int cutscene_vga_play(Game *g, uint16_t filename, uint16_t delay, uint16_t variant, uint8_t *screen, uint8_t *palette,
                      const ImageIO *files, const MapResources *platform)
{
    uint8_t *ds = g->ds;
    if (!screen || !palette || !files || !files->call || !platform || !platform->call || DS_U16(ds, 0x91B8)
        || DS_U16(ds, DS_WORK_BUFFER))
        return -1;
    map_clear_key_buffer(ds);
    uint16_t at = movie_copy_name(ds, filename, 0xDB8A);
    movie_copy_name(ds, 0xDB71, at);
    at = movie_copy_name(ds, filename, 0xDB97);
    movie_copy_name(ds, 0xDB76, at);
    at = 0xDBA4;
    uint16_t prefix = DS_U16(ds, 0xDB8A);
    if (variant && prefix != 0x796E && prefix != 0x656E && prefix != 0x7374)
        DS_U8(ds, at++) = 't';
    at = movie_copy_name(ds, filename, at);
    movie_copy_name(ds, 0xDB6C, at);
    DS_U16(ds, 0xDBB3) = delay >> 1;
    if (movie_platform(g, platform, MS_VIDEO_MODE, 19))
        return -1;
    memset(screen, 0, 65536);
    if (file_load(g, files, 0xDB8A, DS_U16(ds, 0x91BA), DS_U16(ds, 0x91B8)) == UINT32_MAX)
        return -1;
    cutscene_background(ds, far_ptr(g, DS_U16(ds, 0x91BA), 0), screen, palette);
    uint32_t opened = files->call(g, IMG_OPEN, 2, g->ds_seg, 0xDBA4, 0, files->user);
    if (opened == UINT32_MAX)
        return -1;
    if (!(opened & 0x10000)) {
        uint16_t handle = (uint16_t)opened;
        if (files->call(g, IMG_READ, handle, DS_U16(ds, DS_WORK_BUFFER_SEG), DS_U16(ds, DS_WORK_BUFFER), 10000,
                        files->user)
            == UINT32_MAX)
            return -1;
        if (files->call(g, IMG_CLOSE, handle, 0, 0, 0, files->user) == UINT32_MAX)
            return -1;
        uint16_t saved_source = DS_U16(ds, DS_UNPACK_SRC_SEG), saved_dest = DS_U16(ds, DS_UNPACK_DST_SEG);
        DS_U16(ds, DS_UNPACK_DST_SEG) = DS_U16(ds, 0x91BA);
        DS_U16(ds, DS_UNPACK_SRC_SEG) = DS_U16(ds, DS_WORK_BUFFER_SEG);
        uint16_t source = DS_U16(ds, DS_WORK_BUFFER),
                 type = DS_U16(far_ptr(g, DS_U16(ds, DS_UNPACK_SRC_SEG), (uint16_t)(source + 12)), 0);
        if (image_unpack_shared(g, source, DS_U16(ds, 0x91B8), (type & 8) != 0) == UINT64_MAX)
            return -1;
        cutscene_vga_overlay(far_ptr(g, DS_U16(ds, 0x91BA), 0), screen, DS_U16(ds, 0x91B8), 0xB540, 55);
        DS_U16(ds, DS_UNPACK_SRC_SEG) = saved_source;
        DS_U16(ds, DS_UNPACK_DST_SEG) = saved_dest;
    }
    if (movie_load_large(g, files, 0xDB97, DS_U16(ds, 0x91BA), DS_U16(ds, 0x91B8)))
        return -1;
    if (DS_U16(ds, 0xDB8A) == 0x6262)
        event_push(EV_SOUND, 30, 0);
    if (cutscene_vga_sequence(g, screen, platform))
        return -1;
    if (!DS_U8(ds, DS_KEYBUF_COUNT) && DS_U16(ds, 0xDB8A) == 0x6E69) {
        DS_U8(ds, 0xABC8) = 255;
        if (image_vga_load(g, files, 0xDB7B, screen, palette))
            return -1;
        DS_U8(ds, 0xABC8) = 0;
    }
    DS_U16(ds, DS_VISIBLE_CELL) = 65535;
    return 0;
}

int cutscene_play(Game *g, uint16_t filename, uint16_t width, uint16_t delay, uint16_t variant,
                  const MovieServices *host)
{
    if (!host)
        return -1;
    if (DS_U8(g->ds, 0xADD0))
        return cutscene_vga_play(g, filename, delay, variant, host->screen, host->palette, host->files, host->platform);
    return cutscene_ega_play(g, filename, width, delay, variant, host->files, host->platform);
}

/* B7B6's movie call has AX=40,BX=8,CX=0. Other scene/modal services are
 * explicitly forwarded, so the native movie can compose with the AI/world loop. */
uint32_t cutscene_opponent_service(Game *g, uint16_t op, uint16_t arg, void *user)
{
    const MovieServices *host = (const MovieServices *)user;
    if (!host)
        return UINT32_MAX;
    if (op == OS_CUTSCENE)
        return cutscene_play(g, arg, 40, 8, 0, host) < 0 ? UINT32_MAX : 0;
    return !host->other || !host->other->call ? UINT32_MAX : host->other->call(g, op, arg, host->other->user);
}
