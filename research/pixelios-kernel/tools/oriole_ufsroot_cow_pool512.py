#!/usr/bin/env python3
"""Pinned Oriole 512 MiB RAM-COW trial with a 900-second boot argument."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import oriole_ufsroot_cow as cow

KERNEL_SHA = 'eb38bc975e299f83c94c7e83a332f484d414bdc209064b30bf87e15f0ab1dd1c'
PAYLOAD_SHA = 'aadb1029d93b49f21c38a77c06b6737f412c0dcf97d3e30f5d2804fe7d7e2599'
PAYLOAD_SIZE = 16714528
ARGS = cow.ARGS.replace('sweetrestart=300', 'sweetrestart=900')


def check(blob):
    if len(blob) != PAYLOAD_SIZE or hashlib.sha256(blob).hexdigest() != PAYLOAD_SHA:
        raise SystemExit('Oriole 512 MiB COW: unreviewed payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS:
        raise SystemExit('Oriole 512 MiB COW: unexpected boot arguments')
    required = dict(cow.REQUIRED, sweetrestart='900')
    tokens = [token.partition('=') for token in args.split()]
    keys = [key for key, _, _ in tokens]
    values = {key: value for key, sep, value in tokens if sep}
    if len(keys) != len(set(keys)) or any(values.get(k) != v for k, v in required.items()):
        raise SystemExit('Oriole 512 MiB COW: safety guard changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--kernel', type=Path)
    group.add_argument('--check', type=Path)
    group.add_argument('--check-image', type=Path)
    parser.add_argument('--product', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.kernel:
        if not args.product or not args.out:
            parser.error('--kernel requires --product and --out')
        cow.ARGS = ARGS
        cow.REQUIRED['sweetrestart'] = '900'
        blob, _ = cow.build(args.kernel, args.product, args.out, kernel_sha=KERNEL_SHA)
        check(blob)
        (args.out / 'oriole-cow512-payload.bin').write_bytes(blob)
    elif args.check:
        check(args.check.read_bytes())
    else:
        image = args.check_image.read_bytes()
        if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
            raise SystemExit('Oriole 512 MiB COW: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        offset = 4096 + ((kernel_size + 4095) & ~4095)
        if offset + ramdisk_size > len(image):
            raise SystemExit('Oriole 512 MiB COW: truncated image')
        check(image[offset:offset + ramdisk_size])
    print('Oriole 512 MiB RAM-COW payload: exact input verified')


if __name__ == '__main__':
    main()
