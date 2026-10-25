#!/usr/bin/env python3
"""Exact 1800-second continuation of the reviewed Oriole 512 MiB COW payload."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import oriole_ufsroot_cow_pool512 as base

OLD = b'sweetrestart=900'
NEW = b'sweetrestart=1800'
PAYLOAD_SHA = '4218a85cd2d1e55bd3f327f28bac6715a9cf55f2715213bd7e93ae419b7a3970'
START = 0x48
SIZE = 608


def replace_arg(blob, old, new):
    field = blob[START:START + SIZE]
    args = field.split(b'\0', 1)[0]
    if args.count(old) != 1 or new in args:
        raise SystemExit('Oriole 1800-second COW: unexpected command line')
    updated = args.replace(old, new)
    if len(updated) >= SIZE:
        raise SystemExit('Oriole 1800-second COW: command line overflow')
    return blob[:START] + updated + bytes(SIZE - len(updated)) + blob[START + SIZE:]


def check(blob):
    if len(blob) != base.PAYLOAD_SIZE or hashlib.sha256(blob).hexdigest() != PAYLOAD_SHA:
        raise SystemExit('Oriole 1800-second COW: unreviewed payload')
    original = replace_arg(blob, NEW, OLD)
    base.check(original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--base', type=Path)
    group.add_argument('--check', type=Path)
    group.add_argument('--check-image', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.base:
        if not args.out:
            parser.error('--base requires --out')
        original = args.base.read_bytes()
        base.check(original)
        result = replace_arg(original, OLD, NEW)
        check(result)
        args.out.write_bytes(result)
    elif args.check:
        check(args.check.read_bytes())
    else:
        image = args.check_image.read_bytes()
        if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
            raise SystemExit('Oriole 1800-second COW: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        offset = 4096 + ((kernel_size + 4095) & ~4095)
        if offset + ramdisk_size > len(image):
            raise SystemExit('Oriole 1800-second COW: truncated image')
        check(image[offset:offset + ramdisk_size])
    print('Oriole 1800-second 512 MiB COW payload: exact input verified')


if __name__ == '__main__':
    main()
