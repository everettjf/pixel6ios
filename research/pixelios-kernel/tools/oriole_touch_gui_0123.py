#!/usr/bin/env python3
"""Pin the Oriole 0123 extended-window GUI-touch payload.

Relative to 0122, the kernel accepts a 2400-second touch window; this profile
sets a 3000-second restart. The ADT and 0121 HID metadata remain pinned.
Earlier profiles remain separate for comparison.
This script constructs or checks local files; it never contacts the phone.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_gui_0122 as base


KERNEL_SHA = '62c47dd99e2cfd9bf763c0b03c618223ca4deb4d1ab34c24e81a0abea1115d56'
PAYLOAD_SHA = '6d114538e636421087bf86d634f851d564e9a6626d225cb0c987fff0ff75142d'
PAYLOAD_SIZE = 16713664
# The shim's pstore marker embeds the source HEAD used for this local build.
IMAGE_SHA = '64a6aa547b5cac811b71ff8f80f7f0a9374fb18ad32ba8fe91cc4e87671abff7'
assert base.ARGS.count('sweetrestart=1800') == 1
assert base.ARGS.count('sweettouchwindow=1200') == 1
ARGS = base.ARGS.replace('sweetrestart=1800', 'sweetrestart=3000').replace('sweettouchwindow=1200', 'sweettouchwindow=2400')
assert 'serial=0' in ARGS and 'sweetrestart=3000' in ARGS and 'sweettouchwindow=2400' in ARGS


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0123 GUI touch: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0123 GUI touch: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args) >= 608:
        raise SystemExit('Oriole 0123 GUI touch: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0123 GUI touch: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, base.base.base.ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0123 GUI touch: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0123 GUI touch: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0123 GUI touch: truncated image')
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
        tree = base.base.base.make_adt(a.base_adt.read_bytes())
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
    print('Oriole 0123 GUI touch: exact local inputs verified')


if __name__ == '__main__':
    main()
