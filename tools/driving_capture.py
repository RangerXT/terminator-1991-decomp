"""Prepare vehicle mode through original 02B5, then record actual 3269 game-loop calls.
Uses real image resources and source 5EF7 alternate vehicle configuration; the script
selects drive (gear key Home) after starting. Audio group/sound/border are external.
CPU context is restored after the preparation call so gameplay resumes its saved site.
"""
import os, struct, gzip, pickle
import capture, dosemu


def main():
    m = dosemu.Machine()
    m.load(os.path.join(capture.STATES, 'ingame.pkl'))
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    p = m.rw(m.DATA_SEG, 0x03A0)
    m.ds_write(0x5BD9, bytes(0x59))
    m.key_events = []
    m.kbd_queue = []
    word(0x5BD4, 0)
    for off in [0x8A9E, 0x89A2, 0x0A4F]:
        m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
    m.ds_write(0x5EF7, bytes([255]))
    word(0x5F76, 30000)
    word(0x5F72, 100)
    word(p+26, 0)
    word(p+28, 1000)
    m.ds_write(0x0345, bytes([255]))
    context = m.uc.context_save()
    cs, ip = m.cs, m.ip
    m.call(0, 0x02B5, bx=2, max_instr=50_000_000)
    if not m.ds_read(p+14, 1)[0]&2:
        raise SystemExit('Original vehicle entry did not set vehicle flag')
    m.uc.context_restore(context)
    m.cs, m.ip = cs, ip
    m.pending = None
    word(0x7242, 65535)
    m.ds_write(0x50B0, bytes([255]))
    word(p+48, 30000)
    start = 'driving_controls'
    m.save(os.path.join(capture.STATES, start+'.pkl'))
    keys = '2:s:10,14:home:10,18:up:20,40:right:10,54:down:10,68:rshift:10,68:rbracket:10,84:left:10'
    n = capture.record(0, 0x3269, 'driving_live', count=48, skip=1, start=start, ticks=180, keys=keys)
    if n != 48:
        raise SystemExit('Not enough original driving updates: %d'%n)
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'driving_live.pkl.gz'), 'rb'))
    if len({st['trace_frame'] for st in caps}) < 24:
        raise SystemExit('Recording did not advance game frames')
    print('Driving frames:', len({st['trace_frame'] for st in caps}))

if __name__ == '__main__':
    main()
