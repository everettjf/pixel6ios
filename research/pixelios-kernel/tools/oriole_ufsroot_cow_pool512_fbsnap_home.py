#!/usr/bin/env python3
"""Exact silent Oriole panel snapshot with one late Home HID test."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import mkpayload, oriole_ufsroot_cow_pool512_fbsnap_silent as base

KERNEL_SHA = base.KERNEL_SHA
ADT_SHA = base.ADT_SHA
PAYLOAD_SHA = '97cef6179801eef92599b3017d8ccbb4a852840b86610f48d9ef1b7c1373b63e'
PAYLOAD_SIZE = base.PAYLOAD_SIZE
ARGS = base.ARGS + ' sweethidtest=1300'


def require_hash(data, expected, name):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Oriole Home HID diagnostic: unexpected ' + name)


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole Home HID diagnostic: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS:
        raise SystemExit('Oriole Home HID diagnostic: command line mismatch')
    keys = [token.partition('=')[0] for token in args.split()]
    if len(keys) != len(set(keys)) or not args.endswith(' sweethidtest=1300'):
        raise SystemExit('Oriole Home HID diagnostic: duplicate or unexpected boot argument')
    # The base profile owns and checks all storage, reset, and USB safety args.
    baseline = args.removesuffix(' sweethidtest=1300')
    if baseline != base.ARGS:
        raise SystemExit('Oriole Home HID diagnostic: base command line changed')


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
            raise SystemExit('Oriole Home HID diagnostic: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        offset = 4096 + ((kernel_size + 4095) & ~4095)
        if offset + ramdisk_size > len(image):
            raise SystemExit('Oriole Home HID diagnostic: truncated image')
        check(image[offset:offset + ramdisk_size])
    print('Oriole Home HID diagnostic: exact payload verified')


if __name__ == '__main__':
    main()
