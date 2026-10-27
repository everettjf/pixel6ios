#!/usr/bin/env python3
"""Summarize one bounded FTM5 FIFO capture without claiming iOS touch works."""

import argparse
import json
from pathlib import Path
import re

from report_touch_id import STAGES, segments, summarize


FIFO = (
    re.compile(r'^ORIOLE TOUCH FIFO attempts([0-9A-F]{8}) event0([0-9A-F]{8})$'),
    re.compile(r'^ORIOLE TOUCH FIFO b1([0-9A-F]{8}) b2([0-9A-F]{8})$'),
    re.compile(r'^ORIOLE TOUCH FIFO b3([0-9A-F]{8}) b4([0-9A-F]{8})$'),
    re.compile(r'^ORIOLE TOUCH FIFO b5([0-9A-F]{8}) b6([0-9A-F]{8})$'),
    re.compile(r'^ORIOLE TOUCH FIFO b7([0-9A-F]{8}) cleanup([0-9A-F]{8})$'),
)
FIFO_START = 'INVENTORY Oriole one-shot touch FIFO and restore'


def summarize_fifo(lines):
    base = summarize(lines)
    matches = []
    for pattern in FIFO:
        found = [pattern.fullmatch(line) for line in lines]
        found = [match for match in found if match is not None]
        matches.append(found[0] if len(found) == 1 else None)
    if any(match is None for match in matches):
        fields = None
    else:
        fields = [int(value, 16) for match in matches for value in match.groups()]
    attempts = fields[0] if fields else None
    event = fields[1:9] if fields else None
    cleanup = fields[9] if fields else None
    # A failed read still yields an informative complete diagnostic if the
    # probe restored its rails and emitted all five FIFO records.
    complete = (base['complete'] and fields is not None and attempts == 1 and
                lines.count(FIFO_START) == 1 and all(0 <= value <= 0xff for value in event))
    return {**base, 'complete': complete,
            'fifo_read_attempted': attempts == 1,
            'fifo_read_succeeded': complete and base['chip_id_verified_by_probe'] and cleanup == 0,
            'event_bytes': event if complete and base['chip_id_verified_by_probe'] and cleanup == 0 else None,
            'fifo_cleanup_stage': STAGES[cleanup] if cleanup is not None and cleanup < len(STAGES) else cleanup,
            'ios_touch_or_gestures_verified': False}


def report_from_raw(raw):
    captures = [summarize_fifo(lines) for lines in segments(raw)]
    if not captures:
        raise ValueError('No Oriole touch FIFO run marker; no hardware conclusion')
    return {'capture_count': len(captures), 'selected_capture': len(captures), **captures[-1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--out', type=Path)
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
        print(f"Touch FIFO USB log {'complete' if report['complete'] else 'incomplete'}: {args.out}")
    else:
        print(output, end='')
    if not report['complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
