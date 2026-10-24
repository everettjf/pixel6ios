#!/usr/bin/env python3
"""Fail-closed audit of the two-pair EL3 writer. Compiler changes need review."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
# Exact reviewed GCC16.2 AArch64 instructions; all branches are intra-function,
# so the bytes are identical in shim.o and the linked ELF. This pins both the
# full-width PA/value guards and x0=82000504,x1=PA,x2=1,x3=value at the sole SMC.
WORDS='''2a0103e3 aa0003e2 7103f07f d2810200 f2a2e8c0 fa400040 540000e0
d2874000 f2a2e8c0 eb00005f 7a420860 92800000 540000c1 d280a080
aa0203e1 f2b04000 d2800022 d4000003 d65f03c0'''.split()
PROTOCOL_SHA='5ee167c91f91f9cb6fe70e56b5c1e4e149ebf59240b3d1a91e16e92a06a66742'
PROTOCOL_WORDS_SHA='acdff603d0f3ac830023fd3551001a95d3afe5f50e3d0c9563911e5c5a054b47'
CALLS='''20:CALL26:con_str 28:CALL26:resetcheck_ready 34:CALL26:resetcheck_wait_ms
38:CALL26:resetcheck_ticks 48:CALL26:resetcheck_ready 60:CALL26:resetcheck_read
74:CALL26:con_hex 84:CALL26:resetcheck_write 98:CALL26:resetcheck_read
ac:CALL26:con_hex bc:CALL26:con_hex cc:CALL26:con_hex f8:CALL26:con_str
100:CALL26:resetcheck_wait_ms 120:CALL26:con_str 140:CALL26:con_str
148:CALL26:resetcheck_wait_ms 14c:CALL26:resetcheck_ready 160:CALL26:resetcheck_write
170:CALL26:con_hex 178:CALL26:resetcheck_wait_ms 1a0:JUMP26:con_str'''.split()


def source_check(shim,header,protocol):
    code=re.sub(r'/\*.*?\*/','',shim,flags=re.S)
    m=re.search(r'uint64_t resetcheck_write\(uintptr_t pa, uint32_t v\)\s*\{(.*?)\n\}',code,re.S)
    expected='''if (!((pa==RC_SYSIP && v==0xfc) || (pa==RC_SWRESET && v==2))) return ~0ULL;
    return smc(0x82000504UL,pa,1,v);'''
    compact=lambda s:re.sub(r'\s+','',s)
    if not m or compact(m[1])!=compact(expected):
        raise ValueError('resetcheck source writer/allowlist changed')
    # Includes readiness, guarded read, serviced wait, deadline and placement
    # after USB start / before finish-reset. A changed profile requires review.
    for pattern,digest in [
        (r'#ifdef ORIOLE_RESETCHECK\n#include "resetcheck.h".*?\n#endif',
         'db4d2e1aa0623733a1f7923e179f378fa35ccb9dfd961d6b231999b30ddab486'),
        (r'#ifdef ORIOLE_RAMPROBE\n    inventory_dtb = dtb;.*?\n#endif\n#ifdef INVENTORY',
         '8a5ae8d4c490feed3114d2f07d9cce4f7fed87547c32f79800d36949c33b9015')]:
        block=re.search(pattern,code,re.S)
        if not block or hashlib.sha256(compact(block[0]).encode()).hexdigest()!=digest:
            raise ValueError('resetcheck hooks/profile placement changed')
    for macro,value in [('RC_SYSIP','0x17460810UL'),('RC_SWRESET','0x17463a00UL')]:
        if not re.search(r'^#define\s+'+macro+r'\s+'+value+r'\s*$',header,re.M):
            raise ValueError('resetcheck PMU constant changed')
    if hashlib.sha256(protocol).hexdigest()!=PROTOCOL_SHA:
        raise ValueError('resetcheck protocol differs from reviewed source')


def writer_check(disasm):
    words=re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',disasm,re.M)
    if words!=WORDS:
        raise ValueError('resetcheck compiled guard/SMC sequence changed; independent review required')


def protocol_check(disasm):
    words=re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',disasm,re.M)
    if hashlib.sha256(' '.join(words).encode()).hexdigest()!=PROTOCOL_WORDS_SHA:
        raise ValueError('resetcheck protocol compiled instructions changed')
    calls=[':'.join(t) for t in re.findall(
        r'^\s*([0-9a-f]+):\s+R_AARCH64_(CALL26|JUMP26)\s+(\w+)',disasm,re.M)]
    if calls!=CALLS:
        raise ValueError('resetcheck protocol call targets/count/order changed')
    for line in disasm.splitlines():
        m=re.match(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(\w+)\s+(.*)',line)
        if m and m[1].startswith(('str','stp','stur','stl','stx')) and '[sp' not in m[2]:
            raise ValueError('resetcheck protocol store outside stack')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',choices=('0','1'),required=True)
    p.add_argument('--object',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--objdump',required=True)
    a=p.parse_args()
    source_check((ROOT/'shim/shim.c').read_text(),(ROOT/'shim/resetcheck.h').read_text(),
                 (ROOT/'shim/resetcheck.c').read_bytes())
    for file in (a.object,a.elf):
        if a.enabled=='1':
            s=subprocess.check_output([a.objdump,'-d','--disassemble=resetcheck_write',str(file)],text=True)
            writer_check(s)
        else:
            symbols=subprocess.check_output([a.objdump,'-t',str(file)],text=True)
            if re.search(r'\b(?:resetcheck_\w+|oriole_resetcheck)\b',symbols):
                raise ValueError('resetcheck symbol present in a non-reset profile')
    if a.enabled=='1':
        disasm=subprocess.check_output([a.objdump,'-dr','--disassemble=oriole_resetcheck',
                                        str(a.object.parent/'resetcheck.o')],text=True)
        protocol_check(disasm)
        table=subprocess.check_output([a.objdump,'-t',str(a.object.parent/'resetcheck.o')],text=True)
        undef={line.split()[-1] for line in table.splitlines() if '*UND*' in line}
        if undef!={'con_hex','con_str','resetcheck_read','resetcheck_ready','resetcheck_ticks',
                   'resetcheck_wait_ms','resetcheck_write'}:
            raise ValueError('resetcheck protocol acquired a new external surface')
    print('PASS resetcheck source, compiled writer and profile omission audit')


if __name__=='__main__':
    main()
