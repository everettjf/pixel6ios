#!/usr/bin/env python3
"""Exact read-only Oriole UFS root profile permitting the iOS launchd platform.

The original storage-root profile remains pinned and unchanged. This variant
adds only the XNU DEVELOPMENT boot argument needed when the macOS-targeted
kernel execs an iOS binary without posix_spawn platform attributes.
"""
import argparse
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import adt, mkadt, mkpayload, oriole_ufsroot as base

ARGS = base.ARGS + ' unentitled_ios_sim_launch=1'
PAYLOAD_SHA = 'f40d4945133cd9d3a40175b052fbc88c5e63cceb5a41d34cc2b0367e8d7072a3'


def validate_args(args):
    if args != ARGS:
        raise SystemExit('Oriole launchd-platform: unexpected command line')
    tokens = [token.partition('=') for token in args.split()]
    keys = [key for key, _, _ in tokens]
    if len(keys) != len(set(keys)):
        raise SystemExit('Oriole launchd-platform: duplicate argument')
    if {key: value for key, sep, value in tokens if sep}.get('unentitled_ios_sim_launch') != '1':
        raise SystemExit('Oriole launchd-platform: platform permission missing')
    for key, value in base.REQUIRED.items():
        if {k: v for k, sep, v in tokens if sep}.get(key) != value:
            raise SystemExit('Oriole launchd-platform: read-only guard changed')


def build(kernel, product, out):
    base.require_hash(kernel.read_bytes(), base.KERNEL_SHA)
    base.require_hash(product.read_bytes(), base.PRODUCT_SHA)
    if (base.ROOT/'research/ipsw-x/d22ap.adt').exists():
        raise SystemExit('Oriole launchd-platform: implicit product lookup must remain absent')
    product_props = mkadt.d22ap_product(str(product))
    if not product_props or len(product_props) != 61 or len(dict(product_props)) != 61:
        raise SystemExit('Oriole launchd-platform: incomplete D22AP product input')
    product_props = [(k, v) for k, v in product_props if k != 'product-description'] + [
        ('product-description', b'Pixel 6\0')]
    root = mkadt.build(seed=bytes(range(64)), board='oriole')
    root.children = [n for n in root.children if n.name not in ('sweet-touch', 'sweet-keys', 'product')]
    root.children.append(mkadt.node('product', product_props))
    root.props = [(k, f, b'oriole\0' if k == 'model-number' else v) for k, f, v in root.props]
    ufs = next(n for n in root.children if n.name == 'sweet-ufs')
    ufs.props.append(('oriole-root-board', 0, b'oriole\0'))
    base.check_tree(root)
    validate_args(ARGS)
    out.mkdir(parents=True, exist_ok=True)
    (out/'oriole-ufsroot-platform.adt').write_bytes(adt.serialize(root))
    return mkpayload.build(kernel, out/'oriole-ufsroot-platform.adt', ARGS, board='oriole')


def check(blob):
    if len(blob) != base.PAYLOAD_SIZE:
        raise SystemExit('Oriole launchd-platform: payload size mismatch')
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
        (a.out/'oriole-ufsroot-platform-payload.bin').write_bytes(blob)
    print('Oriole read-only launchd-platform root: exact payload verified')


if __name__ == '__main__':
    main()
