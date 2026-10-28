#!/usr/bin/env python3
"""Read-only preflight for the separately pinned Oriole GUI-touch trials.

This program never boots, flashes, erases, or changes a device. It checks the
local private images first, then queries an explicitly recorded fastboot target.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BOOT_SHA = 'b6b152dfba0228d1adf03339ad09493c5ccc96c2c0e10bcfceeb4d62c1dbfc11'
BOOT_SHA_0121 = 'a153da85ce9bbd3f519c83739e4d6cab1b1df7e220aa896f528c7c294bdb8d2d'
BOOT_SHA_0122 = 'cf4ef12866af697903d76a5eaae188cf80ee74bbe3a45997034f429a3e42701c'
BOOT_SHA_0123 = '64a6aa547b5cac811b71ff8f80f7f0a9374fb18ad32ba8fe91cc4e87671abff7'
BOOT_SHA_0124 = '34951d115aa9e933bf1b2b69e8897fcd74779bb048e8693c008c82c178e692fb'
BOOT_SHA_0125 = 'd13bf273969dff02a101f2e70c857f7bcf7f5d9b61360448dc12146a35806a4e'
ROOT_SHA = '8b53c7102ba7e057483910c60f769b50f79046e5e60829052b401f7c017e0c67'
SPARSE_MAGIC = 0xED26FF3A
TRIALS = {
    '0120': (BOOT_SHA, ROOT / 'private/touch-xnu-source/relink-0120/oriole-touch-gui-avb.img'),
    '0121': (BOOT_SHA_0121, ROOT / 'private/touch-xnu-source/relink-0121/oriole-touch-gui-avb.img'),
    '0122': (BOOT_SHA_0122, ROOT / 'private/touch-xnu-source/relink-0122/oriole-touch-gui-avb.img'),
    '0123': (BOOT_SHA_0123, ROOT / 'private/touch-xnu-source/relink-0122/oriole-touch-gui-extended-avb.img'),
    '0124': (BOOT_SHA_0124, ROOT / 'private/oriole-net-route-source/relink-0123/oriole-netroute-0124-avb.img'),
    '0125': (BOOT_SHA_0125, ROOT / 'private/oriole-net-route-source/relink-0124/oriole-usb-resource-0125-avb.img'),
}


def fail(message):
    raise SystemExit('REFUSED: ' + message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def check_images(boot, root, boot_sha=BOOT_SHA):
    if not boot.is_file() or boot.stat().st_size != 64 * 1024 * 1024:
        fail('expected the reviewed 64 MiB temporary boot image')
    if digest(boot) != boot_sha:
        fail('temporary boot image SHA-256 changed')
    if not root.is_file() or digest(root) != ROOT_SHA:
        fail('iOS root image SHA-256 changed or is missing')
    with root.open('rb') as stream:
        header = stream.read(28)
    if len(header) != 28:
        fail('truncated Android sparse header')
    magic, major, minor, file_hdr, chunk_hdr, block_size, blocks, chunks, _checksum = struct.unpack(
        '<IHHHHIIII', header)
    if (magic != SPARSE_MAGIC or (major, minor, file_hdr, chunk_hdr, block_size)
            != (1, 0, 28, 12, 4096) or blocks != 4194304 or chunks == 0):
        fail('unexpected iOS root sparse geometry')
    return blocks * block_size


def fastboot_value(output, field):
    prefix = r'(?:\(bootloader\)[ \t]*)?' + re.escape(field) + ':'
    matches = [line for line in output.splitlines() if re.match(prefix, line)]
    if len(matches) != 1:
        fail('missing or duplicate fastboot value: ' + field)
    m = re.fullmatch(prefix + r'[ \t]*(\S+)[ \t]*', matches[0])
    if not m:
        fail('malformed fastboot value: ' + field)
    return m[1]


def check_device(fastboot, serial, baseline, expanded_size, run=subprocess.run):
    if not re.fullmatch(r'[A-Za-z0-9._-]+', serial):
        fail('invalid recorded target serial')
    try:
        devices = run([str(fastboot), 'devices', '-l'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        fail('cannot enumerate fastboot devices')
    if devices.returncode:
        fail('fastboot enumeration failed')
    ids = [line.split()[0] for line in devices.stdout.splitlines() if line.strip()]
    if ids != [serial]:
        fail('expected exactly the recorded Pixel 6 in fastboot')

    def getvar(field):
        try:
            result = run([str(fastboot), '-s', serial, 'getvar', field],
                         capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            fail('fastboot getvar failed: ' + field)
        if result.returncode:
            fail('fastboot getvar failed: ' + field)
        return fastboot_value(result.stdout + result.stderr, field)

    if getvar('product') != 'oriole' or getvar('unlocked') != 'yes':
        fail('target is not an unlocked oriole')
    if baseline.get('slot') not in ('a', 'b') or not baseline.get('bootloader'):
        fail('invalid private firmware baseline')
    if getvar('current-slot') != baseline['slot'] or \
            getvar('version-bootloader') != baseline['bootloader']:
        fail('phone firmware or slot differs from the recorded baseline')
    for field, expected in [('partition-size:boot_' + baseline['slot'], 64 * 1024 * 1024),
                            ('partition-size:userdata', None)]:
        try:
            size = int(getvar(field), 0)
        except ValueError:
            fail('invalid partition geometry: ' + field)
        if expected is not None and size != expected:
            fail('unexpected partition geometry: ' + field)
        if expected is None and size < expanded_size:
            fail('unexpected partition geometry: ' + field)
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline', action='store_true', help='check local images only; do not query fastboot')
    p.add_argument('--trial', choices=TRIALS, default='0120', help='exact candidate to verify (default: 0120)')
    p.add_argument('--boot-image', type=Path, help='override the selected trial image path; SHA remains pinned')
    p.add_argument('--root-image', type=Path, default=ROOT / 'artifacts/oriole-root/ios16-oriole-root.nojournal.sparse.img')
    p.add_argument('--fastboot', type=Path, default=ROOT / 'tools/platform-tools/fastboot')
    args = p.parse_args()
    boot_sha, default_boot = TRIALS[args.trial]
    expanded = check_images(args.boot_image or default_boot, args.root_image, boot_sha)
    print(f'Local images match reviewed SHA-256; sparse expansion {expanded // (1024**3)} GiB')
    if not args.offline:
        try:
            serial = (ROOT / 'private/target-serial').read_text().strip()
            baseline = json.loads((ROOT / 'private/boot-baseline.json').read_text())
        except (OSError, ValueError):
            fail('recorded target or firmware baseline unavailable')
        check_device(args.fastboot, serial, baseline, expanded)
        print('Exactly one recorded unlocked oriole matches firmware, slot, and partition geometry')
    print('PREFLIGHT PASS (read-only). No device action was performed.')


if __name__ == '__main__':
    main()
