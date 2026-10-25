"""Fail-closed checks for the separately gated RAM-COW Oriole root."""
from pathlib import Path
import tempfile
import unittest

from tools import mkadt, oriole_ufsroot as base, oriole_ufsroot_cow as profile


class OrioleCowProfileTests(unittest.TestCase):
    def test_boot_args_keep_physical_ufs_read_only(self):
        profile.validate_args(profile.ARGS)
        self.assertIn('ufsrw=0', profile.ARGS)
        self.assertIn('rootrw=1', profile.ARGS)
        self.assertIn('ufscow=1', profile.ARGS)
        for args in (
            base.ARGS,
            profile.ARGS + ' rootrw=1',
            profile.ARGS.replace('ufsrw=0', 'ufsrw=1'),
            profile.ARGS.replace('rootrw=1', 'rootrw=0'),
            profile.ARGS.replace('ufscow=1', 'ufscow=0'),
            profile.ARGS.replace('sweetlog=0', 'sweetlog=1'),
            profile.ARGS.replace('unentitled_ios_sim_launch=1',
                                 'unentitled_ios_sim_launch=0'),
        ):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                profile.validate_args(args)

    def test_exact_adt_marker_required(self):
        root = mkadt.build(seed=bytes(range(64)), board='oriole')
        root.children = [n for n in root.children
                         if n.name not in ('sweet-touch', 'sweet-keys', 'product')]
        root.children.append(mkadt.node('product', [('product-description', b'Pixel 6\0')]))
        root.props = [(k, f, b'oriole\0' if k == 'model-number' else v)
                      for k, f, v in root.props]
        ufs = next(n for n in root.children if n.name == 'sweet-ufs')
        ufs.props.append(('oriole-root-board', 0, b'oriole\0'))
        with self.assertRaises(SystemExit):
            profile.check_tree(root)
        ufs.props.append(('oriole-cow-board', 0, b'oriole-cow\0'))
        profile.check_tree(root)
        ufs.props.append(('oriole-cow-board', 0, b'oriole-cow\0'))
        with self.assertRaises(SystemExit):
            profile.check_tree(root)

    def test_unpinned_kernel_refused_before_product_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            kernel = work/'wrong-kernel'
            kernel.write_bytes(b'wrong')
            with self.assertRaises(SystemExit):
                profile.build(kernel, work/'absent-product', work/'out')
            self.assertFalse((work/'out').exists())


if __name__ == '__main__':
    unittest.main()
