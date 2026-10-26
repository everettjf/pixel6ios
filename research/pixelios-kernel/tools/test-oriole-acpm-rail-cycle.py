#!/usr/bin/env python3
"""Pin the isolated Oriole PMIC rail-cycle entry and linked symbol surface."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

SHIM = Path(__file__).resolve().parents[1] / 'shim'
ENTRY_SHA256 = 'b343d7204f780a80af298556ee802b565db5ca8ac8c5d0b46e0438a766a26469'
CLIENT_DEFINED = frozenset(('acpm_cfg_init', 'acpm_describe', 'acpm_chan_id',
                            'acpm_qword', 'acpm_pmic_read',
                            'acpm_oriole_touch_rail_set', 'acpm_why', 'acpm_unsure'))
CLIENT_UNDEFINED = frozenset(('try_read32', 'try_write32', 'counter_freq', 'touch_ticks'))
ENTRY_DEFINED = frozenset(('acpm_rail_cycle_run',))
ENTRY_UNDEFINED = frozenset(('acpm_cfg_init', 'acpm_describe',
                            'acpm_oriole_touch_rail_set', 'acpm_pmic_read',
                            'con_hex2', 'con_str'))


def validate_source(source):
    if hashlib.sha256(source.encode()).hexdigest() != ENTRY_SHA256:
        raise ValueError('Oriole rail-cycle entry changed; re-review exact sequence')
    ordered = ('rc = acpm_describe(&c, &h);',
               'if (!read_exact(&c, 0x5cu, 0x2cu, &seq) || !read_exact(&c, 0x5du, 0x3cu, &seq))',
               'set_rail(&c, 0x5cu, 1, &a, &seq)',
               'set_rail(&c, 0x5du, 1, &b, &seq)',
               'restore:',
               'set_rail(&c, 0x5du, 0, &b, &seq)',
               'set_rail(&c, 0x5cu, 0, &a, &seq)')
    if any(source.count(s) != 1 for s in ordered):
        raise ValueError('Oriole rail-cycle gate or call count changed')
    if list(map(source.index, ordered)) != sorted(map(source.index, ordered)):
        raise ValueError('Oriole rail-cycle order changed')
    if any(word in source for word in ('try_write32', 'try_read32', 'volatile', '__asm__', 'asm(')):
        raise ValueError('Oriole rail-cycle entry gained direct hardware access')


def validate_symbols(raw, defined, undefined):
    have_def, have_undef = set(), set()
    for line in raw.splitlines():
        m = re.fullmatch(r'(?:[0-9a-fA-F]+\s+)?([A-Za-z])\s+([\w.]+)', line.strip())
        if not m:
            continue
        kind, name = m.groups()
        if kind == 'U':
            have_undef.add(name)
        elif kind.isupper():
            have_def.add(name)
    if have_def != defined or have_undef != undefined:
        raise ValueError(f'rail-cycle symbol drift: defined={sorted(have_def)} undefined={sorted(have_undef)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--nm', required=True)
    ap.add_argument('--client', type=Path, required=True)
    ap.add_argument('--entry', type=Path, required=True)
    args = ap.parse_args()
    source = (SHIM / 'acpmrailcycle.c').read_text()
    validate_source(source)
    client = subprocess.check_output([args.nm, '-g', str(args.client)], text=True)
    entry = subprocess.check_output([args.nm, '-g', str(args.entry)], text=True)
    validate_symbols(client, CLIENT_DEFINED, CLIENT_UNDEFINED)
    validate_symbols(entry, ENTRY_DEFINED, ENTRY_UNDEFINED)
    for old, new in (('0x5cu, 0x2cu, &seq', '0x5cu, 0x2du, &seq'),
                     ('set_rail(&c, 0x5du, 0, &b, &seq)', 'set_rail(&c, 0x5du, 1, &b, &seq)'),
                     ('restore:', 'no_restore:')):
        if old not in source:
            raise ValueError('source mutation fixture drifted')
        try:
            validate_source(source.replace(old, new, 1))
        except ValueError:
            pass
        else:
            raise ValueError('source mutation escaped the rail-cycle auditor')
    for raw, defs, undefs in ((client + '\n00000000 T acpm_pmic_update', CLIENT_DEFINED, CLIENT_UNDEFINED),
                             (entry + '\n         U try_write32', ENTRY_DEFINED, ENTRY_UNDEFINED)):
        try:
            validate_symbols(raw, defs, undefs)
        except ValueError:
            pass
        else:
            raise ValueError('object mutation escaped the rail-cycle auditor')
    print('PASS Oriole rail-cycle source, objects and mutation audits')


if __name__ == '__main__':
    main()
