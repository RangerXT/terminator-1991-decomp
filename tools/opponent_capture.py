"""Prepare an automated nearby on-foot opponent and record actual BC68 calls.
The encounter positions/attack counters are prepared. The original update/render
loop then chooses when to call BC68; sound/border bodies remain external boundaries.
"""
import argparse, gzip, os, pickle, struct
import capture, dosemu

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=12)
    ap.add_argument('--ticks', type=int, default=400)
    args = ap.parse_args()
    m = dosemu.Machine()
    m.load(os.path.join(capture.STATES, 'ingame.pkl'))
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    player = m.rw(m.DATA_SEG, 0x03A0)
    other = 0x4D4 if player == 0x508 else 0x508
    word(0x04BA, other)
    for axis, base in enumerate([34, 42]):
        value = struct.unpack('<I', m.ds_read(player+base, 4))[0]+200
        m.ds_write(other+base, struct.pack('<I', value))
        word(other+(32 if axis else 30), value//1024)
        word(other+(4 if axis else 0), (1024-value%1024) if axis else value%1024)
    for actor in [player, other]:
        m.ds_write(actor+14, bytes([1]))
        word(actor+26, 0)
        word(actor+28, 200)
    word(other+10, 10)
    word(other+12, 10)
    for o, v in [(0x0345, 0), (0x1152, 0), (0x1153, 255), (0x034B, 0), (0x034E, 0), (0x034F, 0), (0xB69F, 200), (0xAA83, 0),
                (0x0359, 255), (0x0356, 4), (0x0357, 1), (0x0358, 1), (0x0355, 40), (0x035F, 3), (0xE3E0, 0)]:m.ds_write(o, bytes([v]))
    word(0xDE46, 1)
    m.ds_write(0x0351, bytes([20, 20, 20, 20]))
    word(0xDEC8, 50000)
    word(0xDECA, 50000)
    m.ds_write(0x5BD9, bytes(0x59))
    word(0x5BD4, 0)
    word(0x5B6A, 0)
    word(0x5B6C, 0x5B70)
    word(0x5B6E, 0x5B70)
    m.key_events = []
    m.kbd_queue = []
    collision = m.rw(m.DATA_SEG, 0x91B2)
    m.wb(collision, 0, bytes(0x9000))
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    m.wb(dosemu.LOAD_SEG, 0x0A4F, bytes([0xC3]))
    word(0x7242, 65535)
    m.ds_write(0x50B0, bytes([255]))
    path = os.path.join(capture.STATES, 'opponent_near.pkl')
    m.save(path)
    print('Prepared nearby on-foot encounter:', path, flush=True)
    found = capture.record(0, 0xBC68, 'opponentfire_live', count=args.count, skip=0, start='opponent_near', ticks=args.ticks)
    if found < args.count:
        raise SystemExit('Encounter ended before enough firing calls were recorded.')
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'opponentfire_live.pkl.gz'), 'rb'))
    base = m.DATA_SEG<<4
    slots = [struct.unpack_from('<H', st['low'], base+0xB64C)[0] for st in caps]
    if len(caps) > 1 and len(set(slots)) < 2:
        raise SystemExit('Recorder did not capture distinct firing calls.')
    print('Distinct shot-ring positions:', len(set(slots)))

if __name__ == '__main__':
    main()
