#!/usr/bin/env python3
"""Summarize one bounded Oriole touch-ID USB capture; never infer iOS touch."""

import argparse
import json
from pathlib import Path
import re


START = 'INVENTORY Oriole one-shot touch ID and restore'
END = 'INVENTORY report complete'
RAIL = re.compile(r'^ORIOLE TOUCH RAIL reg([0-9A-F]{8}) value([0-9A-F]{8})$')
RESULT = re.compile(r'^ORIOLE TOUCH ID first([0-9A-F]{8}) cleanup([0-9A-F]{8})$')
IDENT = re.compile(r'^ORIOLE TOUCH ID id0([0-9A-F]{8}) id1([0-9A-F]{8})$')
COUNTS = re.compile(r'^ORIOLE TOUCH ID attempts([0-9A-F]{8}) restored([0-9A-F]{8})$')
RAIL_SEQUENCE = [(0x5c, 0x2c), (0x5d, 0x3c), (0x5c, 0xac),
                 (0x5d, 0xbc), (0x5d, 0x3c), (0x5c, 0x2c)]
STAGES = ('OK', 'BAD_OPS', 'PREFLIGHT', 'SHARED_SNAPSHOT', 'RAIL_READ',
          'RAIL_ENABLE_25', 'RAIL_ENABLE_26', 'RAIL_VERIFY', 'MODE_SET',
          'ENGINE_SNAPSHOT', 'SPI_PREPARE', 'SPI_IDENTIFY', 'ID_MISMATCH',
          'ENGINE_RESTORE', 'MODE_RESTORE', 'SHARED_RESTORE',
          'RAIL_RESTORE_26', 'RAIL_RESTORE_25')


def segments(raw):
    current = None
    result = []
    for line in raw.decode('utf-8', errors='replace').splitlines():
        line = line.strip()
        if line == START:
            if current is not None:
                result.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
            if line == END:
                result.append(current)
                current = None
    if current is not None:
        result.append(current)
    return result


def summarize(lines):
    rails = []
    result = ident = counts = None
    status = []
    diagnostics = []
    for line in lines:
        if match := RAIL.fullmatch(line):
            rails.append((int(match[1], 16), int(match[2], 16)))
        elif match := RESULT.fullmatch(line):
            result = (int(match[1], 16), int(match[2], 16))
        elif match := IDENT.fullmatch(line):
            ident = (int(match[1], 16), int(match[2], 16))
        elif match := COUNTS.fullmatch(line):
            counts = (int(match[1], 16), int(match[2], 16))
        elif line in ('ORIOLE TOUCH ID FAILED',
                      'ORIOLE TOUCH ID PASS 36 48 AND RESTORED'):
            status.append(line.removeprefix('ORIOLE TOUCH ID '))
        elif line.startswith('ORIOLE TOUCH '):
            diagnostics.append(line)
    complete = (lines[-1] == END and rails == RAIL_SEQUENCE and
                result is not None and ident is not None and
                counts is not None and len(status) == 1)
    first, cleanup = result if result is not None else (None, None)
    attempts, restored = counts if counts is not None else (None, None)
    identified = (complete and first == 0 and cleanup == 0 and
                  attempts == 1 and restored == 2 and
                  ident == (0x36, 0x48) and
                  status == ['PASS 36 48 AND RESTORED'])
    return {
        'complete': complete,
        'chip_id_verified_by_probe': identified,
        'ios_touch_or_gestures_verified': False,
        'first_stage': STAGES[first] if first is not None and first < len(STAGES) else first,
        'cleanup_stage': STAGES[cleanup] if cleanup is not None and cleanup < len(STAGES) else cleanup,
        'id_bytes': list(ident) if ident is not None else None,
        'attempts': attempts,
        'rails_restored_by_probe': complete and rails[-2:] == RAIL_SEQUENCE[-2:] and restored == 2,
        'rail_sequence_valid': rails == RAIL_SEQUENCE,
        'status': status,
        'diagnostics': diagnostics,
    }


def report_from_raw(raw):
    captures = [summarize(lines) for lines in segments(raw)]
    if not captures:
        raise ValueError('No Oriole touch-ID run marker; no hardware conclusion')
    # A partial tail may be a new run rather than a replay; never silently
    # select an older successful capture in that case.
    return {'capture_count': len(captures), 'selected_capture': len(captures),
            **captures[-1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--out', type=Path, help='private JSON report path')
    args = parser.parse_args()
    try:
        report = report_from_raw(args.log.read_bytes())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    output = json.dumps(report, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
        args.out.chmod(0o600)
        print(f"Touch-ID USB log {'complete' if report['complete'] else 'incomplete'}; "
              f"chip ID {'verified' if report['chip_id_verified_by_probe'] else 'not verified'}: {args.out}")
    else:
        print(output, end='')
    if not report['complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
