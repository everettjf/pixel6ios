"""Check the host snapshot's fail-closed interface selection."""

import plistlib
import subprocess
import unittest

import preflight_oriole_usb_host as host


class HostPreflightTests(unittest.TestCase):
    def test_exact_distinct_candidate(self):
        outputs = [
            b'   interface: en1\n',
            b'en1: flags=1\n\tinet 192.168.1.2 netmask 0xffffff00\nen9: flags=1\n\tinet 192.168.7.1 netmask 0xffffff00\n',
            plistlib.dumps([{'idVendor': 0x1209, 'idProduct': 1}]),
        ]
        calls = []

        def run(argv, **kwargs):
            calls.append(argv)
            self.assertEqual(kwargs['timeout'], 10)
            self.assertTrue(kwargs['check'])
            return subprocess.CompletedProcess(argv, 0, outputs[len(calls) - 1], b'')

        result = host.snapshot(run)
        self.assertTrue(result['distinct_candidate'])
        self.assertFalse(result['internet_verified'])
        self.assertFalse(result['network_configuration_changed'])
        self.assertEqual([c[0] for c in calls], ['route', 'ifconfig', 'ioreg'])

    def test_missing_or_ambiguous_identity_is_not_candidate(self):
        self.assertIsNone(host.default_interface('interface: en1\ninterface: en2\n'))
        self.assertEqual(host.interfaces_with_host_ip('en1: flags=1\n\tinet 192.168.7.10 netmask 0xffffff00\n'), [])
        self.assertEqual(host.usb_gadget_count(plistlib.dumps([{'idVendor': 0x1209, 'idProduct': 2}])), 0)


if __name__ == '__main__':
    unittest.main()
