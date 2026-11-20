/* Perspective projection of the working vertex buffer. */
#include "term.h"

/* One coordinate: (v * 256) / depth, as the original computes it.
 *
 * The dividend is built with CWD / MOV DL,AH / MOV AH,AL, which leaves AL in the low byte
 * instead of clearing it, so it is v*256 + (v & 0xFF). The divisor is used as a signed
 * word. If the quotient does not fit in 16 bits the CPU raises a divide error; while
 * projecting, the game's handler (0000:481A) replaces the result with 0x7E6F for a
 * non-negative v and 0x8190 for a negative one.
 *
 * (Whether a quotient of exactly -32768 faults depends on the CPU; this follows the 386
 * and the emulator, where it does not.)
 */
static int16_t project_coord(int16_t v, uint16_t depth)
{
    int32_t num = (int32_t)(((uint32_t)(v < 0 ? 0xFFu : 0u) << 24) | ((uint32_t)(uint8_t)((uint16_t)v >> 8) << 16)
                            | ((uint32_t)(uint8_t)v << 8) | (uint32_t)(uint8_t)v);
    int32_t q = num / (int16_t)depth;
    if (q > 32767 || q < -32768)
        return (int16_t)(v < 0 ? 0x8190 : 0x7E6F);
    return (int16_t)q;
}

/* orig 0000:4772   in AX = x, BX = y, CX = depth (z + 40)   out AX, BX
 * One point: the depth is halved once for each active zoom (not in ground pass 2) and
 * never taken below 30. */
void project_point(const uint8_t *ds, int16_t *x, int16_t *y, uint16_t depth)
{
    if (DS_U8(ds, DS_GROUND_PASS) != 2) {
        if (DS_U8(ds, DS_ZOOM_1))
            depth >>= 1;
        if (DS_U8(ds, DS_ZOOM_2))
            depth >>= 1;
    }
    if (depth < 0x1E)
        depth = 0x1E;
    *x = project_coord(*x, depth);
    *y = project_coord(*y, depth);
}

/* orig 0000:46AC (with the per-vertex helper 0000:4772)   out: carry flag
 *
 * Projects every vertex of the 3D buffer (DS:[3CDC] up to DS:[4B86]) that is in front of the
 * camera into the 2D buffer (DS:[40DE], same 6-byte stride: x, y, unused):
 *
 *      depth = z + 40, halved once for each active zoom (DS:114D, DS:114F; not in ground
 *              pass 2), never less than 30
 *      sx = x * 256 / depth + centre_x (DS:0408)
 *      sy = y * 256 / depth + centre_y (DS:040A)
 *
 * so the focal length is 256 pixels. Vertices with z < 0 are left unprojected.
 * It also classifies each projected point against the view window (DS:03F4..03FA) and
 * returns 1 (carry set in the original) when the object cannot be visible: no point inside
 * the window, not spanning it left-to-right, and nothing above or below it.
 */
int project_vertices(uint8_t *ds)
{
    uint16_t src = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    uint16_t dst = DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR);
    uint16_t end = DS_U16(ds, DS_VERTEX_BUFFER_END);

    DS_U8(ds, DS_ANY_POINT_INSIDE) = 0;
    DS_U8(ds, DS_OUTCODE_UNION) = 0;

    while (src != end) {
        int16_t x = DS_I16(ds, src), y = DS_I16(ds, (uint16_t)(src + 2)), z = DS_I16(ds, (uint16_t)(src + 4));
        src = (uint16_t)(src + 6);
        if (z < 0) {
            dst = (uint16_t)(dst + 6);
            continue;
        }
        project_point(ds, &x, &y, (uint16_t)(z + 0x28));
        int16_t sx = (int16_t)(x + DS_I16(ds, DS_VIEW_CENTRE_X));
        int16_t sy = (int16_t)(y + DS_I16(ds, DS_VIEW_CENTRE_Y));
        DS_I16(ds, dst) = sx;
        DS_I16(ds, (uint16_t)(dst + 2)) = sy;
        dst = (uint16_t)(dst + 6);

        uint8_t code = 0;
        if (sx < DS_I16(ds, DS_VIEW_LEFT))
            code |= 1;
        if (sx > DS_I16(ds, DS_VIEW_RIGHT))
            code |= 2;
        if (sy < DS_I16(ds, DS_VIEW_TOP))
            code |= 4;
        if (sy > DS_I16(ds, DS_VIEW_BOTTOM))
            code |= 8;
        if (code == 0)
            DS_U8(ds, DS_ANY_POINT_INSIDE) = 8;
        else
            DS_U8(ds, DS_OUTCODE_UNION) |= code;
    }

    if (DS_U8(ds, DS_ANY_POINT_INSIDE))
        return 0;
    uint8_t all = DS_U8(ds, DS_OUTCODE_UNION);
    if ((all & 3) == 3)
        return 0;
    if (all & 0x0C)
        return 0;
    return 1;
}
