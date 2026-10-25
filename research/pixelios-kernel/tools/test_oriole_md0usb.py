"""Exact-payload and boot-argument binding for the separate md0 USB experiment."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import adt, oriole_md0usb as profile


class Md0UsbProfileTests(unittest.TestCase):
    def test_exact_critical_arguments(self):
        profile.validate_args(profile.ARGS)
        for key,value in [('rd','md0'),('sweetusb','2'),('sweetusbdma','0'),('cpus','1'),('sweetremote','0')]:
            for extra in (key+'='+value,key+'=other',key):
                with self.subTest(extra=extra):
                    with self.assertRaises(SystemExit):
                        profile.validate_args(profile.ARGS+' '+extra)
            with self.assertRaises(SystemExit):
                profile.validate_args(profile.ARGS.replace(key+'='+value,''))
        for old,new in [('rd=md0','rd=ufsroot0'),('sweetusbdma=0','sweetusbdma=1'),('sweetusb=2','sweetusb=1'),('cpus=1','cpus=8')]:
            with self.assertRaises(SystemExit):
                profile.validate_args(profile.ARGS.replace(old,new))

    def test_unknown_kernel_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);kernel=p/'kernel';kernel.write_bytes(b'wrong input')
            with self.assertRaises(SystemExit):
                profile.build(kernel,p/'out')
            self.assertFalse((p/'out').exists())

    @unittest.skipUnless((ROOT.parents[1]/'artifacts/md0usb/rebuild1/oriole-md0usb-payload.bin').exists(),'local Apple build artifacts absent')
    def test_current_payload_and_disabled_peripherals(self):
        path=ROOT.parents[1]/'artifacts/md0usb/rebuild1/oriole-md0usb-payload.bin'
        blob=path.read_bytes();profile.check(blob)
        bad=bytearray(blob);bad[-1]^=1
        with self.assertRaises(SystemExit):profile.check(bad)
        with self.assertRaises(SystemExit):profile.check(blob[:-1])
        off,size=struct.unpack_from('<QQ',blob,0x20)
        tree,end=adt.parse(blob[off:off+size]);self.assertEqual(end,size)
        nodes={n.name:n for n in tree.children}
        self.assertFalse(set(nodes)&{'sweet-ufs','sweet-touch','sweet-keys'})
        usb={k:v for k,_,v in nodes['sweet-usb'].props}
        self.assertEqual(usb['compatible'],b'google,gs101-dwusb3\0')
        self.assertEqual(usb['dma-pool-range'],struct.pack('<QQ',0xf8800000,0x1000000))
        self.assertEqual(usb['md0-log-board'],b'oriole\0')
        self.assertEqual(usb['init-after-network'],struct.pack('<I',1))


if __name__=='__main__':
    unittest.main()
