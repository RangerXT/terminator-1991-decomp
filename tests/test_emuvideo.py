"""DOS/bulk writes to A000 must reach the modeled card, including range overlap."""
import io
import dosemu
CASES = 0

def run(ctx):
    global CASES
    for start, count in [(0xA0000, 16), (0x9FFFC, 12), (0xAFFFC, 12)]:
        m = dosemu.Machine()
        m.w(dosemu.UC_X86_REG_AX, 19)
        m._video()
        payload = bytes(range(1, count+1))
        m.wb(start>>4, start&15, payload)
        CASES += 1
        lo = max(start, 0xA0000)
        hi = min(start+count, 0xB0000)
        if bytes(m.vga.chunky[lo-0xA0000:hi-0xA0000]) != payload[lo-start:hi-start]:
            return ['bulk video overlap %05x'%start]
        if bytes(m.uc.mem_read(start, count)) != payload:
            return ['bulk RAM backing changed']
    m = dosemu.Machine()
    m._via_stub = False
    m.w(dosemu.UC_X86_REG_AX, 19)
    m._video()
    payload = bytes((j*37)&255 for j in range(64000))
    m.files[6] = [io.BytesIO(payload), 'diagnostic-read-only']
    for reg, val in [(dosemu.UC_X86_REG_AX, 0x3F00), (dosemu.UC_X86_REG_BX, 6), (dosemu.UC_X86_REG_CX, 64000), (dosemu.UC_X86_REG_DS, 0xA000), (dosemu.UC_X86_REG_DX, 0)]:
        m.w(reg, val)
    m._dos()
    CASES += 1
    if m.r(dosemu.UC_X86_REG_AX) != 64000 or bytes(m.vga.chunky[:64000]) != payload:
        return ['DOS read failed to update VGA pixels']
    m = dosemu.Machine()
    m.w(dosemu.UC_X86_REG_AX, 13)
    m._video()
    m.vga.seq[2] = 4
    m.vga.gc[8] = 0xF0
    m.wb(0xA000, 0, bytes([0xA5]))
    CASES += 1
    if [p[0] for p in m.vga.planes] != [0, 0, 0xA0, 0]:
        return ['bulk EGA card semantics lost']
    return []
