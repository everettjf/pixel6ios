#!/usr/bin/env python3
"""Capture one exact-image, bounded Oriole PMIC touch-rail cycle."""
import argparse
from datetime import datetime, timezone
import re
import subprocess
import sys
import time

from run_touch_inventory import (CAPTURE_PYTHON, PORT_CHECK, ROOT,
                                 require_single_recorded_fastboot)


def capture_ok(data):
    """Accept only two observed enables and their verified reverse restoration."""
    if b'ACPM CYCLE both rails enabled and read back' not in data:
        return False
    if b'ACPM CYCLE END enabled00000001 restored00000002' not in data:
        return False
    if b'FAILED' in data:
        return False
    sets = re.findall(rb'ACPM CYCLE SET reg([0-9A-F]{8}) on([0-9A-F]{8})', data)
    reads = re.findall(rb'ACPM CYCLE READ reg([0-9A-F]{8}) value([0-9A-F]{8})', data)
    return sets == [(b'0000005C', b'00000001'), (b'0000005D', b'00000001'),
                    (b'0000005D', b'00000000'), (b'0000005C', b'00000000')] and reads == [
                        (b'0000005C', b'0000002C'), (b'0000005D', b'0000003C'),
                        (b'0000005C', b'000000AC'), (b'0000005D', b'000000BC'),
                        (b'0000005D', b'0000003C'), (b'0000005C', b'0000002C')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=90,
                        help='bounded USB capture duration, 30..300 seconds')
    args = parser.parse_args()
    if not 30 <= args.seconds <= 300:
        parser.error('--seconds must be 30..300')
    require_single_recorded_fastboot()
    ports = subprocess.run([str(CAPTURE_PYTHON), '-c', PORT_CHECK], check=True,
                           capture_output=True, text=True, timeout=10)
    if ports.stdout.strip() != '0':
        raise SystemExit('Another inventory USB gadget is already connected')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / 'private/acpm-rail-cycle-inventory' / stamp
    folder.mkdir(parents=True, mode=0o700)
    raw = folder / 'usb.log'
    status = folder / 'capture.txt'
    with status.open('x') as output:
        status.chmod(0o600)
        capture = subprocess.Popen([str(CAPTURE_PYTHON),
                                    str(ROOT / 'tools/capture_inventory_usb.py'),
                                    '--seconds', str(args.seconds), '--out', str(raw)],
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 5
            while not raw.exists() and capture.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if not raw.exists() or capture.poll() is not None:
                raise SystemExit(f'USB capture did not arm; see {status}')
            try:
                boot = subprocess.run([sys.executable, str(ROOT / 'tools/boot_inventory.py'),
                                       '--acpm-rail-cycle'], check=False, timeout=120)
            except subprocess.TimeoutExpired:
                raise SystemExit('Verified temporary boot helper timed out; inspect phone before retrying') from None
            if boot.returncode:
                raise SystemExit(f'Verified temporary boot refused; see {status}')
            try:
                result = capture.wait(timeout=args.seconds + 10)
            except subprocess.TimeoutExpired:
                raise SystemExit(f'USB capture exceeded its bound; see {status}') from None
            if result:
                raise SystemExit(f'No usable USB capture; see {status}')
        finally:
            if capture.poll() is None:
                capture.terminate()
                try:
                    capture.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    capture.kill()
                    capture.wait()
    data = raw.read_bytes()
    if not capture_ok(data):
        raise SystemExit(f'ACPM rail cycle did not verify full restoration; inspect {raw} and {status}')
    print(f'ACPM rail-cycle capture saved privately: {raw}')


if __name__ == '__main__':
    main()
