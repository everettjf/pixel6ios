#!/usr/bin/env python3
"""Summarize one read-only Oriole touch inventory capture without inferring chip state."""
import argparse
import json
from pathlib import Path
import re


PINS = ('clk', 'mosi', 'miso', 'cs', 'irq', 'reset', 'mux')
PREFIX = 'SWEET TOUCH: '
VALUE = r'(?:0|0x[0-9a-f]+)'
FIELD = rf'\[{VALUE}\]={VALUE}'
REQUIRED = {
    'cmu base': re.compile(rf'^cmu base 0x[0-9a-f]+: OPTION{FIELD} '
                           rf'usi_mux{FIELD} bus_mux{FIELD} bus_auto{FIELD} '
                           rf'usi_auto{FIELD} div{FIELD}$'),
    'cmu_top': re.compile(rf'^cmu_top 0x[0-9a-f]+: PERIC1_IP mux{FIELD} '
                          rf'div{FIELD} gate{FIELD}$'),
    'cmu gates': re.compile(rf'^cmu gates: ipclk_4{FIELD} pclk_4{FIELD} '
                            rf'rstnsync{FIELD} QCH{FIELD}$'),
    'sysreg USI11 mode': re.compile(rf'^sysreg USI11 mode \(0x[0-9a-f]+\) = {VALUE} '
                                    rf'\(SPI = {VALUE}, so (?:already SPI|not SPI yet)\)$'),
}
PIN_RE = re.compile(r'^pin (clk|mosi|miso|cs|irq|reset|mux)\s+'
                    rf'bank 0x[0-9a-f]+\[\d+\] func={VALUE} dat=[01] pud={VALUE}$')
START_RE = re.compile(r'^(?:cmu base|cmu_top|cmu gates:|sysreg USI11 mode|'
                      r'pin (?:clk|mosi|miso|cs|irq|reset|mux)\b|'
                      r'diag |unreadable pa=)')


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
    # The shim splits long printf messages at spaces into <=82-byte fragments.
    # Rejoin those fragments before validating every field in the CMU records.
    messages = []
    for line in lines:
        if START_RE.match(line) or not messages:
            messages.append(line)
        else:
            messages[-1] += ' ' + line
    pins = set()
    present = set()
    faults = []
    for line in messages:
        for label, pattern in REQUIRED.items():
            if pattern.fullmatch(line):
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


def report_from_raw(raw):
    datasets = [summarize(lines) for lines in captures(raw)]
    if not datasets:
        raise ValueError('No SWEET TOUCH lines captured; no hardware conclusion')
    index = max(range(len(datasets)), key=lambda i: (datasets[i]['complete'],
                                                   -len(datasets[i]['missing']), i))
    selected = datasets[index]
    # A read fault can precede its formatted CMU/pin line. Do not let the
    # CMU-started capture boundary or a later RAM-log replay discard it.
    all_faults = [fault for dataset in datasets for fault in dataset['read_faults']]
    if all_faults:
        selected = {**selected, 'complete': False, 'read_faults': all_faults}
    return {'capture_count': len(datasets), 'selected_capture': index + 1, **selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path, help='raw USB capture from tools/capture_inventory_usb.py')
    parser.add_argument('--out', type=Path, help='optional private JSON report path')
    args = parser.parse_args()
    try:
        report = {'source': str(args.log), **report_from_raw(args.log.read_bytes())}
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
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
