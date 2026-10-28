#!/usr/bin/env python3
"""Bounded, read-only observation of the native USB ECM candidate and UDP logs.

Does not configure an interface, detach a driver, reboot a phone or write USB.
Only the reviewed 1209:0001 descriptors are recorded; datagrams stay private.
"""
import argparse
from collections import deque
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
        self.touch_service_open = None
        self.buttons_service_open = None
        self.scan_started_at = None
        self.gui_ready_at = None
        self.first_gui_touch_at = None
        self.first_gui_hid_at = None
        self.scan_ended_at = None
        # Host receive timestamps, not device event timestamps. Keep the most
        # recent observations so a late gesture is not lost to startup noise.
        self.event_observations = deque(maxlen=512)

    def feed(self, data, received_at=None, received_utc=None):
        if received_at is None:
            received_at = time.monotonic()
        if received_utc is None:
            received_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lines = (self.tail + data).split(b'\n')
        self.tail = lines.pop()
        first_gui_touch = False
        first_gui_hid = False
        for line in lines:
            if b'SWEET HID: SweetHIDTouch open by IOHIDEventServiceUserClient -> ' in line:
                self.touch_service_open = line.rstrip().endswith(b'-> 1')
            if b'SWEET HID: SweetHIDButtons open by IOHIDEventServiceUserClient -> ' in line:
                self.buttons_service_open = line.rstrip().endswith(b'-> 1')
            if b'SWEET TOUCH: scanning,' in line and self.scan_started_at is None:
                self.scan_started_at = received_at
            self.scanning |= b'SWEET TOUCH: scanning,' in line
            self.springboard |= b'exec SpringBoard' in line
            self.backboardd |= b'exec backboardd' in line
            if (self.scanning and self.springboard and self.backboardd and
                    not self.window_ended and self.gui_ready_at is None):
                self.gui_ready_at = received_at
            if (b'scan window ended' in line or b'LDO26M restored' in line) and self.scan_ended_at is None:
                self.scan_ended_at = received_at
            self.window_ended |= b'scan window ended' in line or b'LDO26M restored' in line
            active = self.scanning and self.springboard and self.backboardd and not self.window_ended
            if b'SWEET TOUCH: ev ' in line and any(b'-> kind ' + str(k).encode() + b' ' in line for k in (1, 2, 3)):
                self.touch_events += 1
                self.event_observations.append({
                    'received_utc': received_utc,
                    'since_gui_seconds': None if self.gui_ready_at is None else round(received_at - self.gui_ready_at, 3),
                    'path': 'controller', 'line': line.decode('utf-8', 'replace')[:200],
                })
                if active:
                    self.gui_touch_events += 1
                    first_gui_touch = self.gui_touch_events == 1
                    if first_gui_touch:
                        self.first_gui_touch_at = received_at
            if b'SWEET HID: touch ' in line and (b' down at ' in line or b' up at ' in line):
                self.hid_events += 1
                self.event_observations.append({
                    'received_utc': received_utc,
                    'since_gui_seconds': None if self.gui_ready_at is None else round(received_at - self.gui_ready_at, 3),
                    'path': 'hid', 'line': line.decode('utf-8', 'replace')[:200],
                })
                if active:
                    self.gui_hid_events += 1
                    first_gui_hid = self.gui_hid_events == 1
                    if first_gui_hid:
                        self.first_gui_hid_at = received_at
        return first_gui_touch, first_gui_hid

    def timing(self):
        """Host-observed seconds; absent markers remain null, not zero."""
        def elapsed(start, end):
            return None if start is None or end is None else round(end - start, 3)
        return {
            'scan_to_gui_seconds': elapsed(self.scan_started_at, self.gui_ready_at),
            'gui_to_first_touch_seconds': elapsed(self.gui_ready_at, self.first_gui_touch_at),
            'gui_to_first_hid_seconds': elapsed(self.gui_ready_at, self.first_gui_hid_at),
            'gui_to_scan_end_seconds': elapsed(self.gui_ready_at, self.scan_ended_at),
        }


class NetworkPathObserver:
    """Record distinct USB-network milestones; none proves Internet access."""

    def __init__(self):
        self.tail = b''
        self.route_added = False
        self.route_add_failed = False
        self.interface_published = False
        self.interface_publish_failed = False
        self.registration_program_started = False
        self.route_removed = False
        # Patch 0078 logs before the ioctl/route operation. These are
        # requests, not proof that either operation succeeded.
        self.route_delete_requested_by_configd = False
        self.address_delete_requested_by_configd = False

    def feed(self, data):
        lines = (self.tail + data).split(b'\n')
        self.tail = lines.pop()
        new = []
        for line in lines:
            if b'SWEET NET: ue0 default route add 0 owned=1' in line:
                key = 'route_added'
            elif b'SWEET NET: ue0 default route add ' in line:
                key = 'route_add_failed'
            elif b'SWEET NETIF: published IONetworkInterface ue0' in line:
                key = 'interface_published'
            elif b'SWEET NETIF: ' in line and any(
                    marker in line for marker in (b'unavailable', b'attach failed')):
                key = 'interface_publish_failed'
            elif b'exec addNetworkInterface' in line:
                key = 'registration_program_started'
            elif b'SWEET NET: ue0 owned default route remove 0' in line:
                key = 'route_removed'
            elif (b'SWEET NET: configd route delete 0.0.0.0 gw 192.168.7.1 ' in line):
                key = 'route_delete_requested_by_configd'
            elif b'SWEET NET: configd ue0 delete address ' in line:
                key = 'address_delete_requested_by_configd'
            else:
                continue
            if not getattr(self, key):
                setattr(self, key, True)
                new.append(key)
        return new

    def result(self):
        return {key: getattr(self, key) for key in (
            'route_added', 'route_add_failed', 'interface_published',
            'interface_publish_failed', 'registration_program_started',
            'route_removed', 'route_delete_requested_by_configd',
            'address_delete_requested_by_configd')}


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
    network_path = NetworkPathObserver()
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
            for milestone in network_path.feed(data):
                print('Observed USB-network log milestone: ' + milestone, flush=True)
            if not pid_seen and b'ORIOLE USB RAM userspace: init running as PID 1' in window:
                pid_seen = True
                print('Observed repeated native RAM PID1 banner', flush=True)
    result = {'udp_bytes':size, 'pid1_banner':pid_seen, 'gui_process_pair':gui.announced,
              'hid_touch_service_open':touch_path.touch_service_open,
              'hid_buttons_service_open':touch_path.buttons_service_open,
              'touch_events':touch_path.touch_events, 'hid_events':touch_path.hid_events,
              'gui_touch_events':touch_path.gui_touch_events,
              'gui_hid_events':touch_path.gui_hid_events,
              'touch_timing':touch_path.timing(),
              'event_observations':list(touch_path.event_observations),
              'network_log_milestones':network_path.result(),
              'events':len(events),
              'network_configuration_changed':False}
    (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
