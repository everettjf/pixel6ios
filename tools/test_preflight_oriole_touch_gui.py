#!/usr/bin/env python3
"""Fail-closed tests for the read-only Oriole trial preflight."""

import importlib.util
from pathlib import Path
import subprocess
import unittest


PATH = Path(__file__).with_name('preflight_oriole_touch_gui.py')
SPEC = importlib.util.spec_from_file_location('preflight_oriole_touch_gui', PATH)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class PreflightDeviceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.values = {
            'product': 'oriole', 'unlocked': 'yes', 'current-slot': 'b',
            'version-bootloader': 'slider-test',
            'partition-size:boot_b': '0x4000000',
            'partition-size:userdata': '0x1000000000',
        }
        self.ids = 'TARGET\tfastboot usb:1-1\n'

    def run_fastboot(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertEqual(kwargs['timeout'], 10)
        if argv[1:] == ['devices', '-l']:
            return subprocess.CompletedProcess(argv, 0, self.ids, '')
        self.assertEqual(argv[1:3], ['-s', 'TARGET'])
        self.assertEqual(argv[3], 'getvar')
        field = argv[4]
        return subprocess.CompletedProcess(argv, 0, '', f'(bootloader) {field}: {self.values[field]}\n')

    def check(self):
        return PREFLIGHT.check_device(Path('/fake/fastboot'), 'TARGET',
                                      {'slot': 'b', 'bootloader': 'slider-test'},
                                      16 * 1024**3, run=self.run_fastboot)

    def test_exact_target_passes_using_only_read_commands(self):
        self.assertTrue(self.check())
        self.assertTrue(all(c[1:] == ['devices', '-l'] or c[3] == 'getvar'
                            for c in self.calls))

    def test_second_device_refused_before_getvar(self):
        self.ids += 'OTHER\tfastboot usb:2-1\n'
        with self.assertRaises(SystemExit):
            self.check()
        self.assertEqual(len(self.calls), 1)

    def test_wrong_product_refused(self):
        self.values['product'] = 'bluejay'
        with self.assertRaises(SystemExit):
            self.check()

    def test_locked_refused(self):
        self.values['unlocked'] = 'no'
        with self.assertRaises(SystemExit):
            self.check()

    def test_slot_drift_refused(self):
        self.values['current-slot'] = 'a'
        with self.assertRaises(SystemExit):
            self.check()

    def test_userdata_too_small_refused(self):
        self.values['partition-size:userdata'] = '0x100000000'
        with self.assertRaises(SystemExit):
            self.check()

    def test_duplicate_field_refused(self):
        self.values['product'] = 'oriole\n(bootloader) product: oriole'
        with self.assertRaises(SystemExit):
            self.check()

    def test_mismatched_0129_shim_is_refused_before_device_access(self):
        with self.assertRaisesRegex(SystemExit, 'runtime payload guard'):
            PREFLIGHT.select_trial('0129')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
