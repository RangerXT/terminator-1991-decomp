/* Which way a projected polygon faces. */
#include "term.h"

/* orig 11BC:175F   in AX = a, CX = c (magnitudes)   out AX
 * A coarse, monotonic code for the ratio a/c that needs one 16-bit division:
 *   a <  c : (a * 256) / c            0 .. 255
 *   a == c : 0x3FFF
 *   a >  c : 0x7FFF - (c * 256) / a   0x7F00 .. 0x7FFF
 */
static uint16_t slope_code(uint16_t a, uint16_t c)
{
    if (a == c)
        return 0x3FFF;
    if (a < c)
        return (uint16_t)(((uint32_t)a << 8) / c);
    return (uint16_t)(0x7FFF - (uint16_t)(((uint32_t)c << 8) / a));
}

/* 0 or 1 for the quadrant pairs the original numbers 1,0 / 2,3 */
static int quadrant(int16_t x, int16_t y)
{
    if (x >= 0)
        return y >= 0 ? 1 : 0;
    return y >= 0 ? 2 : 3;
}

static uint16_t magnitude(int16_t v)
{
    uint16_t m = (uint16_t)(v < 0 ? -v : v); /* -32768 stays 0x8000, as NEG leaves it */
    return m ? m : 1;
}

/* orig 11BC:168B   in AX,BX = first edge vector (x, y), CX,DX = second edge vector   out AL
 *
 * Returns the sign of the 2D cross product of two screen-space edge vectors without
 * multiplying: first by comparing quadrants, and only when the vectors share a quadrant
 * (or are opposite) by comparing slope codes. The caller (11BC:159C) feeds it the edges
 * v0-v1 and v2-v1 of a projected face (vertices 0, 1, 2 of the face list) and stores the
 * result as the face's "hidden" flag.
 */
uint8_t face_is_hidden(int16_t ax, int16_t bx, int16_t cx, int16_t dx)
{
    if (bx == 0 && dx == 0)
        return 0;
    int q1 = quadrant(ax, bx), q2 = quadrant(cx, dx);
    int d = q1 - q2;
    if (d == 1 || d == -3)
        return 0;
    if (d == -1 || d == 3)
        return 1;
    int same_quadrant = (d == 0);
    uint16_t a = magnitude(ax), b = magnitude(bx), c = magnitude(cx), e = magnitude(dx);
    if (q1 & 1) {
        uint16_t t = a;
        a = b;
        b = t;
        t = c;
        c = e;
        e = t;
    }
    int16_t diff = (int16_t)(slope_code(a, b) - slope_code(c, e));
    if (diff > 0)
        return same_quadrant ? 0 : 1;
    return same_quadrant ? 1 : 0;
}
