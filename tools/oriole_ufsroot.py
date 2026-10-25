#!/usr/bin/env python3
"""One exact Oriole read-only storage-root diagnostic payload (no media writes).

Not full iOS: existing Android userdata is expected to reject filesystem mount.
No phone access here; the shim/host modes must independently opt in after review.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import adt, mkadt, mkpayload

KERNEL_SHA = 'b151ad90ff30e975448f08b055be98234c11a3f798b93701c217019a80d9ddc1'
PRODUCT_SHA = '9e670987c80493bd69aba7be62e3179c04663324d9249b0973675baac175dbf1'
PAYLOAD_SHA = '11062cf7a1133bf89ea87ba81dee1961325026c3d86a8be8c6feca459b7a46e2'
PAYLOAD_SIZE = 16713568
ARGS = ('debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam '
        '-noprogress wdt=-1 wdt_test=no_user_checkin '
        'sweetusb=2 sweetusbdma=0 sweetremote=0 sweetrestart=90 '
        'rd=ufsroot0 ufsroot=userdata ufsrw=0 rootrw=0 sweetlog=0 ufscache=0 ufswait=0')
REQUIRED = {'cpus':'1','sweetusb':'2','sweetusbdma':'0','sweetremote':'0',
            'sweetrestart':'90','rd':'ufsroot0','ufsroot':'userdata','ufsrw':'0',
            'rootrw':'0','sweetlog':'0','ufscache':'0','ufswait':'0'}


def require_hash(blob,expected):
    if not expected or hashlib.sha256(blob).hexdigest()!=expected:
        raise SystemExit('Oriole storage-root: unreviewed input/artifact')


def validate_args(args):
    seen={}
    for token in args.split():
        key,sep,value=token.partition('=')
        if key in seen:
            raise SystemExit('Oriole storage-root: duplicate argument')
        seen[key]=value if sep else None
    if any(seen.get(k)!=v for k,v in REQUIRED.items()):
        raise SystemExit('Oriole storage-root: unsafe or missing required argument')
    if args!=ARGS:
        raise SystemExit('Oriole storage-root: unexpected command line')


def props(node):
    values={k:v for k,_,v in node.props}
    if len(values)!=len(node.props):
        raise SystemExit('Oriole storage-root: duplicate ADT property')
    return values


def check_tree(root):
    names=[n.name for n in root.children]
    if len(names)!=len(set(names)) or any(n in names for n in ('sweet-touch','sweet-keys')):
        raise SystemExit('Oriole storage-root: unexpected hardware node')
    if not {'sweet-ufs','sweet-usb','sweet-reset','product'}<=set(names):
        raise SystemExit('Oriole storage-root: missing required node')
    children={n.name:props(n) for n in root.children}
    ufs,usb=children['sweet-ufs'],children['sweet-usb']
    if (ufs.get('compatible')!=b'google,gs101-ufs\0' or
        ufs.get('reg')!=struct.pack('<QQ',0x14700000,0x200) or
        ufs.get('oriole-root-board')!=b'oriole\0'):
        raise SystemExit('Oriole storage-root: UFS opt-in mismatch')
    if (usb.get('compatible')!=b'google,gs101-dwusb3\0' or
        usb.get('reg')!=struct.pack('<QQ',0x11110000,0x10000) or
        usb.get('dma-pool-range')!=struct.pack('<QQ',0xf8800000,0x1000000)):
        raise SystemExit('Oriole storage-root: USB differs from CP3A measurements')
    if children['product'].get('product-description')!=b'Pixel 6\0' or props(root).get('model-number')!=b'oriole\0':
        raise SystemExit('Oriole storage-root: product identity mismatch')
    def walk(node):
        yield node
        for child in node.children:
            yield from walk(child)
    for node in walk(root):
        values=props(node)
        if 'RAMDisk' in values:
            raise SystemExit('Oriole storage-root: unexpected RAM disk')


def build(kernel,product,out):
    require_hash(kernel.read_bytes(),KERNEL_SHA)
    require_hash(product.read_bytes(),PRODUCT_SHA)
    # Preserve the fixed RAM builders: no implicit input or global monkeypatch.
    if (ROOT/'research/ipsw-x/d22ap.adt').exists():
        raise SystemExit('Oriole storage-root: implicit product lookup must remain absent')
    product_props=mkadt.d22ap_product(str(product))
    if not product_props or len(product_props)!=61 or len(dict(product_props))!=61:
        raise SystemExit('Oriole storage-root: incomplete D22AP product input')
    product_props=[(k,v) for k,v in product_props if k!='product-description']+[
        ('product-description',b'Pixel 6\0')]
    root=mkadt.build(seed=bytes(range(64)),board='oriole')
    root.children=[n for n in root.children if n.name not in ('sweet-touch','sweet-keys','product')]
    root.children.append(mkadt.node('product',product_props))
    root.props=[(k,f,b'oriole\0' if k=='model-number' else v) for k,f,v in root.props]
    ufs=next(n for n in root.children if n.name=='sweet-ufs')
    ufs.props.append(('oriole-root-board',0,b'oriole\0'))
    check_tree(root);validate_args(ARGS)
    out.mkdir(parents=True,exist_ok=True)
    tree=out/'oriole-ufsroot.adt';tree.write_bytes(adt.serialize(root))
    return mkpayload.build(kernel,tree,ARGS,board='oriole')


def check(blob):
    if len(blob)!=PAYLOAD_SIZE:
        raise SystemExit('Oriole storage-root: payload size mismatch')
    require_hash(blob,PAYLOAD_SHA)
    validate_args(blob[0x48:0x48+608].split(b'\0')[0].decode('ascii'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--kernel',type=Path);g.add_argument('--check',type=Path)
    g.add_argument('--check-image',type=Path)
    p.add_argument('--product',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.check:check(a.check.read_bytes())
    elif a.check_image:
        b=a.check_image.read_bytes()
        if b[:8]!=b'ANDROID!' or struct.unpack_from('<I',b,40)[0]!=4:
            raise SystemExit('Expected Android v4 image')
        ks,rs=struct.unpack_from('<II',b,8);off=4096+((ks+4095)&~4095)
        check(b[off:off+rs])
    else:
        if not a.out or not a.product:p.error('--kernel requires --out and explicit --product')
        blob,_=build(a.kernel,a.product,a.out);check(blob)
        (a.out/'oriole-ufsroot-payload.bin').write_bytes(blob)
    print('Oriole read-only storage-root: exact payload verified')


if __name__=='__main__':main()
