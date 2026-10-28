#!/usr/bin/env python3
"""Read-only macOS host snapshot for the Oriole USB ECM Internet trial.

This does not configure an interface, forwarding, NAT, or DNS. A 1209:0001
descriptor and an IPv4 address do not by themselves prove that the interface
belongs to the phone or that iOS can reach the Internet.
"""

import json
from pathlib import Path
import plistlib
import re
import subprocess


HOST_IP = '192.168.7.1'
BOOTPD_PLIST = Path('/etc/bootpd.plist')


def default_interface(output):
    values = re.findall(r'^\s*interface:\s*(\S+)\s*$', output, re.MULTILINE)
    return values[0] if len(values) == 1 and re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', values[0]) else None


def interfaces_with_host_ip(output):
    matches = []
    current = None
    for line in output.splitlines():
        header = re.match(r'^([A-Za-z][A-Za-z0-9]*):\s', line)
        if header:
            current = header[1]
        elif current and re.match(r'^\s+inet\s+' + re.escape(HOST_IP) + r'\s', line):
            matches.append(current)
    return sorted(set(matches))


def usb_gadget_count(blob):
    tree = plistlib.loads(blob)
    count = 0

    def walk(node):
        nonlocal count
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if node.get('idVendor') == 0x1209 and node.get('idProduct') == 1:
                count += 1
            for child in node.get('IORegistryEntryChildren', []):
                walk(child)

    walk(tree)
    return count


def forwarding_enabled(output):
    value = output.strip()
    if value not in ('0', '1'):
        raise ValueError('unexpected IPv4 forwarding value')
    return value == '1'


def macos_bootpd_dhcp_enabled(path=BOOTPD_PLIST):
    try:
        value = plistlib.loads(path.read_bytes()).get('dhcp_enabled')
    except FileNotFoundError:
        return None
    return value if type(value) is bool else None


def snapshot(run=subprocess.run, bootpd_path=BOOTPD_PLIST):
    commands = [
        ['route', '-n', 'get', 'default'],
        ['ifconfig', '-a'],
        ['ioreg', '-a', '-p', 'IOUSB', '-l', '-w', '0'],
        ['sysctl', '-n', 'net.inet.ip.forwarding'],
    ]
    results = [run(command, capture_output=True, timeout=10, check=True) for command in commands]
    uplink = default_interface(results[0].stdout.decode())
    candidates = interfaces_with_host_ip(results[1].stdout.decode())
    gadgets = usb_gadget_count(results[2].stdout)
    forwarding = forwarding_enabled(results[3].stdout.decode())
    return {
        'default_uplink': uplink,
        'host_ip': HOST_IP,
        'host_ip_interfaces': candidates,
        'usb_1209_0001_count': gadgets,
        'ipv4_forwarding_enabled': forwarding,
        'macos_bootpd_dhcp_enabled': macos_bootpd_dhcp_enabled(bootpd_path),
        'distinct_candidate': gadgets == 1 and uplink is not None and
                              len(candidates) == 1 and candidates[0] != uplink,
        'network_configuration_changed': False,
        'internet_verified': False,
    }


if __name__ == '__main__':
    try:
        print(json.dumps(snapshot(), indent=2, sort_keys=True))
    except (OSError, subprocess.SubprocessError, ValueError, plistlib.InvalidFileException) as exc:
        raise SystemExit('HOST PREFLIGHT REFUSED: ' + type(exc).__name__) from None
