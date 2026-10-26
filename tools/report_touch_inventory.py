#!/usr/bin/env python3
"""Summarize one read-only Oriole touch inventory capture without inferring chip state."""
import argparse
import json
from pathlib import Path
import re


PINS = ('clk', 'mosi', 'miso', 'cs', 'irq', 'reset', 'mux')
REQUIRED = ('cmu base', 'cmu_top', 'cmu gates', 'sysreg USI11 mode')
PREFIX = 'SWEET TOUCH: '
PIN_RE = re.compile(r'^pin (clk|mosi|miso|cs|irq|reset|mux)\b')


def captures(raw):
    """The USB gadget may replay RAM logs; keep each CMU-started dump separate."""
    result = []
    current = []
    for line in raw.decode('utf-8', errors='replace').splitlines():
        at = line.find(PREFIX)
        if at < 0:
            continue
        entry = line[at + len(PREFIX):].strip()
        if entry.startswith('cmu base') and current:
            result.append(current)
            current = []
        current.append(entry)
    if current:
        result.append(current)
    return result


def summarize(lines):
    pins = set()
    present = set()
    faults = []
    for line in lines:
        for label in REQUIRED:
            if line.startswith(label):
                present.add(label)
        match = PIN_RE.match(line)
        if match:
            pins.add(match[1])
        if line.startswith('unreadable pa='):
            faults.append(line)
    missing = [label for label in REQUIRED if label not in present]
    missing.extend('pin ' + name for name in PINS if name not in pins)
    # An incomplete capture is never evidence that a register or pad is absent.
    return {'complete': not missing and not faults,
            'missing': missing, 'read_faults': faults, 'touch_lines': lines}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path, help='raw USB capture from tools/capture_inventory_usb.py')
    parser.add_argument('--out', type=Path, help='optional private JSON report path')
    args = parser.parse_args()
    datasets = [summarize(lines) for lines in captures(args.log.read_bytes())]
    if not datasets:
        raise SystemExit('No SWEET TOUCH lines captured; no hardware conclusion')
    # Prefer a complete run over a later partial RAM-log replay. Ties use the latest.
    index = max(range(len(datasets)), key=lambda i: (datasets[i]['complete'],
                                                       -len(datasets[i]['missing']), i))
    report = {'source': str(args.log), 'capture_count': len(datasets),
              'selected_capture': index + 1, **datasets[index]}
    output = json.dumps(report, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
        args.out.chmod(0o600)
        print(f"Touch inventory {'complete' if report['complete'] else 'incomplete'}: {args.out}")
    else:
        print(output, end='')
    if not report['complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
