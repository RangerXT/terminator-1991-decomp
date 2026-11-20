/* The scalable bitmap font (font.pck): loading it and scaling it to a size,
 * 11BC:28F8 and 11BC:2714 with 27D0 / 281E. The ratings screen and five others use it.
 *
 * A font is glyphs of src_rows x src_width pixels, rows padded to whole bytes, one after the
 * other in the work buffer (segment DS:ADE8, from offset DS:ADE6). Scaling writes glyphs of
 * dst_rows x dst_width behind it (segment DS:AE00, from DS:ADFE = the file size): each
 * source row is repeated dst_rows / src_rows times, plus once more whenever the remainders
 * add up past src_rows; pixels the same way across. Then the 88 character widths at DS:AEC3
 * are scaled into DS:AE64 (rounded up from 40/256), and DS:AE02 into DS:AE03 (with the DX
 * the table left in its dividend).
 */
#include "term.h"

enum {
    FS_SIZE = 0xADFE, /* u16: bytes loaded; the scaled glyphs start there */
    FS_SOURCE_SEG = 0xADE8,
    FS_SOURCE = 0xADE6,
    FS_DEST_SEG = 0xAE00,
    FS_SRC = 0xADF4,        /* u8 rows, u8 width of the source glyphs */
    FS_DST = 0xADF6,        /* u8 rows, u8 width of the scaled glyphs */
    FS_ROW_REPEAT = 0xADEE, /* dst_rows / src_rows */
    FS_ROW_REST = 0xADF0,   /* dst_rows % src_rows */
    FS_COL_REPEAT = 0xADEA, /* dst_width / src_width */
    FS_COL_REST = 0xADEC,   /* dst_width % src_width */
    FS_SRC_ROW_BYTES = 0xADF2,
    FS_SRC_GLYPH = 0xADF8,
    FS_DST_ROW_BYTES = 0xADE2,
    FS_DST_GLYPH = 0xADFA,
    FS_ROWS_LEFT = 0xADE1,
    FS_BIT_COUNT = 0xADE3,
    FS_PIXEL = 0xADDF,   /* FF while the current source pixel is set */
    FS_FLUSHED = 0xADDE, /* the last pixel written completed a byte */
};

/* orig 11BC:28F8   load the font file (name at DS:filename) into the work buffer; on an open
 * failure nothing changes. Returns -1 when the file service is missing. */
int font_load(Game *g, const ImageIO *io, uint16_t filename)
{
    uint8_t *ds = g->ds;
    if (!io || !io->call)
        return -1;
    uint32_t opened = io->call(g, IMG_OPEN, 0, g->ds_seg, filename, 0, io->user);
    if (opened == UINT32_MAX)
        return -1;
    if (opened & 0x10000)
        return 0;
    uint16_t handle = (uint16_t)opened;
    uint32_t read =
        io->call(g, IMG_READ, handle, DS_U16(ds, DS_WORK_BUFFER_SEG), DS_U16(ds, DS_WORK_BUFFER), 0xFFFF, io->user);
    if (read == UINT32_MAX || io->call(g, IMG_CLOSE, handle, 0, 0, 0, io->user) == UINT32_MAX)
        return -1;
    DS_U16(ds, FS_SIZE) = (uint16_t)read;
    DS_U16(ds, FS_SOURCE_SEG) = DS_U16(ds, FS_DEST_SEG) = DS_U16(ds, DS_WORK_BUFFER_SEG);
    DS_U16(ds, FS_SOURCE) = 0;
    return 0;
}

/* orig 11BC:281E   one scaled row from the source row at *si to *di */
static void scale_row(Game *g, uint16_t si, uint16_t *di, uint8_t *ah)
{
    uint8_t *ds = g->ds;
    uint8_t *source = far_ptr(g, DS_U16(ds, FS_SOURCE_SEG), 0), *dest = far_ptr(g, DS_U16(ds, FS_DEST_SEG), 0);
    uint8_t width = DS_U8(ds, FS_DST + 1), src_width = DS_U8(ds, FS_SRC + 1), rest = DS_U8(ds, FS_COL_REST);
    uint8_t left = width, accumulated = 0, bits = 0, count;
    unsigned filled = 0;
    DS_U8(ds, FS_BIT_COUNT) = 8;
    for (;;) {
        DS_U8(ds, FS_PIXEL) = 0;
        if (DS_U8(ds, FS_BIT_COUNT) == 8) {
            DS_U8(ds, FS_BIT_COUNT) = 0;
            bits = source[si++];
        }
        DS_U8(ds, FS_BIT_COUNT)++;
        if (bits & 0x80)
            DS_U8(ds, FS_PIXEL) = 0xFF;
        bits = (uint8_t)(bits << 1);
        count = DS_U16(ds, FS_COL_REPEAT) ? DS_U8(ds, FS_COL_REPEAT) : 0;
        for (;;) {
            if (count) { /* write the pixel count times */
                for (;;) {
                    DS_U8(ds, FS_FLUSHED) = 0;
                    uint8_t pixel = DS_U8(ds, FS_PIXEL);
                    DS_U8(ds, FS_PIXEL) = (uint8_t)((pixel << 1) | (pixel >> 7));
                    *ah = (uint8_t)((*ah << 1) | (pixel >> 7));
                    if (++filled == 8) {
                        filled = 0;
                        dest[(*di)++] = *ah;
                        *ah = 0;
                        DS_U8(ds, FS_FLUSHED) = 1;
                    }
                    if (!--left)
                        goto done;
                    if (!--count)
                        break;
                }
            }
            accumulated = (uint8_t)(accumulated + rest);
            if (accumulated < src_width)
                break; /* the next source pixel */
            accumulated = (uint8_t)(accumulated - src_width);
            count = 1; /* once more */
        }
    }
done:
    if (!DS_U8(ds, FS_FLUSHED)) {
        *ah = (uint8_t)(*ah << (8 - filled));
        dest[(*di)++] = *ah;
    }
}

/* orig 11BC:27D0   one scaled glyph from si to di */
static void scale_glyph(Game *g, uint16_t si, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint8_t ah = 0, rest = DS_U8(ds, FS_ROW_REST), accumulated = 0, src_rows = DS_U8(ds, FS_SRC);
    DS_U8(ds, FS_ROWS_LEFT) = DS_U8(ds, FS_DST);
    do {
        for (uint8_t repeat = DS_U8(ds, FS_ROW_REPEAT); repeat; --repeat) {
            scale_row(g, si, &di, &ah);
            if (!--DS_U8(ds, FS_ROWS_LEFT))
                return;
        }
        accumulated = (uint8_t)(accumulated + rest);
        if (accumulated >= src_rows) {
            scale_row(g, si, &di, &ah);
            accumulated = (uint8_t)(accumulated - src_rows);
            DS_U8(ds, FS_ROWS_LEFT)--;
        }
        si = (uint16_t)(si + DS_U16(ds, FS_SRC_ROW_BYTES));
    } while (DS_U8(ds, FS_ROWS_LEFT));
}

/* A width scaled: (width * 256 / src_width) * dst_width / 256, rounded up from 40/256. high
 * is DX before the division; *dx_out gets DX after the multiplication. */
static uint8_t scale_width(uint8_t *ds, uint8_t width, uint16_t high, uint16_t *dx_out)
{
    uint32_t dividend = (uint32_t)high << 16 | (uint32_t)width << 8;
    uint16_t quotient = (uint16_t)(dividend / DS_U8(ds, FS_SRC + 1)); /* above 0xFFFF: #DE in the original */
    uint32_t product = (uint32_t)quotient * DS_U8(ds, FS_DST + 1);
    *dx_out = (uint16_t)(product >> 16);
    uint8_t ah = (uint8_t)(product >> 8);
    return (uint8_t)product >= 0x28 ? (uint8_t)(ah + 1) : ah;
}

/* orig 11BC:2714   scale count glyphs: src = (rows | width << 8), dst likewise; from si
 * (in the source segment) to di (in the destination segment) */
void font_scale(Game *g, uint16_t src, uint16_t dst, uint16_t count, uint16_t si, uint16_t di)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, FS_SRC) = src;
    DS_U16(ds, FS_DST) = dst;
    uint8_t src_rows = (uint8_t)src, src_width = (uint8_t)(src >> 8);
    uint8_t dst_rows = (uint8_t)dst, dst_width = (uint8_t)(dst >> 8);
    DS_U16(ds, FS_ROW_REPEAT) = (uint16_t)(dst_rows / src_rows);
    DS_U16(ds, FS_ROW_REST) = (uint16_t)(dst_rows % src_rows);
    DS_U16(ds, FS_COL_REPEAT) = (uint16_t)(dst_width / src_width);
    DS_U16(ds, FS_COL_REST) = (uint16_t)(dst_width % src_width);
    uint8_t src_row_bytes = (uint8_t)((uint8_t)(src_width + 7) >> 3);
    DS_U16(ds, FS_SRC_ROW_BYTES) = src_row_bytes;
    DS_U16(ds, FS_SRC_GLYPH) = (uint16_t)(src_rows * src_row_bytes);
    uint8_t dst_row_bytes = (uint8_t)((uint8_t)(dst_width + 7) >> 3);
    DS_U8(ds, FS_DST_ROW_BYTES) = dst_row_bytes;
    DS_U16(ds, FS_DST_GLYPH) = (uint16_t)(dst_rows * dst_row_bytes);
    do { /* LOOP: a count of 0 means 65536 */
        scale_glyph(g, si, di);
        si = (uint16_t)(si + DS_U16(ds, FS_SRC_GLYPH));
        di = (uint16_t)(di + DS_U16(ds, FS_DST_GLYPH));
    } while (--count);
    uint16_t dx = 0;
    for (unsigned i = 0; i < 0x58; ++i)
        DS_U8(ds, (uint16_t)(0xAE64 + i)) = scale_width(ds, DS_U8(ds, (uint16_t)(0xAEC3 + i)), 0, &dx);
    /* this one has no XOR DX,DX: the last multiplication's DX is part of the dividend */
    DS_U8(ds, 0xAE03) = scale_width(ds, DS_U8(ds, 0xAE02), dx, &dx);
}

/* orig 11BC:2682 (with 28B0 / 28E4)   the string at DS:text in the scaled font at pixel x,
 * row y of the EGA screen (stride DS:1228, from offset 0) in DS:E40F's colour, through
 * set/reset and the bit mask. A space advances DS:AE03; other characters map to a glyph
 * through DS:AE05 and advance their width DS:AE64. Returns the x after the string.
 * The teardown writes AX = 08FF to 3CE (index 15 := 8) instead of FF08, so the bit mask is
 * left as the last glyph byte set it; set/reset and the rotate are cleared. */
uint16_t font_text(Game *g, uint16_t x, uint16_t y, uint16_t text)
{
    uint8_t *ds = g->ds, *p = g->planes;
    uint8_t *glyphs = far_ptr(g, DS_U16(ds, FS_DEST_SEG), 0);
    DS_U16(ds, 0xADFC) = x;
    /* orig 11BC:28B0 */
    ega_seq_mask(p, 15);
    uint16_t row0 = (uint16_t)(y * DS_U16(ds, 0x1228));
    DS_U8(ds, 0xADE0) = (uint8_t)(x & 7);
    ega_gc(p, 1, 15);
    ega_gc(p, 0, DS_U8(ds, DS_TEXT_COLOUR));
    ega_gc(p, 3, 0);
    ega_gc(p, 5, 0);
    ega_gc_select(p, 8);
    for (uint8_t ch; (ch = DS_U8(ds, text++)) != 0;) {
        uint16_t at = (uint16_t)(row0 + (DS_U16(ds, 0xADFC) >> 3));
        uint8_t shift = (uint8_t)(DS_U16(ds, 0xADFC) & 7);
        DS_U8(ds, 0xADE0) = shift;
        uint8_t code = (uint8_t)(ch - 0x20);
        if (!code) {
            DS_U16(ds, 0xADFC) = (uint16_t)(DS_U16(ds, 0xADFC) + DS_U8(ds, 0xAE03));
            continue;
        }
        uint16_t source = (uint16_t)(DS_U16(ds, FS_SIZE)
                                     + (uint16_t)(DS_U8(ds, (uint16_t)(0xAE05 + code)) * DS_U8(ds, FS_DST_GLYPH)));
        DS_U16(ds, 0xADFC) = (uint16_t)(DS_U16(ds, 0xADFC) + DS_U8(ds, (uint16_t)(0xAE64 + code)));
        uint16_t rows = DS_U8(ds, FS_DST); /* LOOP: 0 means 65536 */
        do {
            uint16_t to = at;
            uint8_t bytes = DS_U8(ds, FS_DST_ROW_BYTES); /* DEC BL: 0 means 256 */
            do {
                uint16_t bits = (uint16_t)(glyphs[source++] << 8 >> shift); /* ROR AX,CL with AH = 0 */
                bits = (uint16_t)((bits >> 8) | (bits << 8));               /* AL = left part, AH = right */
                ega_gc_data(p, (uint8_t)bits);
                ega_store(p, to, ega_load(p, to));
                ega_gc_data(p, (uint8_t)(bits >> 8));
                ega_store(p, (uint16_t)(to + 1), ega_load(p, (uint16_t)(to + 1)));
                to = (uint16_t)(to + 1); /* the right part's byte is the next one's left */
            } while (--bytes);
            at = (uint16_t)(at + DS_U16(ds, 0x1228));
        } while (--rows);
    }
    /* orig 11BC:28E4 */
    ega_gc(p, 15, 8);
    ega_gc(p, 1, 0);
    ega_gc(p, 3, 0);
    return DS_U16(ds, 0xADFC);
}
