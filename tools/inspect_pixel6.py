#!/usr/bin/env python3
"""Collect selected hardware facts from one authorized oriole; never reboot or write it."""
import argparse
import datetime
import json
import os
import pathlib
import shlex
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
DT = '/sys/firmware/devicetree/base'
PROPS = [
    'ro.product.model', 'ro.product.device', 'ro.board.platform', 'ro.hardware',
    'ro.build.fingerprint', 'ro.build.version.release', 'ro.build.version.security_patch',
    'ro.bootloader', 'ro.boot.flash.locked', 'ro.boot.vbmeta.device_state',
    'ro.boot.verifiedbootstate', 'ro.oem_unlock_supported', 'sys.oem_unlock_allowed',
    'ro.boot.slot_suffix', 'ro.boot.hardware.sku',
]
QUERIES = {
    'identity': ['id'],
    'kernel': ['uname', '-a'],
    'memory': ['cat', '/proc/meminfo'],
    'cpu': ['cat', '/proc/cpuinfo'],
    'cpu_id_register': ['cat', '/sys/devices/system/cpu/cpu0/regs/identification/id_aa64isar1_el1'],
    'display_size': ['wm', 'size'],
    'partitions': ['cat', '/proc/partitions'],
    'input': ['cat', '/proc/bus/input/devices'],
    'input_capabilities': ['getevent', '-lp'],
    'input_sysfs_links': ['ls', '-l', '/sys/class/input'],
    'block_names': ['ls', '-l', '/dev/block/by-name'],
    'block_sizes': ['sh', '-c', 'for d in /sys/class/block/sd?; do echo "$d"; cat "$d/size" "$d/queue/logical_block_size"; done'],
    'touch_devices': ['sh', '-c', 'for d in /sys/bus/spi/devices/*; do echo "$d"; cat "$d/modalias" "$d/uevent"; readlink "$d/driver"; done'],
    'panel': ['sh', '-c', 'for f in /sys/class/drm/*/panel_name /sys/class/drm/*/panel_extinfo /sys/class/graphics/fb0/name /sys/class/graphics/fb0/virtual_size /sys/class/graphics/fb0/stride /sys/class/graphics/fb0/bits_per_pixel; do if test -r "$f"; then echo "$f"; cat "$f"; fi; done'],
    'dt_top': ['ls', DT],
    'dt_touch_paths': ['ls', DT + '/spi@10D40000/touchscreen@0'],
    'dt_register_paths': ['sh', '-c', f'for d in {DT}/memory* {DT}/reserved-memory/*; do if test -d "$d"; then echo "$d/reg"; fi; done'],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--adb', default=str(ROOT / 'tools/platform-tools/adb'))
    ap.add_argument('--out', type=pathlib.Path, default=ROOT / 'private/device-facts.json')
    args = ap.parse_args()

    def run(argv):
        try:
            env = dict(os.environ, ADB_LIBUSB='1')
            p = subprocess.run([args.adb] + argv, capture_output=True, timeout=20, env=env)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, b'', b'timed out'

    rc, out, _ = run(['devices'])
    devices = [line.split() for line in out.decode().splitlines()[1:] if line.strip()]
    if rc or len(devices) != 1 or devices[0][1] != 'device':
        raise SystemExit('Need exactly one authorized ADB device; no device queried.')
    serial = devices[0][0]

    def query(argv, binary=False):
        rc, out, err = run(['-s', serial, 'shell', '-T', shlex.join(argv)])
        err = err.decode(errors='replace').replace(serial, '[redacted]')
        denied = b'Permission denied' in out or 'Permission denied' in err
        if denied and not rc:
            rc = 13  # A successful final shell statement can mask an earlier denied read.
        if binary:
            return rc, out, err
        return {'returncode': rc, 'stdout': out.decode(errors='replace').replace(serial, '[redacted]'), 'stderr': err,
                'permission_denied': denied}

    identity = query(['getprop', 'ro.product.device'])
    if identity['returncode'] or identity['stdout'].strip() != 'oriole':
        raise SystemExit('Device is not oriole; stopped after identity query.')
    facts = {'collected_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'scope': 'Read-only Android shell queries. No root, reboot, flash, unlock, or writes to device.',
             'properties': {}, 'queries': {}, 'device_tree': {}}
    for name in PROPS:
        facts['properties'][name] = query(['getprop', name])
    for name, argv in QUERIES.items():
        facts['queries'][name] = query(argv)
    paths = facts['queries']['dt_register_paths']['stdout'].splitlines()
    paths += [DT + '/model', DT + '/compatible', DT + '/#address-cells', DT + '/#size-cells',
              DT + '/reserved-memory/#address-cells', DT + '/reserved-memory/#size-cells']
    for path in paths:
        if not path.startswith(DT + '/') or '\x00' in path:
            continue
        rc, data, err = query(['cat', path], binary=True)
        item = {'returncode': rc, 'hex': data.hex() if rc == 0 else '', 'stderr': err}
        if rc == 0 and len(data) % 4 == 0:
            item['be32_cells'] = [int.from_bytes(data[i:i+4], 'big') for i in range(0, len(data), 4)]
        facts['device_tree'][path.removeprefix(DT)] = item
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.out.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + '\n')
    args.out.chmod(0o600)
    print('Saved:', args.out)
    for p in PROPS:
        print(p + ': ' + facts['properties'][p]['stdout'].strip())
    print('Device-tree properties collected:', len(facts['device_tree']))
    print('Unavailable or partial queries:', ', '.join(k for k,v in facts['queries'].items() if v['returncode']) or 'none')


if __name__ == '__main__':
    main()
