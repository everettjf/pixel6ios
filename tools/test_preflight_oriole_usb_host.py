"""Check the host snapshot's fail-closed interface selection."""

import plistlib
from pathlib import Path
import subprocess
import tempfile
import unittest

import preflight_oriole_usb_host as host


class HostPreflightTests(unittest.TestCase):
    def test_exact_distinct_candidate(self):
        outputs = [
            b'   interface: en1\n',
            b'en1: flags=1\n\tinet 192.168.1.2 netmask 0xffffff00\nen9: flags=1\n\tinet 192.168.7.1 netmask 0xffffff00\n',
            plistlib.dumps([{'idVendor': 0x1209, 'idProduct': 1}]),
            b'1\n',
        ]
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            self.assertEqual(kwargs['timeout'], 10)
            self.assertTrue(kwargs['check'])
            return subprocess.CompletedProcess(argv, 0, outputs[len(calls) - 1], b'')

        with tempfile.TemporaryDirectory() as directory:
            bootpd_path = Path(directory) / 'bootpd.plist'
            bootpd_path.write_bytes(plistlib.dumps({'dhcp_enabled': True}))
            result = host.snapshot(run, bootpd_path=bootpd_path)
        self.assertTrue(result['distinct_candidate'])
        self.assertTrue(result['ipv4_forwarding_enabled'])
        self.assertTrue(result['macos_bootpd_dhcp_enabled'])
        self.assertFalse(result['internet_verified'])
        self.assertFalse(result['network_configuration_changed'])
        self.assertEqual([c[0] for c in calls], ['route', 'ifconfig', 'ioreg', 'sysctl'])

    def test_missing_or_ambiguous_identity_is_not_candidate(self):
        self.assertIsNone(host.default_interface('interface: en1\ninterface: en2\n'))
        self.assertEqual(host.interfaces_with_host_ip('en1: flags=1\n\tinet 192.168.7.10 netmask 0xffffff00\n'), [])
        self.assertEqual(host.usb_gadget_count(plistlib.dumps([{'idVendor': 0x1209, 'idProduct': 2}])), 0)
        with self.assertRaises(ValueError):
            host.forwarding_enabled('enabled')
        with tempfile.TemporaryDirectory() as directory:
            bootpd_path = Path(directory) / 'bootpd.plist'
            self.assertIsNone(host.macos_bootpd_dhcp_enabled(bootpd_path))
            bootpd_path.write_bytes(plistlib.dumps({'dhcp_enabled': 'true'}))
            self.assertIsNone(host.macos_bootpd_dhcp_enabled(bootpd_path))


if __name__ == '__main__':
    unittest.main()
