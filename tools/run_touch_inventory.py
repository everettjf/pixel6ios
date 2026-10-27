#!/usr/bin/env python3
"""Capture one exact Pixel 6 touch inventory, chip ID, or one-event FIFO boot."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
CAPTURE_PYTHON = ROOT / 'private/gate-venv/bin/python'
PORT_CHECK = ('from serial.tools import list_ports; '
              'print(sum((p.vid, p.pid) == (0x1209, 1) for p in list_ports.comports()))')


def require_single_recorded_fastboot():
    serial = (ROOT / 'private/target-serial').read_text().strip()
    if not serial or any(c.isspace() for c in serial):
        raise SystemExit('Invalid recorded target')
    result = subprocess.run([str(FASTBOOT), 'devices'], capture_output=True, text=True,
                            timeout=10, check=True)
    devices = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if devices != [[serial, 'fastboot']]:
        raise SystemExit('Expected exactly the recorded Pixel 6 in Fastboot Mode')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=180,
                        help='bounded USB capture duration, 30..300 seconds')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--touch-id', action='store_true',
                        help='run the separately pinned hardware-writing chip-ID profile')
    group.add_argument('--touch-fifo', action='store_true',
                       help='run the separately pinned one-event FIFO profile')
    args = parser.parse_args()
    if not 30 <= args.seconds <= 300:
        parser.error('--seconds must be 30..300')
    require_single_recorded_fastboot()
    ports = subprocess.run([str(CAPTURE_PYTHON), '-c', PORT_CHECK], check=True,
                           capture_output=True, text=True, timeout=10)
    if ports.stdout.strip() != '0':
        raise SystemExit('Another inventory USB gadget is already connected')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / ('private/touch-fifo-inventory' if args.touch_fifo else
                     'private/touch-id-inventory' if args.touch_id else 'private/touch-inventory') / stamp
    folder.mkdir(parents=True, mode=0o700)
    raw = folder / 'usb.log'
    status = folder / 'capture.txt'
    report = folder / 'report.json'
    with status.open('x') as output:
        status.chmod(0o600)
        capture = subprocess.Popen([str(CAPTURE_PYTHON),
                                    str(ROOT / 'tools/capture_inventory_usb.py'),
                                    '--seconds', str(args.seconds), '--out', str(raw)],
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            # The capture process creates the log before polling USB. Arm it first.
            deadline = time.monotonic() + 5
            while not raw.exists() and capture.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if not raw.exists() or capture.poll() is not None:
                raise SystemExit(f'USB capture did not arm; see {status}')
            try:
                boot = subprocess.run([sys.executable, str(ROOT / 'tools/boot_inventory.py'),
                                       '--touch-fifo' if args.touch_fifo else
                                       '--touch-id' if args.touch_id else '--touch'],
                                      check=False, timeout=120)
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
    subprocess.run([sys.executable, str(ROOT / ('tools/report_touch_fifo.py' if args.touch_fifo else
                                              'tools/report_touch_id.py' if args.touch_id else
                                              'tools/report_touch_inventory.py')),
                    str(raw), '--out', str(report)], check=True)
    print(f'Touch {"FIFO" if args.touch_fifo else "ID" if args.touch_id else "read-only"} inventory report: {report}')


if __name__ == '__main__':
    main()
