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


class GuiProcessCue:
    """Cue a GUI trial only while touch scan is active, across UDP boundaries."""

    def __init__(self):
        self.tail = b''
        self.springboard = False
        self.backboardd = False
        self.scanning = False
        self.window_ended = False
        self.announced = False

    def feed(self, data):
        window = self.tail + data
        self.tail = window[-32:]
        self.springboard |= b'exec SpringBoard' in window
        self.backboardd |= b'exec backboardd' in window
        self.scanning |= b'SWEET TOUCH: scanning,' in window
        self.window_ended |= b'scan window ended' in window or b'LDO26M restored' in window
        if self.scanning and self.springboard and self.backboardd and not self.window_ended and not self.announced:
            self.announced = True
            return True
        return False


class TouchPathObserver:
    """Count complete touch/HID log lines while the GUI scan window is live."""

    def __init__(self):
        self.tail = b''
        self.scanning = False
        self.springboard = False
        self.backboardd = False
        self.window_ended = False
        self.touch_events = 0
        self.hid_events = 0
        self.gui_touch_events = 0
        self.gui_hid_events = 0

    def feed(self, data):
        lines = (self.tail + data).split(b'\n')
        self.tail = lines.pop()
        first_gui_touch = False
        first_gui_hid = False
        for line in lines:
            self.scanning |= b'SWEET TOUCH: scanning,' in line
            self.springboard |= b'exec SpringBoard' in line
            self.backboardd |= b'exec backboardd' in line
            self.window_ended |= b'scan window ended' in line or b'LDO26M restored' in line
            active = self.scanning and self.springboard and self.backboardd and not self.window_ended
            if b'SWEET TOUCH: ev ' in line and any(b'-> kind ' + str(k).encode() + b' ' in line for k in (1, 2, 3)):
                self.touch_events += 1
                if active:
                    self.gui_touch_events += 1
                    first_gui_touch = self.gui_touch_events == 1
            if b'SWEET HID: touch ' in line and (b' down at ' in line or b' up at ' in line):
                self.hid_events += 1
                if active:
                    self.gui_hid_events += 1
                    first_gui_hid = self.gui_hid_events == 1
        return first_gui_touch, first_gui_hid


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
    ap.add_argument('--cue-gui', action='store_true',
                    help='announce when touch scans and both GUI processes have started; not proof of a usable lock screen')
    a = ap.parse_args()
    if not 1 <= a.seconds <= 2500: ap.error('seconds must be 1..2500')
    a.out.mkdir(parents=True, exist_ok=False, mode=0o700)
    baseline = set(socket.if_nameindex())
    events = []
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('0.0.0.0', 5140)); udp.settimeout(0.25)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    deadline = time.monotonic() + a.seconds
    last = None; poll = 0; size = 0; pid_seen = False; tail = b''; gui = GuiProcessCue()
    touch_path = TouchPathObserver()
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
            if a.cue_gui and gui.feed(data):
                print('Touch scan and GUI processes started; watch for the lock screen and test touch as soon as it appears',
                      flush=True)
            first_touch, first_hid = touch_path.feed(data)
            if first_touch:
                print('Observed first touch-controller coordinate event during active GUI scan', flush=True)
            if first_hid:
                print('Observed first HID touch dispatch during active GUI scan', flush=True)
            if not pid_seen and b'ORIOLE USB RAM userspace: init running as PID 1' in window:
                pid_seen = True
                print('Observed repeated native RAM PID1 banner', flush=True)
    result = {'udp_bytes':size, 'pid1_banner':pid_seen, 'gui_process_pair':gui.announced,
              'touch_events':touch_path.touch_events, 'hid_events':touch_path.hid_events,
              'gui_touch_events':touch_path.gui_touch_events,
              'gui_hid_events':touch_path.gui_hid_events,
              'events':len(events),
              'network_configuration_changed':False}
    (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
