#!/usr/bin/env python3
"""Pinned Oriole COW image with preallocated RAM pool and HFS trace."""
import argparse
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import oriole_ufsroot_cow as cow

KERNEL_SHA = 'c916b30ded2c9eed8575df4b45dfa16e7bb9e2ffea5f260f1d12fa6c645987ed'
PAYLOAD_SHA = '3ca9b55cf51544b72f0e3bbc008104dfddbc56ac357978a24dc7cb665e3abb32'
PAYLOAD_SIZE = 16714528


def check(blob):
    cow.check(blob, payload_sha=PAYLOAD_SHA, payload_size=PAYLOAD_SIZE)


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
        image = a.check_image.read_bytes()
        if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
            raise SystemExit('Expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        off = 4096 + ((kernel_size + 4095) & ~4095)
        if off + ramdisk_size > len(image):
            raise SystemExit('Truncated Android boot image')
        check(image[off:off + ramdisk_size])
    else:
        if not a.out or not a.product:
            p.error('--kernel requires --out and explicit --product')
        blob, _ = cow.build(a.kernel, a.product, a.out, kernel_sha=KERNEL_SHA)
        check(blob)
        (a.out/'oriole-ufsroot-cow-pool-payload.bin').write_bytes(blob)
    print('Oriole COW reserved pool: exact payload verified')


if __name__ == '__main__':
    main()
