#!/usr/bin/env python3
"""Pinned 1800-second Oriole RAM-COW payload with read-only panel sampling."""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import mkpayload, oriole_ufsroot_cow_pool512_long as base

KERNEL_SHA = '822584e5de35ff7172102ef43352c0f6ddfc6ffcff254836645740c7d0e49b2a'
ADT_SHA = '9f1733e2b7729dd4d7f33c103865014f539913bc980f62963e4581de3bda91fc'
PAYLOAD_SHA = '494c9c9989dd4370e8a2aba51bcbb79ec08652919429c4e715986c4c0b1fc379'
PAYLOAD_SIZE = 16714672
ARGS = base.base.ARGS.replace('sweetrestart=900', 'sweetrestart=1800') + ' sweetfbsnap=1'


def require_hash(data, expected, name):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Oriole framebuffer diagnostic: unexpected ' + name)


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole framebuffer diagnostic: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS:
        raise SystemExit('Oriole framebuffer diagnostic: command line mismatch')
    tokens = [token.partition('=') for token in args.split()]
    keys = [key for key, _, _ in tokens]
    values = {key: value for key, sep, value in tokens if sep}
    if len(keys) != len(set(keys)) or any(values.get(key) != value for key, value in
            dict(base.base.cow.REQUIRED, sweetrestart='1800', sweetfbsnap='1').items()):
        raise SystemExit('Oriole framebuffer diagnostic: safety guard changed')


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
            raise SystemExit('Oriole framebuffer diagnostic: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        offset = 4096 + ((kernel_size + 4095) & ~4095)
        if offset + ramdisk_size > len(image):
            raise SystemExit('Oriole framebuffer diagnostic: truncated image')
        check(image[offset:offset + ramdisk_size])
    print('Oriole framebuffer diagnostic: exact payload verified')


if __name__ == '__main__':
    main()
