#!/usr/bin/env python3
"""Capture one verified Oriole ACPM descriptor inventory without touching storage."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time

from run_touch_inventory import (CAPTURE_PYTHON, PORT_CHECK, ROOT,
                                 require_single_recorded_fastboot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=180,
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
    folder = ROOT / 'private/acpm-desc-inventory' / stamp
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
                                       '--acpm-desc'], check=False, timeout=120)
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
    if b'ACPM DESC rc' not in data or b'ACPM INIT WORD' not in data or b'INVENTORY report complete' not in data:
        raise SystemExit(f'ACPM descriptor capture is incomplete; inspect {raw} and {status}')
    print(f'ACPM descriptor capture saved privately: {raw}')


if __name__ == '__main__':
    main()
