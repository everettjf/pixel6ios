#!/usr/bin/env python3
"""Fail closed if the Oriole rail-read objects gain another hardware path."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess


SHIM = Path(__file__).resolve().parents[1] / 'shim'
CLIENT_DEFINED = frozenset(('acpm_cfg_init', 'acpm_describe', 'acpm_chan_id',
                            'acpm_qword', 'acpm_pmic_read', 'acpm_why', 'acpm_unsure'))
CLIENT_UNDEFINED = frozenset(('try_read32', 'try_write32', 'counter_freq', 'touch_ticks'))
ENTRY_DEFINED = frozenset(('acpm_rail_read_dump',))
ENTRY_UNDEFINED = frozenset(('acpm_cfg_init', 'acpm_describe', 'acpm_pmic_read',
                            'con_hex2', 'con_str'))
ENTRY_SHA256 = 'e0e8ba8d1aa079c15c2ed20b5e07005bc245d7423b12f5de7fd73b44ebccaf1e'


def symbols(raw):
    defined, undefined = set(), set()
    for line in raw.splitlines():
        match = re.fullmatch(r'(?:[0-9a-fA-F]+\s+)?([A-Za-z])\s+([\w.]+)', line.strip())
        if not match:
            continue
        kind, name = match.groups()
        if kind == 'U':
            undefined.add(name)
        elif kind.isupper():
            defined.add(name)
    return defined, undefined


def validate(raw, expected_defined, expected_undefined):
    defined, undefined = symbols(raw)
    if defined != expected_defined or undefined != expected_undefined:
        raise ValueError(f'object symbols changed: defined={sorted(defined)} undefined={sorted(undefined)}')


def validate_entry_source(entry):
    if hashlib.sha256(entry.encode()).hexdigest() != ENTRY_SHA256:
        raise ValueError('Oriole rail-read entry source changed; re-review exact path')
    ordered = ('acpm_cfg_init(&c);', 'if (c.ch_id != 2', 'rc = acpm_describe(&c, &h);',
               'if (rc || h.rr != h.rf || h.sr != h.sf)', 'for (i = 0; i < 2; i++)',
               'rc = acpm_pmic_read(&c, c.rail[i].reg, &value, &t);',
               'if (rc)\n\t\t\treturn;')
    if any(entry.count(part) != 1 for part in ordered):
        raise ValueError('Oriole rail-read entry ordering or call count changed')
    if list(map(entry.index, ordered)) != sorted(map(entry.index, ordered)):
        raise ValueError('Oriole rail-read entry gate ordering changed')


def source_audit():
    client = (SHIM / 'acpm.c').read_text()
    entry = (SHIM / 'acpmrailread.c').read_text()
    build = (SHIM / 'build.sh').read_text()
    pins = (('#ifndef ORIOLE_ACPM_RAILS_READ', client),
            ('#endif /* ORIOLE_ACPM_RAILS_READ: omit every unrelated ACPM client API */', client),
            ('xfer(c, XM_PMIC, pmic_w0(c, reg), FUNC_READ, 0, 0, t, x)', client),
            ('if (rail_of(c, reg) < 0)', client),
            ('c.rail[0].reg != 0x5cu', entry), ('c.rail[1].reg != 0x5du', entry),
            ('c.layout_verified != 1', entry), ('c.elem_unit_verified != 1', entry),
            ('if (rc)', entry), ('return; /* never make a second request after an uncertain first */', entry),
            ('out/acpmrailread.o out/acpm_rails.o', build))
    if any(pin not in body for pin, body in pins):
        raise ValueError('rail-read source safety pin changed')
    validate_entry_source(entry)
    forbidden = ('try_write32', 'try_read32', 'volatile', '__asm__', 'asm(')
    if any(word in entry for word in forbidden):
        raise ValueError('entry gained direct MMIO or assembly')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--nm', required=True)
    ap.add_argument('--client', type=Path, required=True)
    ap.add_argument('--entry', type=Path, required=True)
    args = ap.parse_args()
    source_audit()
    raw_client = subprocess.check_output([args.nm, '-g', str(args.client)], text=True)
    raw_entry = subprocess.check_output([args.nm, '-g', str(args.entry)], text=True)
    validate(raw_client, CLIENT_DEFINED, CLIENT_UNDEFINED)
    validate(raw_entry, ENTRY_DEFINED, ENTRY_UNDEFINED)
    for bad, defined, undefined in ((raw_client + '\n00000000 T acpm_s10_read', CLIENT_DEFINED, CLIENT_UNDEFINED),
                                    (raw_client + '\n         U acpm_pmic_update', CLIENT_DEFINED, CLIENT_UNDEFINED),
                                    (raw_entry + '\n         U try_write32', ENTRY_DEFINED, ENTRY_UNDEFINED)):
        try:
            validate(bad, defined, undefined)
        except ValueError:
            pass
        else:
            raise SystemExit('rail-read object auditor missed a mutated bad symbol')
    entry = (SHIM / 'acpmrailread.c').read_text()
    for old, new in (('i < 2', 'i < 3'),
                     ('c.rail[i].reg, &value', '0x5eu, &value'),
                     ('if (rc)\n\t\t\treturn;', 'if (0)\n\t\t\treturn;'),
                     ('rc = acpm_describe(&c, &h);',
                      'acpm_pmic_read(&c, c.rail[0].reg, &value, &t);\n\trc = acpm_describe(&c, &h);')):
        if old not in entry:
            raise SystemExit('source mutation fixture no longer matches')
        try:
            validate_entry_source(entry.replace(old, new, 1))
        except ValueError:
            pass
        else:
            raise SystemExit('rail-read source auditor missed a mutated unsafe path')
    print('PASS Oriole ACPM rail-read source, object and mutation audits')


if __name__ == '__main__':
    main()
