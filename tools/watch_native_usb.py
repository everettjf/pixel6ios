#!/usr/bin/env python3
"""Bounded, read-only observation of the native USB ECM candidate and UDP logs.

Does not configure an interface, detach a driver, reboot a phone or write USB.
Only the reviewed 1209:0001 descriptors are recorded; datagrams stay private.
"""
import argparse
import datetime
import json
from pathlib import Path
import plistlib
import socket
import signal
import threading
import subprocess
import time


def devices():
    p = subprocess.run(['ioreg', '-a', '-p', 'IOUSB', '-l', '-w', '0'],
                       capture_output=True, timeout=5, check=True)
    found = []
    def walk(n):
        if isinstance(n, list):
            for c in n: walk(c)
        elif isinstance(n, dict):
            if n.get('idVendor') == 0x1209 and n.get('idProduct') == 1:
                keys = ('USB Product Name', 'USB Vendor Name', 'idVendor', 'idProduct',
                        'bDeviceClass', 'bDeviceSubClass', 'bDeviceProtocol')
                found.append({k:n[k] for k in keys if k in n})
            for c in n.get('IORegistryEntryChildren', []): walk(c)
    walk(plistlib.loads(p.stdout))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seconds', type=int, default=240)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    if not 1 <= a.seconds <= 300: ap.error('seconds must be1..300')
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    baseline = set(socket.if_nameindex())
    events = []
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('0.0.0.0', 5140)); udp.settimeout(0.25)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    deadline = time.monotonic() + a.seconds
    last = None; poll = 0; size = 0; pid_seen = False; tail = b''
    print('Read-only USB/UDP watcher ready', flush=True)
    with (a.out/'udp.log').open('xb') as log:
        while time.monotonic() < deadline and not stop.is_set():
            now = time.monotonic()
            if now >= poll:
                try:
                    dev = devices()
                    interfaces = sorted(set(socket.if_nameindex()) - baseline)
                    state = {'devices':dev, 'new_interfaces':interfaces}
                    if state != last:
                        events.append({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), **state})
                        (a.out/'events.json').write_text(json.dumps(events, indent=2)+'\n')
                        print('USB descriptor/interface state changed; candidate devices='+str(len(dev))+
                              ', new interfaces='+','.join(n for _,n in interfaces), flush=True)
                        last = state
                except (subprocess.SubprocessError, ValueError) as e:
                    print('USB observation error: '+type(e).__name__, flush=True)
                poll = now + 2
            try:
                data, source = udp.recvfrom(65535)
            except socket.timeout:
                continue
            if source[0] != '192.168.7.2': continue
            log.write(data); log.flush(); size += len(data)
            window = tail + data
            tail = window[-256:]
            if not pid_seen and b'ORIOLE USB RAM userspace: init running as PID 1' in window:
                pid_seen = True
                print('Observed repeated native RAM PID1 banner', flush=True)
    result = {'udp_bytes':size, 'pid1_banner':pid_seen, 'events':len(events),
              'network_configuration_changed':False}
    (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
