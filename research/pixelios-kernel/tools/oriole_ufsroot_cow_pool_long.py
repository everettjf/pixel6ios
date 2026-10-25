#!/usr/bin/env python3
"""Exact 900-second Oriole COW trial derived from the checked 300-second payload."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import oriole_ufsroot_cow_pool as pool

OLD = b'sweetrestart=300'
NEW = b'sweetrestart=900'
PAYLOAD_SHA = 'dcb7a3471110b090094b3fe9423caefa9b9bff85f95e85fbc9fb56e68a0ae7fb'


def extend(blob):
    pool.check(blob)
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0]
    if args.count(OLD) != 1 or blob.count(OLD) != 1 or NEW in blob:
        raise SystemExit('Oriole long trial: unexpected boot arguments')
    offset = blob.index(OLD)
    if not 0x48 <= offset < 0x48 + len(args):
        raise SystemExit('Oriole long trial: restart argument outside command line')
    result = blob[:offset] + NEW + blob[offset + len(OLD):]
    check(result)
    return result


def check(blob):
    if len(blob) != pool.PAYLOAD_SIZE or hashlib.sha256(blob).hexdigest() != PAYLOAD_SHA:
        raise SystemExit('Oriole long trial: unreviewed payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0]
    if args.count(NEW) != 1 or OLD in blob or blob.count(NEW) != 1:
        raise SystemExit('Oriole long trial: unexpected command line')
    offset = blob.index(NEW)
    original = blob[:offset] + OLD + blob[offset + len(NEW):]
    pool.check(original)


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
        args.out.write_bytes(extend(args.base.read_bytes()))
    elif args.check:
        check(args.check.read_bytes())
    else:
        image = args.check_image.read_bytes()
        if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
            raise SystemExit('Oriole long trial: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        offset = 4096 + ((kernel_size + 4095) & ~4095)
        if offset + ramdisk_size > len(image):
            raise SystemExit('Oriole long trial: truncated Android image')
        check(image[offset:offset + ramdisk_size])
    print('Oriole 900-second COW payload: exact input verified')


if __name__ == '__main__':
    main()
