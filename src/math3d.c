/* Fixed-point rotation helpers and small table builders. */
#include "term.h"

/* Angles run 0..511 for a full circle. The table holds Q15 sines; the original doubles each
 * coordinate first (ADD AX,AX), so the high word of the product is coordinate * sine.
 * The doubling wraps for |coordinate| >= 16384, exactly as in the original. */
static inline int16_t sine(const uint8_t *ds, uint16_t angle)
{
    return DS_I16(ds, DS_SINE_TABLE + 2 * angle);
}

static inline int16_t cosine(const uint8_t *ds, uint16_t angle)
{
    return DS_I16(ds, DS_SINE_TABLE + 0x100 + 2 * angle);
}

/* orig 0000:1B7D   in AX=x CX=z DX=angle   out AX=x*cos - z*sin, CX=x*sin + z*cos */
void rotate_xz(const uint8_t *ds, int16_t *x, int16_t *z, uint16_t angle)
{
    int16_t s = sine(ds, angle), c = cosine(ds, angle);
    int16_t x2 = (int16_t)(*x * 2), z2 = (int16_t)(*z * 2);
    int16_t nx = (int16_t)(mul_hi(x2, c) - mul_hi(z2, s));
    int16_t nz = (int16_t)(mul_hi(x2, s) + mul_hi(z2, c));
    *x = nx;
    *z = nz;
}

/* orig 0000:1BB0   the opposite turn: AX=x*cos + z*sin, CX=-x*sin + z*cos */
void rotate_xz_inverse(const uint8_t *ds, int16_t *x, int16_t *z, uint16_t angle)
{
    int16_t s = sine(ds, angle), c = cosine(ds, angle);
    int16_t x2 = (int16_t)(*x * 2), z2 = (int16_t)(*z * 2);
    int16_t nx = (int16_t)(mul_hi(x2, c) + mul_hi(z2, s));
    int16_t nz = (int16_t)(mul_hi(x2, (int16_t)-s) + mul_hi(z2, c));
    *x = nx;
    *z = nz;
}

/* orig 0000:1B46   same as rotate_xz_inverse but on the BX/CX pair (AX is preserved) */
void rotate_bc(const uint8_t *ds, int16_t *b, int16_t *c_, uint16_t angle)
{
    rotate_xz_inverse(ds, b, c_, angle);
}

/* orig 0000:1BE5   same as rotate_xz_inverse but on the AX/BX pair (CX is preserved) */
void rotate_ab(const uint8_t *ds, int16_t *a, int16_t *b, uint16_t angle)
{
    rotate_xz_inverse(ds, a, b, angle);
}

/* ---------------------------------------------------------------- 3 x 3 rotation matrix
 * Nine Q15 words at DS:4164, row by row; a second set at DS:4176 is the workspace the
 * original builds new rows in (and it is left as the original leaves it). */
enum {
    MX = 0x4164,
    MX_WORK = 0x4176
};

/* IMUL / ADD AX,AX / RCL DX,1: the product of two Q15 numbers, as a Q15 number */
static inline int16_t q15(int16_t a, int16_t b)
{
    return (int16_t)(((int32_t)a * b) >> 15);
}

static void copy_words_ds(uint8_t *ds, uint16_t to, uint16_t from, int words)
{
    for (int i = 0; i < words; i++)
        DS_U16(ds, (uint16_t)(to + 2 * i)) = DS_U16(ds, (uint16_t)(from + 2 * i));
}

/* orig 0000:1CA7 */
static void matrix_identity(uint8_t *ds)
{
    for (int i = 0; i < 9; i++)
        DS_U16(ds, MX + 2 * i) = (i % 4 == 0) ? 0x7FFF : 0;
    copy_words_ds(ds, MX_WORK, MX, 9);
}

/* The three rotations below each combine two rows of the matrix:
 *     first'  = cos * first + s1 * second
 *     second' = s2 * first  + cos * second
 * `to_first` / `to_second` are where the new rows are built in the workspace. */
static void matrix_mix_rows(uint8_t *ds, int first, int second, int16_t c, int16_t s1, int16_t s2, int to_first,
                            int to_second)
{
    for (int k = 0; k < 3; k++)
        DS_I16(ds, MX_WORK + 2 * (to_first + k)) =
            (int16_t)(q15(c, DS_I16(ds, MX + 2 * (first + k))) + q15(s1, DS_I16(ds, MX + 2 * (second + k))));
    for (int k = 0; k < 3; k++)
        DS_I16(ds, MX_WORK + 2 * (to_second + k)) =
            (int16_t)(q15(s2, DS_I16(ds, MX + 2 * (first + k))) + q15(c, DS_I16(ds, MX + 2 * (second + k))));
}

/* orig 0000:1C1A (with 1CA7, 1E76, 1DA9, 1CDC)   in AX, BX, CX = three angles (0..511)
 * Builds the matrix: identity, turned by BX (rows 0 and 2), then AX (rows 1 and 2), then CX
 * (rows 0 and 1). */
void matrix_from_angles(uint8_t *ds, uint16_t ax, uint16_t bx, uint16_t cx)
{
    int16_t c, s;
    matrix_identity(ds);

    c = cosine(ds, bx); /* orig 0000:1E76 */
    s = sine(ds, bx);
    matrix_mix_rows(ds, 0, 6, c, (int16_t)-s, (int16_t)-(int16_t)-s, 0, 6);
    copy_words_ds(ds, MX, MX_WORK, 3);
    copy_words_ds(ds, MX + 12, MX_WORK + 12, 3);

    c = cosine(ds, ax); /* orig 0000:1DA9 */
    s = sine(ds, ax);
    matrix_mix_rows(ds, 3, 6, c, s, (int16_t)-s, 3, 6);
    copy_words_ds(ds, MX + 6, MX_WORK + 6, 6);

    c = cosine(ds, cx); /* orig 0000:1CDC */
    s = sine(ds, cx);
    matrix_mix_rows(ds, 0, 3, c, s, (int16_t)-s, 0, 3);
    copy_words_ds(ds, MX, MX_WORK, 6);
}

/* orig 0000:1C33   in AX, BX, CX = a point   out AX, BX, CX = the matrix applied to it.
 * Each coordinate is doubled first (wrapping), as in the 2D rotations. The point is also
 * left in the scratch words at DS:3CD6. */
void matrix_apply(uint8_t *ds, int16_t *x, int16_t *y, int16_t *z)
{
    DS_I16(ds, 0x3CD6) = *x;
    DS_I16(ds, 0x3CD8) = *y;
    DS_I16(ds, 0x3CDA) = *z;
    int16_t x2 = (int16_t)(*x * 2), y2 = (int16_t)(*y * 2), z2 = (int16_t)(*z * 2);
    int16_t out[3];
    for (int r = 0; r < 3; r++)
        out[r] = (int16_t)(mul_hi(x2, DS_I16(ds, MX + 6 * r)) + mul_hi(y2, DS_I16(ds, MX + 6 * r + 2))
                           + mul_hi(z2, DS_I16(ds, MX + 6 * r + 4)));
    *x = out[0];
    *y = out[1];
    *z = out[2];
}

/* orig 0000:1F50   colours 16..135 are 50% dithers of two EGA colours: every pair a < b */
void build_dither_table(uint8_t *ds)
{
    uint16_t off = DS_DITHER_PAIRS;
    for (unsigned a = 0; a < 15; a++) {
        for (unsigned b = a + 1; b <= 15; b++) {
            DS_U16(ds, off) = (uint16_t)(b | (a << 8));
            off += 2;
        }
    }
}
