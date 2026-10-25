"""Offline Oriole storage-root opt-in and argument refusal tests."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ufsroot_profile',ROOT/'tools/oriole_ufsroot.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)


class UfsRootProfileTests(unittest.TestCase):
    def tree(self):
        root=profile.mkadt.build(seed=bytes(range(64)),board='oriole')
        root.children=[n for n in root.children if n.name not in ('product','sweet-touch','sweet-keys')]
        root.children.append(profile.mkadt.node('product',[('product-description',b'Pixel 6\0')]))
        root.props=[(k,f,b'oriole\0' if k=='model-number' else v) for k,f,v in root.props]
        ufs=next(n for n in root.children if n.name=='sweet-ufs')
        ufs.props.append(('oriole-root-board',0,b'oriole\0'))
        return root

    def test_exact_unique_readonly_arguments(self):
        profile.validate_args(profile.ARGS)
        for key,value in profile.REQUIRED.items():
            for bad in (profile.ARGS+' '+key+'='+value,
                        profile.ARGS.replace(key+'='+value,key+'=wrong'),
                        profile.ARGS.replace(key+'='+value,'')):
                with self.subTest(key=key,args=bad),self.assertRaises(SystemExit):
                    profile.validate_args(bad)
        with self.assertRaises(SystemExit):profile.validate_args(profile.ARGS+' extra=1')

    def test_exact_tree_and_marker_refusals(self):
        profile.check_tree(self.tree())
        for kind in ('missing-marker','bad-marker','duplicate-marker','bad-ufs-reg',
                     'bad-usb-range','missing-reset','touch','ramdisk','model'):
            root=self.tree();ufs=next(n for n in root.children if n.name=='sweet-ufs')
            usb=next(n for n in root.children if n.name=='sweet-usb')
            if kind=='missing-marker':ufs.props=[p for p in ufs.props if p[0]!='oriole-root-board']
            if kind=='bad-marker':ufs.props=[(k,f,b'bluejay\0' if k=='oriole-root-board' else v) for k,f,v in ufs.props]
            if kind=='duplicate-marker':ufs.props.append(('oriole-root-board',0,b'oriole\0'))
            if kind=='bad-ufs-reg':ufs.props=[(k,f,struct.pack('<QQ',0x14700000,0x4000) if k=='reg' else v) for k,f,v in ufs.props]
            if kind=='bad-usb-range':usb.props=[(k,f,struct.pack('<QQ',0xf8800000,0x2000000) if k=='dma-pool-range' else v) for k,f,v in usb.props]
            if kind=='missing-reset':root.children=[n for n in root.children if n.name!='sweet-reset']
            if kind=='touch':root.children.append(profile.mkadt.node('sweet-touch'))
            if kind=='ramdisk':
                chosen=next(n for n in root.children if n.name=='chosen')
                mmap=next(n for n in chosen.children if n.name=='memory-map')
                mmap.props.append(('RAMDisk',0,struct.pack('<QQ',0x880000000,0x1000)))
            if kind=='model':root.props=[(k,f,b'bluejay\0' if k=='model-number' else v) for k,f,v in root.props]
            with self.subTest(kind=kind),self.assertRaises(SystemExit):profile.check_tree(root)

    def test_unpinned_kernel_refused_before_other_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);kernel=work/'wrong-kernel';kernel.write_bytes(b'wrong')
            with self.assertRaises(SystemExit):profile.build(kernel,work/'absent-product',work/'out')
            self.assertFalse((work/'out').exists())


if __name__=='__main__':unittest.main()
