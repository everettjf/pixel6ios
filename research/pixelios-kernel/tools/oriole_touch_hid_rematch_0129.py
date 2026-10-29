#!/usr/bin/env python3
"""Pin the offline Oriole HID-service late-rematch diagnostic payload.

This profile checks local artifacts only. It makes no claim about touch,
network service registration or Internet access on a phone.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_hid_diag_0128 as base


KERNEL_SHA = '6d34393ecb4ec132859be3e7523300c2329ccb3435dacef37d976ae2a6eb7d3c'
PAYLOAD_SHA = '99f1ac74acfadc02db3688614f5082a0170ef05c28ffcee974ba1fc2c0314b41'
PAYLOAD_SIZE = 16753872
IMAGE_SHA = 'e096c36f79d5cd9cb2cee2c061e4f81c198302dc85325c45d2ff46e36b35ce57'
ARGS = base.ARGS + ' sweethidrematch=1'
ADT_SHA = 'b85187b0fb3eeec4129c896b508680b27392f2d79ccc24ea95e47e18aa0d4164'


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0129 HID rematch: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0129 HID rematch: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args.encode()) >= 608:
        raise SystemExit('Oriole 0129 HID rematch: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0129 HID rematch: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0129 HID rematch: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0129 HID rematch: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0129 HID rematch: truncated image')
    check(image[off:off + ramdisk_size])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--kernel', type=Path)
    group.add_argument('--check', type=Path)
    group.add_argument('--check-image', type=Path)
    p.add_argument('--base-adt', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    if a.kernel:
        if not a.base_adt or not a.out:
            p.error('--kernel requires --base-adt and --out')
        require_hash(a.kernel.read_bytes(), KERNEL_SHA, 'kernel')
        require_hash(a.base_adt.read_bytes(), ADT_SHA,
                     'touch ADT')
        a.out.parent.mkdir(parents=True, exist_ok=True)
        blob, _ = mkpayload.build(a.kernel, a.base_adt, ARGS, board='bluejay')
        check(blob)
        a.out.write_bytes(blob)
    elif a.check:
        check(a.check.read_bytes())
    else:
        check_image(a.check_image.read_bytes())
    print('Oriole 0129 HID rematch: exact local inputs verified')


if __name__ == '__main__':
    main()
