"""A pending OTA must not silently become an approved hardware baseline."""
import unittest
from boot_inventory import (check_firmware, check_touch_image_digest,
                            check_acpm_desc_image_digest, check_acpm_rails_image_digest,
                            check_acpm_rail_cycle_image_digest)


class BootBaselineTests(unittest.TestCase):
    def setUp(self):
        self.baseline={'slot':'a','bootloader':'slider-17.0-15199431',
                       'allowed_modes':['inventory','xnu-loadcheck']}
        self.values={'version-bootloader':'version-bootloader: slider-17.0-15199431\nFinished.',
                     'current-slot':'(bootloader) current-slot: a\nFinished.',
                     'partition-size:boot_a':'partition-size:boot_a: 0x4000000'}

    def test_same_baseline_accepted(self):
        check_firmware(self.values.__getitem__,self.baseline,'xnu-loadcheck')

    def test_touch_requires_a_separately_pinned_exact_image(self):
        digest = 'a' * 64
        opened = dict(self.baseline, allowed_modes=['inventory', 'inventory-touch'])
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_touch_image_digest(opened, digest)
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_touch_image_digest(dict(opened, inventory_touch_image_sha256='wrong'), digest)
        pinned = dict(opened, inventory_touch_image_sha256=digest)
        with self.assertRaisesRegex(SystemExit, 'differs'):
            check_touch_image_digest(pinned, 'b' * 64)
        check_touch_image_digest(pinned, digest)
        self.assertEqual(check_firmware(self.values.__getitem__, pinned, 'inventory-touch'), 'a')

    def test_acpm_descriptor_requires_a_separately_pinned_exact_image(self):
        digest = 'c' * 64
        opened = dict(self.baseline, allowed_modes=['inventory', 'inventory-acpm-desc'])
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_acpm_desc_image_digest(opened, digest)
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_acpm_desc_image_digest(dict(opened, inventory_acpm_desc_image_sha256='wrong'), digest)
        pinned = dict(opened, inventory_acpm_desc_image_sha256=digest)
        with self.assertRaisesRegex(SystemExit, 'differs'):
            check_acpm_desc_image_digest(pinned, 'd' * 64)
        check_acpm_desc_image_digest(pinned, digest)
        self.assertEqual(check_firmware(self.values.__getitem__, pinned, 'inventory-acpm-desc'), 'a')

    def test_acpm_rails_requires_a_separately_pinned_exact_image(self):
        digest = 'e' * 64
        opened = dict(self.baseline, allowed_modes=['inventory', 'inventory-acpm-rails'])
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_acpm_rails_image_digest(opened, digest)
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_acpm_rails_image_digest(dict(opened, inventory_acpm_rails_image_sha256='wrong'), digest)
        pinned = dict(opened, inventory_acpm_rails_image_sha256=digest)
        with self.assertRaisesRegex(SystemExit, 'differs'):
            check_acpm_rails_image_digest(pinned, 'd' * 64)
        check_acpm_rails_image_digest(pinned, digest)
        self.assertEqual(check_firmware(self.values.__getitem__, pinned, 'inventory-acpm-rails'), 'a')

    def test_acpm_rail_cycle_requires_a_separately_pinned_exact_image(self):
        digest = 'f' * 64
        opened = dict(self.baseline, allowed_modes=['inventory', 'inventory-acpm-rail-cycle'])
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_acpm_rail_cycle_image_digest(opened, digest)
        with self.assertRaisesRegex(SystemExit, 'not pinned'):
            check_acpm_rail_cycle_image_digest(dict(opened, inventory_acpm_rail_cycle_image_sha256='wrong'), digest)
        pinned = dict(opened, inventory_acpm_rail_cycle_image_sha256=digest)
        with self.assertRaisesRegex(SystemExit, 'differs'):
            check_acpm_rail_cycle_image_digest(pinned, 'e' * 64)
        check_acpm_rail_cycle_image_digest(pinned, digest)
        self.assertEqual(check_firmware(self.values.__getitem__, pinned, 'inventory-acpm-rail-cycle'), 'a')

    def test_storage_modes_remain_closed_until_explicitly_added(self):
        for mode in ('inventory-touch', 'inventory-acpm-desc', 'inventory-acpm-rails', 'inventory-acpm-rail-cycle', 'inventory-ufs-ready', 'xnu-ufsroot-loadcheck',
                     'xnu-ufsroot-preparecheck', 'xnu-ufsroot',
                     'xnu-ufsroot-coldinit', 'xnu-ufsroot-coldinit-preparecheck'):
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
