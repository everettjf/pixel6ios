"""Fail-closed checks for the separate read-only iOS platform boot profile."""
from pathlib import Path
import tempfile
import unittest

from tools import oriole_ufsroot as base
from tools import oriole_ufsroot_platform as profile


class OriolePlatformProfileTests(unittest.TestCase):
    def test_only_platform_permission_added_to_readonly_profile(self):
        self.assertEqual(profile.ARGS, base.ARGS + ' unentitled_ios_sim_launch=1')
        self.assertEqual(profile.ARGS.count('unentitled_ios_sim_launch=1'), 1)
        profile.validate_args(profile.ARGS)
        base.validate_args(base.ARGS)
        with self.assertRaises(SystemExit):
            base.validate_args(profile.ARGS)
        for args in (base.ARGS, profile.ARGS + ' rootrw=1',
                     profile.ARGS.replace('ufsrw=0', 'ufsrw=1'),
                     profile.ARGS.replace('rootrw=0', 'rootrw=1'),
                     profile.ARGS.replace('unentitled_ios_sim_launch=1', 'unentitled_ios_sim_launch=0')):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                profile.validate_args(args)

    def test_unpinned_kernel_refused_before_product_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            kernel = work/'wrong-kernel'
            kernel.write_bytes(b'wrong')
            with self.assertRaises(SystemExit):
                profile.build(kernel, work/'absent-product', work/'out')
            self.assertFalse((work/'out').exists())

    def test_payload_hash_is_distinct_from_existing_profile(self):
        self.assertNotEqual(profile.PAYLOAD_SHA, base.PAYLOAD_SHA)
        self.assertEqual(len(profile.PAYLOAD_SHA), 64)


if __name__ == '__main__':
    unittest.main()
