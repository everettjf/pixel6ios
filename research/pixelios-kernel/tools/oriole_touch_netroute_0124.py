#!/usr/bin/env python3
"""Pin the local Oriole GUI-touch plus opt-in USB-route trial payload.

The root stays RAM-COW/read-only on UFS. This profile is an offline artifact
checker; no route or Internet behavior is implied by a successful check.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_gui_0123 as base


KERNEL_SHA = 'f68406db756901338eedec463cec3bf54c063f56c817c8fb5173398fb89a89ef'
PAYLOAD_SHA = 'ac57f6084e49200079fc932433bef4bcaeca1da4a9c37cd02555725b8fd00e8f'
PAYLOAD_SIZE = 16730160
IMAGE_SHA = '34951d115aa9e933bf1b2b69e8897fcd74779bb048e8693c008c82c178e692fb'
ARGS = base.ARGS + ' sweetnetroute=1'
assert 'sweetnetroute' not in base.ARGS and ARGS.endswith(' sweetnetroute=1')


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0124 USB-route trial: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0124 USB-route trial: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args.encode()) >= 608:
        raise SystemExit('Oriole 0124 USB-route trial: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0124 USB-route trial: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, base.base.base.base.ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0124 USB-route trial: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0124 USB-route trial: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0124 USB-route trial: truncated image')
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
        tree = base.base.base.base.make_adt(a.base_adt.read_bytes())
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tree_path = a.out.parent / 'oriole-touch-netroute.adt'
        tree_path.write_bytes(tree)
        blob, _ = mkpayload.build(a.kernel, tree_path, ARGS, board='bluejay')
        check(blob)
        a.out.write_bytes(blob)
    elif a.check:
        check(a.check.read_bytes())
    else:
        check_image(a.check_image.read_bytes())
    print('Oriole 0124 USB-route trial: exact local inputs verified')


if __name__ == '__main__':
    main()
