"""Record real AI/controller entries from prepared automated gameplay encounters.
Preparation sets actor roles/proximity and attack probabilities; original gameplay
executes between entries. Only sound/border hardware bodies are replaced by returns.
"""
import argparse, gzip, pickle, os, struct
import capture, dosemu


def main():
    kinds = ['controller', 'slowcontroller', 'companion', 'companionfire', 'companionai', 'world', 'worldslow']
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=kinds)
    ap.add_argument('--count', type=int, default=16)
    ap.add_argument('--ticks', type=int, default=400)
    args = ap.parse_args()
    m = dosemu.Machine()
    m.load(os.path.join(capture.STATES, 'opponent_near.pkl'))
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    if args.kind in ['controller', 'companionai', 'world']:
        # Keep the player's prepared position while switching to the source's
        # 0508 role, dispatching opposing 04D4 through C21F and companion DB26.
        old = m.rw(m.DATA_SEG, 0x03A0)
        if old != 0x0508:
            a = m.ds_read(0x04D4, 52)
            b = m.ds_read(0x0508, 52)
            m.ds_write(0x0508, a)
            m.ds_write(0x04D4, b)
        word(0x03A0, 0x0508)
        word(0x04BA, 0x04D4)
    else:
        word(0x03A0, 0x04D4)
        word(0x04BA, 0x0508)
    if args.kind not in ['controller', 'slowcontroller']:
        word(0x11BE, 2)
        player = m.rw(m.DATA_SEG, 0x03A0)
        for axis, at in enumerate([34, 42]):
            value = (struct.unpack('<I', m.ds_read(player+at, 4))[0]+300)&0xFFFFFFFF
            m.ds_write(0x053C+at, struct.pack('<I', value))
            word(0x053C+(32 if axis else 30), value//1024)
            word(0x053C+(4 if axis else 0), (1024-value%1024) if axis else value%1024)
        word(0x0558, 200)
        word(0x0556, 0)
        m.ds_write(0x1154, bytes([255]))
    if args.kind == 'companionfire':
        m.ds_write(0xB69F, bytes([0]))
        word(0x0386, 10000)
    entry = dict(controller=0xC21F, slowcontroller=0xB7B6, companion=0xDD56, companionfire=0xBFB3, companionai=0xDB26, world=0xB5F9, worldslow=0xB5F9)[args.kind]
    word(0x7242, 65535)
    m.ds_write(0x50B0, b'\xff')
    start = 'ai_'+args.kind
    m.save(os.path.join(capture.STATES, start+'.pkl'))
    name = 'ai_'+args.kind+'_live'
    n = capture.record(0, entry, name, count=args.count, skip=0, start=start, ticks=args.ticks)
    if n < args.count:
        raise SystemExit('Not enough original entries: %d/%d'%(n, args.count))
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, name+'.pkl.gz'), 'rb'))
    base = m.DATA_SEG<<4
    frames = [st['trace_frame'] for st in caps]
    if len(set(frames)) < 2:
        raise SystemExit('Capture did not advance to distinct game frames')
    print('Distinct gameplay frames:', len(set(frames)))

if __name__ == '__main__':
    main()
