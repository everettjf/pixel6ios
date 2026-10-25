#!/usr/bin/env python3
"""Build/check the single reviewed RAM-only Oriole experiment; no generic XNU gate.

The complete payload hash binds kernel bytes, init, boot arguments and every
ADT property (including MMIO). Changing any input requires a new review.
Apple binaries remain local and are never included in this repository.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import adt, mkadt, mkpayload

PAYLOAD_SIZE = 16726576
PAYLOAD_SHA = '6ae22614d729439dcff3345c41f4e3aefd6451be5b77f7518757c89ae9567f66'
KERNEL_SHA = '8e4d38ea655930ef1da4998ab236962caabb9c8af1efaed6a96e243039af2292'
INIT_SHA = 'be90fb2e86b26deab1550cdc84396f7d3421e0c66e8e2685d6e0d470983977d8'
ARGS = ('debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam '
        '-noprogress wdt=-1 wdt_test=no_user_checkin sweetusb=0 rd=md0')


def require_hash(blob, expected):
    if hashlib.sha256(blob).hexdigest() != expected:
        raise SystemExit('Oriole RAM probe: input differs from reviewed artifact')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole RAM probe: payload size mismatch')
    require_hash(blob, PAYLOAD_SHA)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', type=Path)
    g.add_argument('--check-image', type=Path)
    g.add_argument('--kernel', type=Path)
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    if a.check:
        check(a.check.read_bytes())
    elif a.check_image:
        b = a.check_image.read_bytes()
        if b[:8] != b'ANDROID!' or struct.unpack_from('<I', b, 40)[0] != 4:
            raise SystemExit('Expected Android v4 image')
        ks, rs = struct.unpack_from('<II', b, 8)
        off = 4096 + ((ks + 4095) & ~4095)
        check(b[off:off + rs])
    else:
        if not a.out:
            p.error('--kernel requires --out')
        require_hash(a.kernel.read_bytes(), KERNEL_SHA)
        source = ROOT / 'tools/oriole-ram-init.S'
        helper = ROOT / '.upstream/tools/mkinit.py'
        require_hash(source.read_bytes(), 'e0b939074cc84b185fa69f554e504a98d161e2ec1ad9c8ec26b2fa15864da8e3')
        require_hash(helper.read_bytes(), '79b8585105d4ecfc6f47542563577d0c55c22e7eaa517cffb367cf24e7c4e8ac')
        a.out.mkdir(parents=True, exist_ok=True)
        obj, init, tree = [a.out / n for n in ('init.o', 'init.macho', 'oriole.adt')]
        subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios16.0', '-c',
                        str(source), '-o', str(obj)], check=True)
        spec = importlib.util.spec_from_file_location('mkinit', helper)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ib = mod.build(obj.read_bytes())
        require_hash(ib, INIT_SHA)
        init.write_bytes(ib)
        root = mkadt.build(seed=bytes(range(64)), board='oriole', no_ufs=True)
        root.children = [n for n in root.children if n.name not in
                         ('sweet-keys', 'sweet-touch', 'sweet-usb')]
        tree.write_bytes(adt.serialize(root))
        blob, _ = mkpayload.build(a.kernel, tree, ARGS, init, board='oriole')
        check(blob)
        (a.out / 'oriole-payload.bin').write_bytes(blob)
    print('Oriole RAM-only payload: exact reviewed SHA256 verified')


if __name__ == '__main__':
    main()
