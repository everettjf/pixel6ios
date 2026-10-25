#!/usr/bin/env python3
"""Prepare/check one exact Oriole md0+USB logging payload; not a generic XNU gate.

This file alone does not enable a shim/host boot profile. Kernel, init, ADT and
arguments all require exact hashes. Inputs and binaries remain local.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import adt, mkadt, mkpayload

KERNEL_SHA = '4724585fffd9e85144cb86b6c8e91a5131253a25cf341879c17368000007867b'
SOURCE_SHA = 'c775da4d4d8cde124db64352a11207f3671f23d91aefd4bba7ca5fb7b9950454'
INIT_SHA = 'baa6d09e9ef0a3ac68094399266b241c62277d4d134116d1c78600daf5c8b559'
PAYLOAD_SHA = '5139a045c73e0a605a431216bfa131cd38442ce1e98b9617a16e611044a6761b'
PAYLOAD_SIZE = 16727088
ARGS = ('debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam '
        '-noprogress wdt=-1 wdt_test=no_user_checkin '
        'sweetusb=2 sweetusbdma=0 sweetremote=0 rd=md0')


def require_hash(data, expected):
    if not expected or hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Oriole md0 USB: unreviewed input/artifact')


def validate_args(args):
    required = {'rd':'md0','sweetusb':'2','sweetusbdma':'0','cpus':'1','sweetremote':'0'}
    seen = {}
    for token in args.split():
        key,sep,value = token.partition('=')
        if key in required:
            if not sep or key in seen:
                raise SystemExit('Oriole md0 USB: missing/duplicate critical boot argument')
            seen[key] = value
    if seen != required:
        raise SystemExit('Oriole md0 USB: unexpected critical boot argument')


def check(blob):
    if len(blob) != PAYLOAD_SIZE:
        raise SystemExit('Oriole md0 USB: payload size mismatch')
    require_hash(blob,PAYLOAD_SHA)
    args = blob[0x48:0x48+608].split(b'\0')[0].decode('ascii')
    validate_args(args)


def build(kernel, out):
    require_hash(kernel.read_bytes(),KERNEL_SHA)
    source = ROOT/'tools/oriole-usb-init.S'
    require_hash(source.read_bytes(),SOURCE_SHA)
    helper = ROOT/'.upstream/tools/mkinit.py'
    require_hash(helper.read_bytes(),'79b8585105d4ecfc6f47542563577d0c55c22e7eaa517cffb367cf24e7c4e8ac')
    validate_args(ARGS)
    out.mkdir(parents=True,exist_ok=True)
    obj,init,tree = [out/n for n in ('init.o','init.macho','oriole.adt')]
    subprocess.run(['xcrun','clang','-target','arm64-apple-ios16.0','-c',str(source),'-o',str(obj)],check=True)
    spec=importlib.util.spec_from_file_location('mkinit',helper)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    ib=mod.build(obj.read_bytes())
    require_hash(ib,INIT_SHA)
    init.write_bytes(ib)
    root=mkadt.build(seed=bytes(range(64)),board='oriole',no_ufs=True)
    root.children=[n for n in root.children if n.name not in ('sweet-keys','sweet-touch')]
    usb=next(n for n in root.children if n.name=='sweet-usb')
    props={k:v for k,_,v in usb.props}
    if (props.get('compatible') != b'google,gs101-dwusb3\0' or
            props.get('reg') != struct.pack('<QQ',0x11110000,0x10000) or
            props.get('dma-pool-range') != struct.pack('<QQ',0xf8800000,0x1000000)):
        raise SystemExit('Oriole md0 USB: ADT differs from CP3A measurements')
    usb.props += [('md0-log-board',0,b'oriole\0'),('init-after-network',0,struct.pack('<I',1))]
    if any(n.name in ('sweet-ufs','sweet-touch','sweet-keys') for n in root.children):
        raise SystemExit('Oriole md0 USB: unexpected hardware node')
    tree.write_bytes(adt.serialize(root))
    blob,info=mkpayload.build(kernel,tree,ARGS,init,board='oriole')
    return blob,ib,info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--kernel',type=Path)
    g.add_argument('--check',type=Path)
    g.add_argument('--check-image',type=Path)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.check:
        check(a.check.read_bytes())
    elif a.check_image:
        b=a.check_image.read_bytes()
        if b[:8]!=b'ANDROID!' or struct.unpack_from('<I',b,40)[0]!=4:
            raise SystemExit('Expected Android v4 image')
        ks,rs=struct.unpack_from('<II',b,8);off=4096+((ks+4095)&~4095)
        check(b[off:off+rs])
    else:
        if not a.out:p.error('--kernel requires --out')
        blob,_,_=build(a.kernel,a.out)
        check(blob)
        (a.out/'oriole-md0usb-payload.bin').write_bytes(blob)
    print('Oriole md0 USB payload: exact hash verified')


if __name__=='__main__':
    main()
