#!/usr/bin/env python3
"""Exact Oriole RAM-COW root profile; all physical UFS writes remain forbidden."""
import argparse
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import adt, mkadt, mkpayload, oriole_ufsroot as base

# The separate COW kernel is a local PIE relink of the reviewed 0105 source.
KERNEL_SHA = '753d090ab2d833b111e8eb54008b4e984c35bf6f6913a7b492c305fe75cc0d5f'
PAYLOAD_SHA = 'bb08d5b9db73b7dd3f263b2b97ec336c7f44e3fd37313a8b622aef17d18d7d3b'
PAYLOAD_SIZE = 16714240
ARGS = (base.ARGS.replace('sweetrestart=90', 'sweetrestart=300')
        .replace('rootrw=0', 'rootrw=1')
        + ' ufscow=1 unentitled_ios_sim_launch=1')
REQUIRED = dict(base.REQUIRED, sweetrestart='300', rootrw='1', ufscow='1',
                unentitled_ios_sim_launch='1')


def validate_args(args):
    if args != ARGS:
        raise SystemExit('Oriole RAM-COW: unexpected command line')
    tokens = [token.partition('=') for token in args.split()]
    keys = [key for key, _, _ in tokens]
    if len(keys) != len(set(keys)):
        raise SystemExit('Oriole RAM-COW: duplicate argument')
    values = {key: value for key, sep, value in tokens if sep}
    if any(values.get(key) != value for key, value in REQUIRED.items()):
        raise SystemExit('Oriole RAM-COW: missing exact safety guard')


def check_tree(root):
    base.check_tree(root)
    ufs = next(n for n in root.children if n.name == 'sweet-ufs')
    values = base.props(ufs)
    if values.get('oriole-cow-board') != b'oriole-cow\0':
        raise SystemExit('Oriole RAM-COW: missing ADT opt-in')
    if sum(name == 'oriole-cow-board' for name, _, _ in ufs.props) != 1:
        raise SystemExit('Oriole RAM-COW: duplicate ADT opt-in')


def build(kernel, product, out):
    base.require_hash(kernel.read_bytes(), KERNEL_SHA)
    base.require_hash(product.read_bytes(), base.PRODUCT_SHA)
    if (base.ROOT/'research/ipsw-x/d22ap.adt').exists():
        raise SystemExit('Oriole RAM-COW: implicit product lookup must remain absent')
    product_props = mkadt.d22ap_product(str(product))
    if not product_props or len(product_props) != 61 or len(dict(product_props)) != 61:
        raise SystemExit('Oriole RAM-COW: incomplete D22AP product input')
    product_props = [(k, v) for k, v in product_props if k != 'product-description'] + [
        ('product-description', b'Pixel 6\0')]
    root = mkadt.build(seed=bytes(range(64)), board='oriole')
    root.children = [n for n in root.children if n.name not in ('sweet-touch', 'sweet-keys', 'product')]
    root.children.append(mkadt.node('product', product_props))
    root.props = [(k, f, b'oriole\0' if k == 'model-number' else v) for k, f, v in root.props]
    ufs = next(n for n in root.children if n.name == 'sweet-ufs')
    ufs.props.append(('oriole-root-board', 0, b'oriole\0'))
    ufs.props.append(('oriole-cow-board', 0, b'oriole-cow\0'))
    check_tree(root)
    validate_args(ARGS)
    out.mkdir(parents=True, exist_ok=True)
    tree = out/'oriole-ufsroot-cow.adt'
    tree.write_bytes(adt.serialize(root))
    return mkpayload.build(kernel, tree, ARGS, board='oriole')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole RAM-COW: payload size mismatch')
    base.require_hash(blob, PAYLOAD_SHA)
    validate_args(blob[0x48:0x48+608].split(b'\0')[0].decode('ascii'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--kernel', type=Path)
    g.add_argument('--check', type=Path)
    g.add_argument('--check-image', type=Path)
    p.add_argument('--product', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    if a.check:
        check(a.check.read_bytes())
    elif a.check_image:
        b = a.check_image.read_bytes()
        if b[:8] != b'ANDROID!' or struct.unpack_from('<I', b, 40)[0] != 4:
            raise SystemExit('Expected Android v4 image')
        ks, rs = struct.unpack_from('<II', b, 8)
        off = 4096 + ((ks+4095)&~4095)
        check(b[off:off+rs])
    else:
        if not a.out or not a.product:
            p.error('--kernel requires --out and explicit --product')
        blob, _ = build(a.kernel, a.product, a.out)
        check(blob)
        (a.out/'oriole-ufsroot-cow-payload.bin').write_bytes(blob)
    print('Oriole RAM-COW root: exact payload verified')


if __name__ == '__main__':
    main()
