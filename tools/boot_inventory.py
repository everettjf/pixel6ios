#!/usr/bin/env python3
"""Temporarily boot only a fresh, headless inventory image on the recorded oriole."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / 'research/pixelios-kernel'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', type=Path, default=CHECKOUT / 'shim/out/shim-boot-avb.img')
    args = ap.parse_args()
    image = args.image.resolve()
    serial = (ROOT / 'private/target-serial').read_text().strip()
    if not serial or any(c.isspace() for c in serial):
        raise SystemExit('Invalid recorded target')
    meta = json.loads(Path(str(image) + '.meta.json').read_text())
    blob = image.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if meta.get('kind') != 'probe' or meta.get('sha256') != digest:
        raise SystemExit('Image provenance/hash mismatch')
    if blob[:8] != b'ANDROID!' or struct.unpack_from('<I', blob, 40)[0] != 4:
        raise SystemExit('Expected Android boot header v4')
    kernel_size = struct.unpack_from('<I', blob, 8)[0]
    kernel = blob[4096:4096 + kernel_size]
    if kernel[0x38:0x3c] != b'ARMd' or b'oriole: headless, no storage access' not in kernel:
        raise SystemExit('Expected uncompressed headless Oriole inventory kernel')
    if '#define UART_BASE 0x0UL' not in (CHECKOUT / 'shim/out/board_config.h').read_text():
        raise SystemExit('Current build configuration is not headless Oriole')
    subprocess.run([str(ROOT / 'artifacts/build-venv/bin/python'), 'tools/imgmeta.py',
                    'check', str(image), '--expect', 'probe'], cwd=CHECKOUT, check=True)
    base = [str(ROOT / 'tools/platform-tools/fastboot'), '-s', serial]

    def getvar(name):
        p = subprocess.run(base + ['getvar', name], capture_output=True, text=True, timeout=10)
        text = (p.stdout + p.stderr).replace(serial, '[redacted]')
        if p.returncode:
            raise SystemExit('Cannot read fastboot variable ' + name)
        return text

    if 'product: oriole' not in getvar('product') or 'unlocked: yes' not in getvar('unlocked'):
        raise SystemExit('Target must be unlocked oriole')
    if len(blob) != 0x4000000:
        raise SystemExit('Expected audited 64 MiB AVB-footed temporary image')
    if 'partition-size:boot_a: 0x4000000' not in getvar('partition-size:boot_a'):
        raise SystemExit('Unexpected boot partition geometry')
    record = {'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'board': 'oriole', 'mode': 'inventory', 'image': str(image),
              'sha256': digest, 'source_commit': meta.get('git_head')}
    path = ROOT / 'private/inventory-last-boot.json'
    path.write_text(json.dumps(record, indent=2) + '\n')
    print('Booting verified headless inventory temporarily; SHA256=' + digest, flush=True)
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
