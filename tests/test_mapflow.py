"""Original map entry/exit with scripted taps, to verify the emulator test route.

This tests original UI flow; it does not claim C has replaced map setup or input dispatch.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import dosemu
from unicorn import UC_HOOK_CODE

CASES = 0


def run(ctx):
    global CASES
    fails = []
    for start, mode in [('local_map', 0x0D), ('area_map', 0x10)]:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out', 'emu', 'states', start + '.pkl'))
        CASES += 1
        if m.vga.mode != mode:
            fails.append(f'{start}: wrong starting video mode')
        frames = [0]

        def scene_done(uc, address, size, ud):
            frames[0] += 1

        at = (dosemu.LOAD_SEG << 4) + 0x0752
        m.uc.hook_add(UC_HOOK_CODE, scene_done, None, at, at)
        m.press(m.ticks + 2, 'esc', hold=1)
        reason = m.run(ticks=20)
        CASES += 1
        if reason != 'ticks' or frames[0] < 2:
            fails.append(f'{start}: no return to live frames ({frames[0]} frames, {reason})')
        CASES += 1
        if m.vga.mode != 0x0D or len(set(m.vga.attr[:16])) < 8:
            fails.append(f'{start}: video mode/palette not restored')
        shot = m.vga.screenshot()
        CASES += 1
        if not shot or not any(shot[2]):
            fails.append(f'{start}: visible page is black')
        print(f'    {start}: {frames[0]} live scene frames after Escape tap')
    # A held exit key reaches pause while 7A28's blank palette is still active.
    # Exiting pause allows the first gameplay frame to run 0214 and unblank it.
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/local_map.pkl'))
    menu_hits = [0]
    def menu(uc, address, size, ud):
        menu_hits[0] += 1
    at = (dosemu.LOAD_SEG << 4) + 0x4A96
    m.uc.hook_add(UC_HOOK_CODE, menu, None, at, at)
    m.press(m.ticks + 2, 'esc', hold=4)
    m.run(ticks=10)
    CASES += 1
    if not menu_hits[0] or any(m.vga.attr[:16]) or not m.ds_read(0x01DD, 1)[0]:
        fails.append('held map exit: expected pause before deferred palette restoration')
    m.press(m.ticks + 2, 'esc', hold=1)
    reason = m.run(ticks=20)
    CASES += 1
    if reason != 'ticks' or len(set(m.vga.attr[:16])) < 8 or m.ds_read(0x01DD, 1)[0]:
        fails.append('held map exit: dismissing pause did not restore normal palette/frame state')
    CASES += 1
    shot = m.vga.screenshot()
    if not shot or not any(shot[2]):
        fails.append('held map exit: recovered display remains black')
    print('    held Escape exit: early blank pause dismissed; deferred palette restoration completed')
    return fails
