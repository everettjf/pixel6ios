"""The local Safari probe must refuse an ambiguous USB target."""

import unittest

import probe_oriole_usb_http as probe


class LocalHttpProbeTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            'distinct_candidate': True,
            'usb_1209_0001_count': 1,
            'host_ip': '192.168.7.1',
            'host_ip_interfaces': ['en9'],
            'default_uplink': 'en1',
        }

    def test_unique_usb_candidate(self):
        self.assertEqual(probe.verify_candidate(self.state), 'en9')

    def test_ambiguous_or_absent_candidate_is_refused(self):
        cases = [
            ('distinct_candidate', False),
            ('usb_1209_0001_count', 0),
            ('usb_1209_0001_count', 2),
            ('host_ip', '192.168.1.1'),
            ('host_ip_interfaces', []),
            ('host_ip_interfaces', ['en8', 'en9']),
            ('default_uplink', 'en9'),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    probe.verify_candidate(dict(self.state, **{field: value}))


if __name__ == '__main__':
    unittest.main()
