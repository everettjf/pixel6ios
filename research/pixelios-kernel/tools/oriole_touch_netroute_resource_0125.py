#!/usr/bin/env python3
"""Pin the offline Oriole GUI/USB-route resource-observation trial payload.

This checker produces no evidence of USB reconnect, touch or Internet on a
phone. The kernel includes the unbooted 0124 DWC3 observation patch.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_netroute_0124 as base


KERNEL_SHA = '6dc7bd5d718d6292cd41aeb924c9966bc822ab2067eae41f24663b26fb04046b'
PAYLOAD_SHA = 'c87a4317c1e0ac019bfcd1723ae399ce21036bab1e36ec67e5d580540dc802d3'
PAYLOAD_SIZE = 16713744
IMAGE_SHA = 'd13bf273969dff02a101f2e70c857f7bcf7f5d9b61360448dc12146a35806a4e'
ARGS = base.ARGS


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0125 USB-resource trial: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0125 USB-resource trial: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args.encode()) >= 608:
        raise SystemExit('Oriole 0125 USB-resource trial: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0125 USB-resource trial: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, base.base.base.base.base.ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0125 USB-resource trial: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0125 USB-resource trial: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0125 USB-resource trial: truncated image')
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
        # Reuse the exact already-transformed 0121 touch ADT from the 0124
        # profile; do not transform it a second time.
        require_hash(a.base_adt.read_bytes(), base.base.base.base.base.ADT_SHA,
                     'touch ADT')
        a.out.parent.mkdir(parents=True, exist_ok=True)
        blob, _ = mkpayload.build(a.kernel, a.base_adt, ARGS, board='bluejay')
        check(blob)
        a.out.write_bytes(blob)
    elif a.check:
        check(a.check.read_bytes())
    else:
        check_image(a.check_image.read_bytes())
    print('Oriole 0125 USB-resource trial: exact local inputs verified')


if __name__ == '__main__':
    main()
