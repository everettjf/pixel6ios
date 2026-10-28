#!/usr/bin/env python3
"""Prepare, but never apply, a scoped macOS USB Internet trial.

The live snapshot is intentionally only a candidate check. A human must match
the USB interface against the phone's connect/disconnect transition before
installing either generated configuration.
"""

import argparse
import ipaddress
import json
from pathlib import Path
import plistlib
import re
import subprocess

from preflight_oriole_usb_host import snapshot


INTERFACE = re.compile(r'[A-Za-z][A-Za-z0-9]*\Z')
SUBNET = '192.168.7.0/24'
HOST_IP = '192.168.7.1'


def prepare(state, usb_interface, uplink, dns_upstream):
    if not state.get('distinct_candidate'):
        raise ValueError('no distinct live USB network candidate')
    if not INTERFACE.fullmatch(usb_interface) or not INTERFACE.fullmatch(uplink):
        raise ValueError('invalid interface name')
    if state.get('host_ip_interfaces') != [usb_interface]:
        raise ValueError('USB interface does not match the live host-IP candidate')
    if state.get('default_uplink') != uplink or usb_interface == uplink:
        raise ValueError('uplink does not match the live default route')
    if state.get('usb_1209_0001_count') != 1 or state.get('host_ip') != HOST_IP:
        raise ValueError('USB gadget or host address changed')
    if state.get('macos_bootpd_dhcp_enabled') is not False:
        raise ValueError('Apple bootpd DHCP state is not confirmed disabled')
    upstream = ipaddress.IPv4Address(dns_upstream)
    if (upstream.is_unspecified or upstream.is_multicast or upstream.is_loopback
            or upstream.is_link_local or upstream.is_reserved):
        raise ValueError('DNS upstream must be a unicast external IPv4 address')
    if upstream in ipaddress.IPv4Network(SUBNET):
        raise ValueError('DNS upstream cannot be on the USB subnet')

    dnsmasq = '\n'.join([
        '# Pixel 6 USB trial; generated only after a live candidate snapshot.',
        'no-resolv',
        'no-hosts',
        'bind-interfaces',
        f'interface={usb_interface}',
        f'listen-address={HOST_IP}',
        f'server={upstream}',
        'dhcp-range=192.168.7.20,192.168.7.30,255.255.255.0,1h',
        f'dhcp-option=option:router,{HOST_IP}',
        f'dhcp-option=option:dns-server,{HOST_IP}',
        'log-dhcp',
        '',
    ])
    pf_anchor = (f'nat on {uplink} inet from {SUBNET} to any -> ({uplink})\n')
    return {'dnsmasq_conf': dnsmasq, 'pf_nat_anchor': pf_anchor,
            'usb_interface': usb_interface, 'uplink': uplink,
            'dns_upstream': str(upstream), 'applied': False,
            'ipv4_forwarding_enabled': state.get('ipv4_forwarding_enabled'),
            'internet_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--usb-interface', required=True)
    parser.add_argument('--uplink', required=True)
    parser.add_argument('--dns-upstream', required=True)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = prepare(snapshot(), args.usb_interface, args.uplink, args.dns_upstream)
    except (OSError, ValueError, subprocess.SubprocessError,
            plistlib.InvalidFileException) as exc:
        parser.exit(1, f'HOST INTERNET PREP REFUSED: {exc}\n')
    try:
        args.output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    except FileExistsError:
        parser.exit(1, 'HOST INTERNET PREP REFUSED: output directory already exists\n')
    (args.output_dir / 'dnsmasq.conf').write_text(plan.pop('dnsmasq_conf'))
    (args.output_dir / 'pf-nat.anchor').write_text(plan.pop('pf_nat_anchor'))
    (args.output_dir / 'plan.json').write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    print(f'Prepared uninstalled trial files in {args.output_dir}')


if __name__ == '__main__':
    main()
