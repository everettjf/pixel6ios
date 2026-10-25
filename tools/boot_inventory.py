#!/usr/bin/env python3
"""Temporarily boot a verified, narrowly gated probe on the recorded Oriole."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / 'research/pixelios-kernel'


KNOWN_MODES = frozenset(('inventory', 'inventory-display', 'inventory-ufs',
                         'inventory-ufs-ready',
                         'xnu-ramprobe', 'xnu-loadcheck', 'xnu-resetcheck',
                         'xnu-md0usb', 'xnu-md0usb-loadcheck',
                         'xnu-ufsroot', 'xnu-ufsroot-loadcheck',
                         'xnu-ufsroot-preparecheck'))


def fastboot_value(raw, field):
    prefix = r'(?:\(bootloader\)[ \t]*)?' + re.escape(field) + ':'
    lines = [line for line in raw.splitlines() if re.match(prefix, line)]
    if len(lines) != 1:
        raise SystemExit('Expected exactly one fastboot value: ' + field)
    match = re.fullmatch(prefix + r'[ \t]*(\S+)[ \t]*', lines[0])
    if not match:
        raise SystemExit('Malformed fastboot value: ' + field)
    values = [match[1]]
    return values[0]


def check_firmware(getvar, baseline, mode):
    """Reject OTA/slot drift before temporary boot; never auto-adopt new firmware."""
    if not isinstance(baseline, dict):
        raise SystemExit('Invalid firmware baseline schema')
    slot, version, modes = (baseline.get(k) for k in ('slot', 'bootloader', 'allowed_modes'))
    if (slot not in ('a', 'b') or not isinstance(version, str) or not version.strip()
            or any(c.isspace() for c in version) or not isinstance(modes, list)
            or any(not isinstance(m, str) or m not in KNOWN_MODES for m in modes)
            or len(modes) != len(set(modes))):
        raise SystemExit('Invalid firmware baseline schema')
    if mode not in modes or mode not in KNOWN_MODES:
        raise SystemExit('Profile is not validated for this firmware baseline')
    for field, expected in [('version-bootloader', version), ('current-slot', slot)]:
        if fastboot_value(getvar(field), field) != expected:
            raise SystemExit('Firmware baseline changed: ' + field +
                             '; re-inspect and revalidate before booting')
    field = 'partition-size:boot_' + slot
    try:
        size = int(fastboot_value(getvar(field), field), 0)
    except ValueError:
        raise SystemExit('Invalid boot partition geometry') from None
    if size != 0x4000000:
        raise SystemExit('Unexpected boot partition geometry')
    return slot


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--md0usb', action='store_true', help='exact md0 + kernel USB logging experiment')
    group.add_argument('--md0usb-loadcheck', action='store_true', help='copy md0 USB payload but skip kernel entry')
    group.add_argument('--ufsroot', action='store_true', help='exact read-only UFS root diagnostic')
    group.add_argument('--ufsroot-loadcheck', action='store_true', help='copy UFS-root payload but skip kernel entry')
    group.add_argument('--ufsroot-preparecheck', action='store_true', help='prepare/stop UFS, then skip kernel entry')
    group.add_argument('--ramprobe', action='store_true', help='exact reviewed RAM-only XNU experiment')
    group.add_argument('--loadcheck', action='store_true', help='load/copy then intentionally skip the XNU branch')
    group.add_argument('--resetcheck', action='store_true', help='load/copy, log volatile reset SMC, then reset')
    ap.add_argument('--image', type=Path, default=CHECKOUT / 'shim/out/shim-boot-avb.img')
    args = ap.parse_args()
    md0profile = args.md0usb or args.md0usb_loadcheck
    ufsprofile = args.ufsroot or args.ufsroot_loadcheck or args.ufsroot_preparecheck
    ramprofile = args.ramprobe or args.loadcheck or args.resetcheck or md0profile or ufsprofile
    image = args.image.resolve()
    serial = (ROOT / 'private/target-serial').read_text().strip()
    if not serial or any(c.isspace() for c in serial):
        raise SystemExit('Invalid recorded target')
    meta = json.loads(Path(str(image) + '.meta.json').read_text())
    blob = image.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    kind = 'xnu' if ramprofile else 'probe'
    if meta.get('kind') != kind or meta.get('sha256') != digest:
        raise SystemExit('Image provenance/hash mismatch')
    if blob[:8] != b'ANDROID!' or struct.unpack_from('<I', blob, 40)[0] != 4:
        raise SystemExit('Expected Android boot header v4')
    kernel_size = struct.unpack_from('<I', blob, 8)[0]
    kernel = blob[4096:4096 + kernel_size]
    markers = ((b'ORIOLE_UFS_ROOT',) if ufsprofile else (b'ORIOLE_RAM_PROBE',) if ramprofile else (
        b'oriole: headless, no storage access', b'oriole: headless, media-read-only UFS/GPT'))
    if kernel[0x38:0x3c] != b'ARMd' or not any(m in kernel for m in markers):
        raise SystemExit('Expected uncompressed reviewed Oriole profile')
    if ramprofile:
        subprocess.run([str(ROOT / 'artifacts/build-venv/bin/python'),
                        str(CHECKOUT / ('tools/oriole_ufsroot.py' if ufsprofile else 'tools/oriole_md0usb.py' if md0profile else 'tools/oriole_ramprobe.py')), '--check-image', str(image)], check=True)
    if ramprofile and ((b'ORIOLE_LOADCHECK' in kernel) != (args.loadcheck or args.resetcheck or args.md0usb_loadcheck or args.ufsroot_loadcheck)):
        raise SystemExit('RAM profile must match explicit transfer/skip selection')
    if ramprofile and ((b'ORIOLE_MD0_USB' in kernel) != md0profile):
        raise SystemExit('md0 USB image must match explicit host profile')
    if ramprofile and ((b'ORIOLE_UFS_ROOT' in kernel) != ufsprofile):
        raise SystemExit('UFS-root image must match explicit host profile')
    if ramprofile and ((b'ORIOLE_UFS_PREPARECHECK' in kernel) != args.ufsroot_preparecheck):
        raise SystemExit('UFS prepare-check image must match explicit host profile')
    if ramprofile and ((b'ORIOLE_RESETCHECK' in kernel) != args.resetcheck):
        raise SystemExit('Reset-check image must match explicit host selection')
    if '#define UART_BASE 0x0UL' not in (CHECKOUT / 'shim/out/board_config.h').read_text():
        raise SystemExit('Current build configuration is not headless Oriole')
    subprocess.run([str(ROOT / 'artifacts/build-venv/bin/python'), 'tools/imgmeta.py',
                    'check', str(image), '--expect', kind], cwd=CHECKOUT, check=True)
    base = [str(ROOT / 'tools/platform-tools/fastboot'), '-s', serial]

    def getvar(name):
        try:
            p = subprocess.run(base + ['getvar', name], capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            raise SystemExit('Fastboot variable timed out: ' + name) from None
        text = (p.stdout + p.stderr).replace(serial, '[redacted]')
        if p.returncode:
            raise SystemExit('Cannot read fastboot variable ' + name)
        return text

    if (fastboot_value(getvar('product'), 'product') != 'oriole' or
            fastboot_value(getvar('unlocked'), 'unlocked') != 'yes'):
        raise SystemExit('Target must be unlocked oriole')
    mode = ('xnu-ufsroot-preparecheck' if args.ufsroot_preparecheck else 'xnu-ufsroot-loadcheck' if args.ufsroot_loadcheck else 'xnu-ufsroot' if args.ufsroot else 'xnu-md0usb-loadcheck' if args.md0usb_loadcheck else 'xnu-md0usb' if args.md0usb else 'xnu-resetcheck' if args.resetcheck else 'xnu-loadcheck' if args.loadcheck else 'xnu-ramprobe' if args.ramprobe else 'inventory-ufs-ready' if b'UFS READY-HOST' in kernel else 'inventory-ufs' if b'UFS INVENTORY' in kernel else
            'inventory-display' if b'RDMA channel' in kernel else 'inventory')
    baseline = json.loads((ROOT / 'private/boot-baseline.json').read_text())
    slot = check_firmware(getvar, baseline, mode)
    if len(blob) != 0x4000000:
        raise SystemExit('Expected audited 64 MiB AVB-footed temporary image')
    record = {'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'board': 'oriole', 'mode': mode, 'image': str(image),
              'bootloader': baseline['bootloader'], 'slot': slot,
              'sha256': digest, 'source_commit': meta.get('git_head')}
    path = ROOT / ('private/ramprobe-last-boot.json' if ramprofile else 'private/inventory-last-boot.json')
    path.write_text(json.dumps(record, indent=2) + '\n')
    print('Temporary boot of verified ' + mode + '; SHA256=' + digest, flush=True)
    try:
        p = subprocess.run(base + ['boot', str(image)], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise SystemExit('Temporary boot command timed out; inspect device state before retrying')
    record.update(returncode=p.returncode, output=(p.stdout + p.stderr).replace(serial, '[redacted]'))
    path.write_text(json.dumps(record, indent=2) + '\n')
    path.chmod(0o600)
    print(record['output'], flush=True)
    raise SystemExit(p.returncode)


if __name__ == '__main__':
    main()
