#!/usr/bin/env python3
"""Reassemble opt-in SWEET FB SNAP rows from a USB log into PNG thumbnails.

Only complete, uniquely numbered frames with their BEGIN and END markers are
written. The input is private device evidence; never commit the generated PNGs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

BEGIN = re.compile(r'SWEET FB SNAP (\d{1,10}) BEGIN (\d{1,3}) (\d{1,3}) rolling=1(?=\D|$)')
ROW = re.compile(r'SWEET FB SNAP (\d{1,10}) R (\d{1,3}) ([0-9a-f]{1,256})(?=[^0-9a-f]|$)')
END = re.compile(r'SWEET FB SNAP (\d{1,10}) END(?=\D|$)')
MAX_WIDTH = 128
MAX_HEIGHT = 256
MAX_FRAMES = 256


def frames(lines):
    pending = None
    for line in lines:
        for part in line.split('SWEET FB SNAP ')[1:]:
            record = 'SWEET FB SNAP ' + part[:512]
            if match := BEGIN.match(record):
                stamp, width, height = map(int, match.groups())
                if 0 < width <= MAX_WIDTH and 0 < height <= MAX_HEIGHT:
                    pending = {'stamp': stamp, 'width': width, 'height': height,
                               'rows': {}}
            elif match := ROW.match(record):
                stamp, y, data = match.groups()
                stamp, y = int(stamp), int(y)
                frame = pending
                if (frame is None or stamp != frame['stamp'] or
                        y >= frame['height'] or len(data) != frame['width'] * 2):
                    continue
                try:
                    row = bytes.fromhex(data)
                except ValueError:
                    continue
                if y in frame['rows'] and frame['rows'][y] != row:
                    frame['invalid'] = True
                frame['rows'][y] = row
            elif match := END.match(record):
                stamp = int(match.group(1))
                frame = pending
                if frame is None or stamp != frame['stamp']:
                    continue
                pending = None
                if not frame.get('invalid') and len(frame['rows']) == frame['height']:
                    yield stamp, frame


def png_chunk(kind, data):
    return (struct.pack('>I', len(data)) + kind + data +
            struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))


def png_bytes(frame, scale=8):
    width, height = frame['width'], frame['height']
    raw = bytearray()
    for y in range(height):
        row = bytearray()
        for value in frame['rows'][y]:
            rgb = (((value >> 5) & 7) * 255 // 7,
                   ((value >> 2) & 7) * 255 // 7,
                   (value & 3) * 255 // 3)
            row.extend(bytes(rgb) * scale)
        scan = b'\0' + row
        raw.extend(scan * scale)
    header = struct.pack('>IIBBBBB', width * scale, height * scale, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', header) +
            png_chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + png_chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = []
    with args.log.open(errors='replace') as source:
        # readline(size) bounds memory even when a damaged log lacks newlines.
        chunks = iter(lambda: source.readline(8192), '')
        for sequence, (stamp, frame) in enumerate(frames(chunks), 1):
            if sequence > MAX_FRAMES:
                raise SystemExit(f'Too many frames (limit {MAX_FRAMES})')
            path = args.out_dir / f'fb-snap-{sequence:04d}-{stamp}.png'
            path.write_bytes(png_bytes(frame))
            pixels = b''.join(frame['rows'][y] for y in range(frame['height']))
            report.append({'frame': stamp, 'sampling': 'rolling',
                           'width': frame['width'], 'height': frame['height'],
                           'rgb332_sha256': hashlib.sha256(pixels).hexdigest(),
                           'png': path.name})
    if not report:
        raise SystemExit('No complete SWEET FB SNAP frame in this log')
    (args.out_dir / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Decoded {len(report)} complete frame(s) into {args.out_dir}')


if __name__ == '__main__':
    main()
