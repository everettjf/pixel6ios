"""Verify the host Internet trial remains scoped and fail-closed."""

import unittest

import prepare_oriole_usb_internet as trial


class PrepareInternetTests(unittest.TestCase):
    def setUp(self):
        self.state = {'distinct_candidate': True,
                      'host_ip_interfaces': ['en9'],
                      'default_uplink': 'en1',
                      'usb_1209_0001_count': 1,
                      'host_ip': '192.168.7.1',
                      'macos_bootpd_dhcp_enabled': False}

    def test_scoped_trial(self):
        plan = trial.prepare(self.state, 'en9', 'en1', '1.1.1.1')
        self.assertIn('interface=en9\n', plan['dnsmasq_conf'])
        self.assertIn('listen-address=192.168.7.1\n', plan['dnsmasq_conf'])
        self.assertIn('dhcp-option=option:router,192.168.7.1\n', plan['dnsmasq_conf'])
        self.assertEqual(plan['pf_nat_anchor'],
                         'nat on en1 inet from 192.168.7.0/24 to any -> (en1)\n')
        self.assertFalse(plan['applied'])
        self.assertFalse(plan['internet_verified'])

    def test_ambiguous_or_mismatched_interface_refused(self):
        for field, value in [('distinct_candidate', False),
                             ('host_ip_interfaces', ['en8', 'en9']),
                             ('usb_1209_0001_count', 2),
                             ('macos_bootpd_dhcp_enabled', True),
                             ('macos_bootpd_dhcp_enabled', None)]:
            with self.subTest(field=field, value=value):
                state = dict(self.state, **{field: value})
                with self.assertRaises(ValueError):
                    trial.prepare(state, 'en9', 'en1', '1.1.1.1')
        for usb, uplink, dns in [('en1', 'en1', '1.1.1.1'),
                                 ('en9', 'en0', '1.1.1.1'),
                                 ('en9;rm', 'en1', '1.1.1.1'),
                                 ('en9', 'en1', '192.168.7.2'),
                                 ('en9', 'en1', '127.0.0.1')]:
            with self.subTest(usb=usb, uplink=uplink, dns=dns):
                with self.assertRaises(ValueError):
                    trial.prepare(self.state, usb, uplink, dns)


if __name__ == '__main__':
    unittest.main()
