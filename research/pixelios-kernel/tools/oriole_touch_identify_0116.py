#!/usr/bin/env python3
"""Build/check the exact Oriole XNU FTM5 ACPM PMIC rail-cycle ID payload.

Only the /sweet-touch node and fixed identify boot args differ from the
previous 1800-second framebuffer profile. The kernel and base ADT are pinned.
No iOS root or Apple binary is distributed by this script.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import adt, mkadt, mkpayload, oriole_ufsroot_cow_pool512_fbsnap as base

KERNEL_SHA = 'd21a69b6481bcdd4cb2e23556b9407ff3eebd456cf7d85e91dced3b854f44774'
BASE_ADT_SHA = base.ADT_SHA
ADT_SHA = 'b85187b0fb3eeec4129c896b508680b27392f2d79ccc24ea95e47e18aa0d4164'
PAYLOAD_SHA = '0ccaac530588a86864258d00c35cf7e6aaf8964a4d1ba2d8eaa481027bdfc4a2'
PAYLOAD_SIZE = 16716768
TOUCH_ARGS = (' sweettouch=1 sweettouchdelay=2 sweettouchmux=1 '
              'sweettouchclk=3 sweettouchcs=1 '
              'sweettouchrailcycle=1 sweettouchpoke=m:10c00640=10=0;d:100;m:10c0180c=f=5;')
ARGS = base.ARGS.replace('sweetrestart=1800', 'sweetrestart=180') + TOUCH_ARGS


def require_hash(data, expected, what):
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'Oriole touch identify: unexpected {what}')


def make_adt(base_blob):
    require_hash(base_blob, BASE_ADT_SHA, 'base ADT')
    root, end = adt.parse(base_blob)
    if end != len(base_blob) or any(n.name == 'sweet-touch' for n in root.children):
        raise SystemExit('Oriole touch identify: unexpected base tree')
    generated = mkadt.build(seed=bytes(range(64)), board='oriole')
    candidates = [n for n in generated.children if n.name == 'sweet-touch']
    if len(candidates) != 1 or candidates[0].prop('compatible') != b'google,gs101-ftm5-spi\0':
        raise SystemExit('Oriole touch identify: unexpected controller node')
    candidates[0].props = [
        (name, flags, b'pixelios,oriole-ftm5-spi\0' if name == 'compatible' else value)
        for name, flags, value in candidates[0].props
    ]
    root.children.append(candidates[0])
    new_adt = adt.serialize(root)
    require_hash(new_adt, ADT_SHA, 'touch ADT')
    return new_adt


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole touch identify: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA, 'payload')
    args = blob[0x48:0x48 + 608].split(b'\0', 1)[0].decode('ascii')
    if args != ARGS or len(args) >= 608:
        raise SystemExit('Oriole touch identify: command line mismatch')
    adt_off, adt_size = struct.unpack_from('<QQ', blob, 0x20)
    if adt_off + adt_size > len(blob) or adt_size == 0:
        raise SystemExit('Oriole touch identify: ADT bounds invalid')
    require_hash(blob[adt_off:adt_off + adt_size], ADT_SHA, 'embedded ADT')
    tree, end = adt.parse(blob[adt_off:adt_off + adt_size])
    nodes = [node for node in tree.children if node.name == 'sweet-touch']
    if end != adt_size or len(nodes) != 1 or \
            nodes[0].prop('compatible') != b'pixelios,oriole-ftm5-spi\0':
        raise SystemExit('Oriole touch identify: controller compatible mismatch')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--kernel', type=Path)
    g.add_argument('--check', type=Path)
    g.add_argument('--check-image', type=Path)
    p.add_argument('--base-adt', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    if a.kernel:
        if not a.base_adt or not a.out:
            p.error('--kernel requires --base-adt and --out')
        require_hash(a.kernel.read_bytes(), KERNEL_SHA, 'kernel')
        tree = make_adt(a.base_adt.read_bytes())
        a.out.parent.mkdir(parents=True, exist_ok=True)
        tree_path = a.out.parent / 'oriole-touch-identify.adt'
        tree_path.write_bytes(tree)
        blob, _ = mkpayload.build(a.kernel, tree_path, ARGS, board='bluejay')
        check(blob)
        a.out.write_bytes(blob)
    elif a.check:
        check(a.check.read_bytes())
    else:
        image = a.check_image.read_bytes()
        if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 4:
            raise SystemExit('Oriole touch identify: expected Android v4 image')
        kernel_size, ramdisk_size = struct.unpack_from('<II', image, 8)
        off = 4096 + ((kernel_size + 4095) & ~4095)
        if off + ramdisk_size > len(image):
            raise SystemExit('Oriole touch identify: truncated image')
        check(image[off:off + ramdisk_size])
    print('Oriole FTM5 identify-only payload: exact inputs verified')


if __name__ == '__main__':
    main()
