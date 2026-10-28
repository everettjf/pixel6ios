#!/usr/bin/env python3
"""Pin the offline Oriole GUI-touch, USB-route and IORegistry trial payload.

This profile checks local artifacts only. It makes no claim about touch,
network service registration or Internet access on a phone.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_netroute_resource_0125 as base


KERNEL_SHA = 'a1036dba2c11af88587a72ad581339af09efbe9f39dd9c727279240056492df6'
PAYLOAD_SHA = '972d39341a4a5f9875ee8646fc361278e0a696acf2a540d84c410cc45f1cfb4a'
PAYLOAD_SIZE = 16753584
IMAGE_SHA = 'fde6a6198053fb0716051e0ebabf279c10e28f843c0fb25c588092dad0ea67c1'
ARGS = base.ARGS + ' sweetnetif=1'
assert 'sweetnetif' not in base.ARGS and ARGS.endswith(' sweetnetif=1')


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0126 NETIF trial: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0126 NETIF trial: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args.encode()) >= 608:
        raise SystemExit('Oriole 0126 NETIF trial: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0126 NETIF trial: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, base.base.base.base.base.base.ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0126 NETIF trial: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0126 NETIF trial: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0126 NETIF trial: truncated image')
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
        require_hash(a.base_adt.read_bytes(), base.base.base.base.base.base.ADT_SHA,
                     'touch ADT')
        a.out.parent.mkdir(parents=True, exist_ok=True)
        blob, _ = mkpayload.build(a.kernel, a.base_adt, ARGS, board='bluejay')
        check(blob)
        a.out.write_bytes(blob)
    elif a.check:
        check(a.check.read_bytes())
    else:
        check_image(a.check_image.read_bytes())
    print('Oriole 0126 NETIF trial: exact local inputs verified')


if __name__ == '__main__':
    main()
