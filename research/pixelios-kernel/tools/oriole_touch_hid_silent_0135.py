#!/usr/bin/env python3
"""Pin a quiet-display variant of the hardware-tested Oriole HID payload.

This profile checks local artifacts only. It makes no claim about touch,
network service registration or Internet access on a phone.
"""

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import adt, mkpayload, oriole_touch_hid_abi_0134 as base


KERNEL_SHA = base.KERNEL_SHA
PAYLOAD_SHA = '53b28fdd2c0c5494fd1628ecea90ec51b00d9bf79340e21f122cd687fe3dc423'
PAYLOAD_SIZE = base.PAYLOAD_SIZE
IMAGE_SHA = 'f2f18d92f74ff6f2550b3983295c1584f8c316ebb36fcbc29b3959c77a6716cc'
ARGS = base.ARGS.replace('serial=3', 'serial=0')
ADT_SHA = base.ADT_SHA
if ARGS == base.ARGS or ARGS.replace('serial=0', 'serial=3') != base.ARGS:
    raise RuntimeError('0135 must change only the framebuffer serial boot argument')


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole 0135 HID silent: unexpected {what}')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole 0135 HID silent: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args.encode()) >= 608:
        raise SystemExit('Oriole 0135 HID silent: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if not adt_size or adt_off + adt_size > len(blob):
        raise SystemExit('Oriole 0135 HID silent: ADT bounds invalid')
    tree_blob = blob[adt_off:adt_off + adt_size]
    require_hash(tree_blob, ADT_SHA, 'touch ADT')
    tree, end = adt.parse(tree_blob)
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole 0135 HID silent: controller compatible mismatch')


def check_image(image):
    require_hash(image, IMAGE_SHA, 'complete AVB boot image')
    if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
        raise SystemExit('Oriole 0135 HID silent: expected Android v4 image')
    kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
    off = 4096 + ((kernel_size + 4095) & ~4095)
    if off + ramdisk_size > len(image):
        raise SystemExit('Oriole 0135 HID silent: truncated image')
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
    print('Oriole 0135 HID silent: exact local inputs verified')


if __name__ == '__main__':
    main()
