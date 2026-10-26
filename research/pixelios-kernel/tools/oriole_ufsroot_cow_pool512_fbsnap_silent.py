#!/usr/bin/env python3
"""Exact Oriole panel-snapshot payload without framebuffer serial output."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import mkpayload, oriole_ufsroot_cow_pool512_fbsnap as base

KERNEL_SHA = base.KERNEL_SHA
ADT_SHA = base.ADT_SHA
PAYLOAD_SHA = '5b595108e7d6c14f59f154a6ec16cb200b1b6af7daac84b4b935df7cadd73e61'
PAYLOAD_SIZE = base.PAYLOAD_SIZE
ARGS = base.ARGS.replace('serial=3', 'serial=0')
assert ARGS != base.ARGS and 'serial=3' not in ARGS


def require_hash(data, expected, name):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Oriole silent panel diagnostic: unexpected ' + name)


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole silent panel diagnostic: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS:
        raise SystemExit('Oriole silent panel diagnostic: command line mismatch')
    tokens = [token.partition('=') for token in args.split()]
    keys = [key for key, _, _ in tokens]
    values = {key: value for key, sep, value in tokens if sep}
    required = {'serial': '0', 'cpus': '1', 'sweetrestart': '1800',
                'sweetusb': '2', 'sweetremote': '0', 'ufsrw': '0',
                'ufscow': '1', 'sweetlog': '0', 'sweetfbsnap': '1'}
    if len(keys) != len(set(keys)) or any(values.get(key) != value for key, value in required.items()):
        raise SystemExit('Oriole silent panel diagnostic: safety guard changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--kernel', type=Path)
    group.add_argument('--check', type=Path)
    group.add_argument('--check-image', type=Path)
    parser.add_argument('--adt', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.kernel:
        if not args.adt or not args.out:
            parser.error('--kernel requires --adt and --out')
        require_hash(args.kernel.read_bytes(), KERNEL_SHA, 'kernel')
        require_hash(args.adt.read_bytes(), ADT_SHA, 'ADT')
        blob, _ = mkpayload.build(args.kernel, args.adt, ARGS, board='bluejay')
        check(blob)
        args.out.write_bytes(blob)
    elif args.check:
        check(args.check.read_bytes())
    else:
        image = args.check_image.read_bytes()
        if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
            raise SystemExit('Oriole silent panel diagnostic: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        offset = 4096 + ((kernel_size + 4095) & ~4095)
        if offset + ramdisk_size > len(image):
            raise SystemExit('Oriole silent panel diagnostic: truncated image')
        check(image[offset:offset + ramdisk_size])
    print('Oriole silent panel diagnostic: exact payload verified')


if __name__ == '__main__':
    main()
