"""A pending OTA must not silently become an approved hardware baseline."""
import unittest
from boot_inventory import check_firmware


class BootBaselineTests(unittest.TestCase):
    def setUp(self):
        self.baseline={'slot':'a','bootloader':'slider-17.0-15199431',
                       'allowed_modes':['inventory','xnu-loadcheck']}
        self.values={'version-bootloader':'version-bootloader: slider-17.0-15199431\nFinished.',
                     'current-slot':'(bootloader) current-slot: a\nFinished.',
                     'partition-size:boot_a':'partition-size:boot_a: 0x4000000'}

    def test_same_baseline_accepted(self):
        check_firmware(self.values.__getitem__,self.baseline,'xnu-loadcheck')

    def test_storage_modes_remain_closed_until_explicitly_added(self):
        for mode in ('xnu-ufsroot-loadcheck','xnu-ufsroot'):
            with self.assertRaisesRegex(SystemExit,'not validated'):
                check_firmware(self.values.__getitem__,self.baseline,mode)
            opened=dict(self.baseline,allowed_modes=self.baseline['allowed_modes']+[mode])
            self.assertEqual(check_firmware(self.values.__getitem__,opened,mode),'a')

    def test_ota_bootloader_and_slot_drift_refused_independently(self):
        for key,new in [('version-bootloader','slider-17.0-15681480'),('current-slot','b')]:
            values=dict(self.values);values[key]=key+': '+new
            with self.assertRaisesRegex(SystemExit,'Firmware baseline changed'):
                check_firmware(values.__getitem__,self.baseline,'xnu-loadcheck')

    def test_unknown_response_or_unvalidated_profile_refused(self):
        with self.assertRaises(SystemExit):
            check_firmware(lambda _: 'unavailable',self.baseline,'inventory')
        with self.assertRaisesRegex(SystemExit,'not validated'):
            check_firmware(self.values.__getitem__,self.baseline,'xnu-resetcheck')

    def test_duplicate_response_rejected(self):
        for field in self.values:
            values = dict(self.values)
            values[field] += '\n' + values[field]
            with self.assertRaisesRegex(SystemExit, 'exactly one'):
                check_firmware(values.__getitem__, self.baseline, 'inventory')

    def test_trailing_tokens_rejected(self):
        for field in self.values:
            values = dict(self.values)
            values[field] = values[field].splitlines()[0] + ' unexpected'
            with self.assertRaisesRegex(SystemExit, 'Malformed'):
                check_firmware(values.__getitem__, self.baseline, 'inventory')

    def test_malformed_baseline_rejected(self):
        malformed = [None, [], {'slot': 'c'}, *(
            dict(self.baseline, allowed_modes=m) for m in
            ('inventory', {'inventory'}, ['inventory', 'inventory'], [1], ['unknown']))]
        for baseline in malformed:
            with self.assertRaises(SystemExit):
                check_firmware(self.values.__getitem__, baseline, 'inventory')

    def test_active_b_geometry_used(self):
        baseline = dict(self.baseline, slot='b')
        values = dict(self.values)
        del values['partition-size:boot_a']
        values['current-slot'] = 'current-slot: b'
        values['partition-size:boot_b'] = 'partition-size:boot_b: 0x4000000'
        self.assertEqual(check_firmware(values.__getitem__, baseline, 'inventory'), 'b')
        values['partition-size:boot_b'] = 'partition-size:boot_b: 0x2000000'
        with self.assertRaisesRegex(SystemExit, 'geometry'):
            check_firmware(values.__getitem__, baseline, 'inventory')


if __name__=='__main__':
    unittest.main()
