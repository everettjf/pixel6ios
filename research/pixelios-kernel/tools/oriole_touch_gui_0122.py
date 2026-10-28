#!/usr/bin/env python3
"""Pin the Oriole 0122 GUI-touch payload with framebuffer serial disabled.

Only serial=3 becomes serial=0 relative to 0121. The touch window, rail
sequence, kernel and ADT remain pinned to the same bytes. The 0120 and 0121
profiles remain separate for comparison.
This script constructs or checks local files; it never contacts the phone.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_gui_0121 as base


KERNEL_SHA = base.KERNEL_SHA
PAYLOAD_SHA = '91d586106277bb53eae6303441d9282f4a5be8a74e20a860f7535c363e572965'
PAYLOAD_SIZE = 16713664
# The shim's pstore marker embeds the source HEAD used for this local build.
IMAGE_SHA = 'cf4ef12866af697903d76a5eaae188cf80ee74bbe3a45997034f429a3e42701c'
ARGS = base.base.ARGS.replace('serial=3', 'serial=0')
assert ARGS != base.base.ARGS and 'serial=3' not in ARGS


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0122 GUI touch: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0122 GUI touch: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args) >= 608:
        raise SystemExit('Oriole 0122 GUI touch: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0122 GUI touch: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, base.base.ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0122 GUI touch: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0122 GUI touch: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0122 GUI touch: truncated image')
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
        tree = base.base.make_adt(a.base_adt.read_bytes())
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tree_path = a.out.parent / 'oriole-touch-gui.adt'
        tree_path.write_bytes(tree)
        blob, _ = mkpayload.build(a.kernel, tree_path, ARGS, board='bluejay')
        check(blob)
        a.out.write_bytes(blob)
    elif a.check:
        check(a.check.read_bytes())
    else:
        check_image(a.check_image.read_bytes())
    print('Oriole 0122 GUI touch: exact local inputs verified')


if __name__ == '__main__':
    main()
