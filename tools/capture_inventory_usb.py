#!/usr/bin/env python3
"""Bounded CDC-ACM capture for the existing PixeliOS 1209:0001 gadget on macOS."""
import argparse
import pathlib
import time

import serial
from serial.tools import list_ports


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seconds', type=int, default=90)
    ap.add_argument('--out', type=pathlib.Path, required=True)
    args = ap.parse_args()
    if not 1 <= args.seconds <= 300:
        ap.error('--seconds must be 1..300')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.seconds
    print('Waiting for inventory USB gadget 1209:0001', flush=True)
    received = 0
    with args.out.open('xb') as log:
        while time.monotonic() < deadline:
            ports = [p for p in list_ports.comports() if (p.vid, p.pid) == (0x1209, 1)]
            if len(ports) > 1:
                raise SystemExit('More than one inventory gadget; no port selected')
            if not ports:
                time.sleep(0.2)
                continue
            try:
                # macOS/pyserial clears its input queue during open(). Keep
                # DTR low until that flush is complete, or the gadget can
                # send its initial replay into the queue being discarded.
                port = serial.Serial(None, 115200, timeout=0.2, write_timeout=1)
                port.dtr = False
                port.port = ports[0].device
                with port:
                    port.dtr = True
                    print('Inventory gadget opened', flush=True)
                    while time.monotonic() < deadline:
                        data = port.read(4096)
                        if data:
                            log.write(data)
                            log.flush()
                            received += len(data)
            except (serial.SerialException, OSError):
                if received:
                    break
                time.sleep(0.2)
    args.out.chmod(0o600)
    print(f'Captured {received} bytes: {args.out}', flush=True)
    if not received:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
