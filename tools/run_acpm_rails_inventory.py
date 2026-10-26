#!/usr/bin/env python3
"""Capture one verified Oriole touch-rail IPC-read experiment without storage I/O."""
import argparse
from datetime import datetime, timezone
import re
import subprocess
import sys
import time

from run_touch_inventory import (CAPTURE_PYTHON, PORT_CHECK, ROOT,
                                 require_single_recorded_fastboot)


def capture_ok(data):
    """Only two successful, replied-to reads constitute a completed measurement."""
    if b'ACPM RAIL DESC rc00000000 why00000000' not in data or b'INVENTORY report complete' not in data:
        return False
    reads = re.findall(rb'ACPM RAIL READ reg([0-9A-F]{8}) rc([0-9A-F]{8})', data)
    ipc = re.findall(rb'ACPM RAIL IPC published([0-9A-F]{8}) reply([0-9A-F]{8})', data)
    return reads == [(b'0000005C', b'00000000'), (b'0000005D', b'00000000')] and ipc == [
        (b'00000002', b'00000001'), (b'00000002', b'00000001')]


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
    folder = ROOT / 'private/acpm-rails-inventory' / stamp
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
                                       '--acpm-rails'], check=False, timeout=120)
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
        raise SystemExit(f'ACPM rail-read capture lacks two successful replies; inspect {raw} and {status}')
    print(f'ACPM rail-read capture saved privately: {raw}')


if __name__ == '__main__':
    main()
