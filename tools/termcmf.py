"""Extract SONG1.CMF to MIDI, raw instrument records and lossless JSON.
CMF header/clock cross-check: libADLMIDI's primary loader implementation,
https://github.com/Wohlstand/libADLMIDI/blob/master/src/midiseq/impl/read_cmf_impl.hpp
MIDI preserves original CMF patch numbers/controllers; it does not remap to GM.
The standard-library exporter can optionally be validated with independent mido.
"""
import argparse, collections, csv, hashlib, json, struct
from fractions import Fraction
from pathlib import Path

KINDS = {8:'note_off', 9:'note_on', 10:'poly_pressure', 11:'control_change', 12:'program_change', 13:'channel_pressure', 14:'pitch_bend'}

def vlq(raw, at):
    value = 0
    for _ in range(4):
        if at >= len(raw):
            raise ValueError('truncated variable-length number')
        b = raw[at]
        at += 1
        value = (value<<7)|(b&127)
        if b < 128:
            return value, at
    raise ValueError('variable-length number exceeds four bytes')

def encode_vlq(value):
    out = bytearray([value&127])
    value >>= 7
    while value:
        out.insert(0, 128|(value&127))
        value >>= 7
    return bytes(out)

def parse(raw):
    if raw[:4] != b'CTMF' or len(raw) < 37:
        raise ValueError('missing CMF header')
    version = struct.unpack_from('<H', raw, 4)[0]
    if version not in [0x100, 0x101]:
        raise ValueError('unsupported CMF version')
    ins, music, tpq, tps, title, composer, remarks = struct.unpack_from('<7H', raw, 6)
    count = raw[36] if version == 0x100 else struct.unpack_from('<H', raw, 36)[0]
    if not 0 < tpq < 32768 or not tps or not 37 <= ins <= ins+count*16 <= music <= len(raw):
        raise ValueError('invalid CMF header bounds/clock')
    def text(offset):
        if not offset:
            return ''
        end = raw.find(bytes([0]), offset)
        if not 0 <= offset < end < len(raw):
            raise ValueError('invalid CMF metadata string')
        return raw[offset:end].decode('cp437')
    header = dict(version='%d.%d'%(version>>8, version&255), instrument_offset=ins, music_offset=music, ticks_per_quarter=tpq, ticks_per_second=tps, title=text(title), composer=text(composer), remarks=text(remarks), channels_in_use=list(raw[20:36]), instrument_count=count, extra_header_word=struct.unpack_from('<H', raw, 38)[0] if version == 0x101 else None)
    instruments = [dict(index=i, raw_hex=raw[ins+i*16:ins+(i+1)*16].hex()) for i in range(count)]
    at = music
    tick = 0
    running = None
    events = []
    ended = False
    while at < len(raw):
        start = at
        delta, at = vlq(raw, at)
        tick += delta
        if at >= len(raw):
            raise ValueError('missing event status')
        if raw[at] >= 128:
            status = raw[at]
            at += 1
        elif running is not None:
            status = running
        else:
            raise ValueError('running status without prior channel status')
        event = dict(index=len(events), offset=start, delta=delta, tick=tick, status=status)
        if status < 240:
            if status < 128:
                raise ValueError('invalid channel status')
            running = status
            n = 1 if status>>4 in [12, 13] else 2
            payload = raw[at:at+n]
            at += n
            if len(payload) != n or any(x >= 128 for x in payload):
                raise ValueError('invalid channel data')
            event.update(kind=KINDS[status>>4], channel=status&15, data=list(payload))
        elif status in [240, 247, 255]:
            running = None
            if status == 255:
                if at >= len(raw):
                    raise ValueError('missing meta type')
                event['meta_type'] = raw[at]
                at += 1
            n, at = vlq(raw, at)
            payload = raw[at:at+n]
            at += n
            if len(payload) != n:
                raise ValueError('truncated system/meta data')
            event.update(kind='meta' if status == 255 else 'sysex', data=list(payload))
            if status == 255 and event['meta_type'] == 47:
                if n:
                    raise ValueError('nonempty end-of-track')
                ended = True
        else:
            raise ValueError('unsupported system status %02x'%status)
        event['raw_hex'] = raw[start:at].hex()
        events.append(event)
        if ended:
            break
    if not ended:
        raise ValueError('no end-of-track event')
    programs = sorted({e['data'][0] for e in events if e['kind'] == 'program_change'})
    if programs and programs[-1] >= count:
        raise ValueError('program outside CMF bank')
    doc = dict(source_sha256=hashlib.sha256(raw).hexdigest(), source_bytes=len(raw), header=header, raw_header_hex=raw[:ins].hex(), instruments=instruments, bank_to_music_gap_hex=raw[ins+count*16:music].hex(), events=events, track_tail_hex=raw[at:].hex(), event_count=len(events), end_tick=tick, duration_at_header_clock_seconds=float(Fraction(tick, tps)), programs_used=programs, controllers=sorted({e['data'][0] for e in events if e['kind'] == 'control_change'}), primary_format_reference='https://github.com/Wohlstand/libADLMIDI/blob/master/src/midiseq/impl/read_cmf_impl.hpp')
    rebuilt = bytes.fromhex(doc['raw_header_hex'])+b''.join(bytes.fromhex(i['raw_hex']) for i in instruments)+bytes.fromhex(doc['bank_to_music_gap_hex'])+b''.join(bytes.fromhex(e['raw_hex']) for e in events)+bytes.fromhex(doc['track_tail_hex'])
    if rebuilt != raw:
        raise ValueError('lossless CMF reassembly failed')
    return doc, raw[music:at]

def verify_mido(path, doc, tempo):
    import mido
    midi = mido.MidiFile(path)
    track = midi.tracks[0]
    if midi.type != 0 or midi.ticks_per_beat != doc['header']['ticks_per_quarter'] or track[0].type != 'set_tempo' or track[0].tempo != tempo:
        raise ValueError('independent MIDI header/tempo mismatch')
    tick = 0
    if len(track) != len(doc['events'])+1:
        raise ValueError('independent MIDI event count mismatch')
    for event, msg in zip(doc['events'], track[1:]):
        tick += msg.time
        payload = bytes(event['data'])
        status = event['status']
        if status == 255:
            expected = bytes([255, event['meta_type']])+encode_vlq(len(payload))+payload
        elif status in [240, 247]:
            raise ValueError('independent sysex comparison not implemented')
        else:
            expected = bytes([status])+payload
        if tick != event['tick'] or bytes(msg.bytes()) != expected:
            raise ValueError('independent MIDI event mismatch '+str(event['index']))
    if abs(midi.length-doc['duration_at_header_clock_seconds']) > 1e-7:
        raise ValueError('independent MIDI duration mismatch')
    return dict(parser='mido', event_count=len(track), duration_seconds=midi.length, all_source_events_identical=True)

def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', nargs='?', type=Path, default=root/'data/common/SONG1.CMF')
    ap.add_argument('output', nargs='?', type=Path, default=root/'out/music')
    ap.add_argument('--verify-mido', action='store_true')
    args = ap.parse_args()
    raw = args.source.read_bytes()
    doc, track = parse(raw)
    h = doc['header']
    tempo = Fraction(h['ticks_per_quarter']*1000000, h['ticks_per_second'])
    if tempo.denominator != 1 or not 0 < tempo < 0x1000000:
        raise ValueError('clock cannot be represented exactly with original TPQ')
    tempo = int(tempo)
    data = bytes.fromhex('00ff5103')+tempo.to_bytes(3, 'big')+track
    midi = b'MThd'+struct.pack('>IHHH', 6, 0, 1, h['ticks_per_quarter'])+b'MTrk'+struct.pack('>I', len(data))+data
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    stem = args.source.stem
    mid = out/(stem+'.mid')
    mid.write_bytes(midi)
    bank = b''.join(bytes.fromhex(i['raw_hex']) for i in doc['instruments'])
    (out/(stem+'.opl-bank.bin')).write_bytes(bank)
    with (out/(stem+'_instruments.csv')).open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['index']+['byte_%02d'%i for i in range(16)])
        for i, inst in enumerate(doc['instruments']):
            writer.writerow([i]+['%02X'%x for x in bytes.fromhex(inst['raw_hex'])])
    doc['midi'] = dict(file=mid.name, tempo_microseconds=tempo, division=h['ticks_per_quarter'], original_patch_numbers_preserved=True, general_midi_remapping=False)
    if args.verify_mido:
        doc['independent_validation'] = verify_mido(mid, doc, tempo)
    (out/(stem+'.json')).write_text(json.dumps(doc, indent=2), encoding='utf-8')
    readme = ['SONG1 music export', '', 'MIDI event timing, CMF program numbers and controllers are preserved.',
            'The raw bank contains consecutive 16-byte CMF instrument records.',
            'Use those records with an OPL/CMF renderer for the original timbres;',
            'a General MIDI synthesizer will assign different instruments.',
            'JSON preserves the complete original header, event encodings and trailing bytes,',
            'and reassembles byte-for-byte to the original CMF. MIDI omits CMF tail padding.',
            'No audio rendering or original FM-driver timing is claimed here.', '']
    (out/'README.txt').write_text(chr(10).join(readme), encoding='utf-8')
    print('CMF:', len(doc['instruments']), 'instruments,', len(doc['events']), 'events,', doc['end_tick'], 'ticks,', doc['duration_at_header_clock_seconds'], 'seconds; lossless reassembly PASS')
    if args.verify_mido:
        print('Independent mido validation: all events/ticks/duration match')
if __name__ == '__main__':
    main()
