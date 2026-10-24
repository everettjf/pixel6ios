#!/usr/bin/env python3
"""Offline XNU relink from the pinned CI archive; never prepares or boots a phone image.

Preserves PIE with locally built ld64-956.6. Rebuilt support objects/toolchain differ
from CI and require independent review; success here is not hardware approval.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'artifacts/xnu-reference'
LINK = REF / 'kernel.development.sweet.link'
OUT = ROOT / 'artifacts/native-kernel'


def section(blob, segment, name):
    off = 32
    for _ in range(struct.unpack_from('<I', blob, 16)[0]):
        cmd, size = struct.unpack_from('<II', blob, off)
        if cmd == 0x19 and blob[off+8:off+24].split(b'\0')[0].decode() == segment:
            for i in range(struct.unpack_from('<I', blob, off+64)[0]):
                at = off+72+i*80
                if blob[at:at+16].split(b'\0')[0].decode() == name:
                    count = struct.unpack_from('<Q', blob, at+40)[0]
                    start = struct.unpack_from('<I', blob, at+48)[0]
                    if start+count > len(blob):
                        raise SystemExit('Truncated reference section')
                    return blob[start:start+count]
        off += size
    raise SystemExit('Missing reference section '+segment+','+name)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root):
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        h.update(str(path.relative_to(root)).encode()+b'\0')
        h.update(path.read_bytes())
    return h.hexdigest()


def verify_inputs():
    policy = json.loads((ROOT/'docs/native-link-inputs.json').read_text())
    for relative, expected in policy['files'].items():
        if digest(ROOT/relative) != expected:
            raise SystemExit('Unreviewed relink input: '+relative)
    for relative, expected in policy.get('header_trees',{}).items():
        if tree_digest(ROOT/relative) != expected:
            raise SystemExit('Unexpected installed header tree: '+relative)
    for name, tool in policy['tools'].items():
        if digest(Path(tool['path'])) != tool['sha256']:
            raise SystemExit('Unreviewed relink tool: '+name)
    for relative, expected in policy['git_commits'].items():
        actual = subprocess.check_output(['git','-C',str(ROOT/relative),'rev-parse','HEAD'],text=True).strip()
        if actual != expected:
            raise SystemExit('Unreviewed source revision: '+relative)
        if subprocess.check_output(['git','-C',str(ROOT/relative),'status','--porcelain','--untracked-files=no'],text=True).strip():
            raise SystemExit('Modified tracked source: '+relative)
    return policy


class SymbolTable(dict):
    def __init__(self):
        super().__init__()
        self.record_counts = Counter()


def macho_info(blob):
    magic,cpu,subtype,filetype,count,command_size,flags,reserved = struct.unpack_from('<8I',blob)
    if (magic,cpu,subtype,filetype) != (0xfeedfacf,0x100000c,0,2) or reserved != 0 or 32+command_size > len(blob):
        raise SystemExit('Expected plain-arm64 executable Mach-O')
    off, segments, commands, symbols = 32, {}, [], SymbolTable()
    seen_segments = set()
    entry = None
    for _ in range(count):
        cmd, size = struct.unpack_from('<II',blob,off)
        if size < 8 or off+size > len(blob):
            raise SystemExit('Invalid Mach-O command range')
        commands.append((cmd,''))
        if cmd == 0x19:
            name = blob[off+8:off+24].split(b'\0')[0].decode()
            if name in seen_segments:
                raise SystemExit('Duplicate segment name')
            seen_segments.add(name)
            commands[-1] = (cmd,name)
            va, vs, fo, fs, mp, ip = struct.unpack_from('<4Q2I',blob,off+24)
            if fs > len(blob)-fo:
                raise SystemExit('Segment exceeds file')
            if vs:
                if name in segments or fs > vs:
                    raise SystemExit('Duplicate/oversized loaded segment')
                segments[name] = [va,vs,fo,fs,mp,ip]
        elif cmd == 0x5:
            entry = struct.unpack_from('<Q',blob,off+16+32*8)[0]
        elif cmd == 0x2:
            symoff,nsyms,stroff,strsize = struct.unpack_from('<4I',blob,off+8)
            if stroff+strsize > len(blob) or symoff+nsyms*16 > len(blob):
                raise SystemExit('Invalid symbol-table bounds')
            strings = blob[stroff:stroff+strsize]
            for n in range(nsyms):
                si, typ, sect, desc, value = struct.unpack_from('<IBBHQ',blob,symoff+n*16)
                if not si or typ & 0xe0:
                    continue
                if si >= strsize:
                    raise SystemExit('Invalid symbol-name index')
                if (typ & 0x0e) == 0:
                    raise SystemExit('Undefined symbol in static kernel')
                end = strings.find(b'\0',si)
                if end < 0:
                    raise SystemExit('Unterminated Mach-O symbol')
                name = strings[si:end].decode()
                symbols.record_counts[(name,typ)] += 1
                symbols[name] = (value, bool(typ & 1 and not typ & 0x10))
        off += size
    if off != 32+command_size:
        raise SystemExit('Load-command area size mismatch')
    return segments, symbols, entry, commands


def verify_output(reference, blob, md0):
    if struct.unpack_from('<I',blob,24)[0] != 0x200001:
        raise SystemExit('Expected NOUNDEFS|PIE')
    rs,rn,re,rc = macho_info(reference)
    ss,sn,se,sc = macho_info(blob)
    if set(rs) != set(ss):
        raise SystemExit('Loaded segment set changed')
    for name, expected in rs.items():
        got = ss[name]
        # LINKEDIT is rounded to whole pages by the source strip/link pipeline.
        # Every other loaded segment's address, length and protections must match.
        if name == '__LINKEDIT':
            if (got[0],(got[1]+0x3fff)&~0x3fff,got[4:]) != (expected[0],(expected[1]+0x3fff)&~0x3fff,expected[4:]):
                raise SystemExit('LINKEDIT range/protection changed')
            li = ss['__LINKINFO']
            if (got[2] != li[2]+li[3] or got[2]+got[3] != len(blob) or
                    not 0 <= got[1]-got[3] < 0x4000):
                raise SystemExit('LINKEDIT file range changed')
        elif got != expected:
            raise SystemExit('Runtime segment changed: '+name)
    if sc != [c for c in rc if c != (0x19,'__CTF')]:
        raise SystemExit('Unexpected load-command/entry/symbol-table contract')
    if se != re or se != sn.get('__start',(None,False))[0]:
        raise SystemExit('Entry differs from linked __start')
    if {n for n,(_,g) in rn.items() if g} != {n for n,(_,g) in sn.items() if g}:
        raise SystemExit('Development global-symbol scope changed')
    allowed = {'_ContinuouslySyncProfile','_PageSize','_TheBufferIO','_VPDataArray'}
    if md0:
        allowed |= {'_sweet_md0_usb_ready','_sweet_md0_usb_ready.called'}
    if set(rn)-set(sn) or set(sn)-set(rn) != allowed:
        raise SystemExit('Unreviewed local/runtime symbol delta')
    expected_extra = Counter({(name,0x0e):1 for name in allowed})
    if (rn.record_counts-sn.record_counts != Counter({('__MergedGlobals',0x0e):2}) or
            sn.record_counts-rn.record_counts != expected_extra):
        raise SystemExit('Unreviewed symbol-record multiplicity/scope')
    if section(reference,'__LINKINFO','__symbolsets') != section(blob,'__LINKINFO','__symbolsets'):
        raise SystemExit('LINKINFO contents changed')
    def read_at(data,segs,address,size):
        for va,vs,fo,fs,mp,ip in segs.values():
            if va <= address and address+size <= va+fs:
                return data[fo+address-va:fo+address-va+size]
        raise SystemExit('Symbol is not file-backed')
    for data,segs,names in [(reference,rs,rn),(blob,ss,sn)]:
        if read_at(data,segs,names['___llvm_profile_raw_version'][0],8) != struct.pack('<Q',8):
            raise SystemExit('Incompatible compiler profile ABI')
    if read_at(reference,rs,rn['___chkstk_darwin'][0],48) != read_at(blob,ss,sn['___chkstk_darwin'][0],48):
        raise SystemExit('Stack-check builtin changed')
    return {'loaded_segments':len(ss),'global_symbols':sum(g for _,g in sn.values()),
            'entry':hex(se),'profile_raw_version':8,'extra_local_symbols':sorted(set(sn)-set(rn))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--md0', action='store_true', help='substitute reviewed-source callback object (offline only)')
    args = ap.parse_args()
    policy = verify_inputs()
    ar_tool = policy['tools']['ar']['path']
    reference = (REF/'kernel.development.sweet').read_bytes()
    if hashlib.sha256(reference).hexdigest() != '8e4d38ea655930ef1da4998ab236962caabb9c8af1efaed6a96e243039af2292':
        raise SystemExit('Unexpected reference kernel')
    original_archive = LINK/'kernel.development.sweet.a'
    archive = original_archive
    if args.md0:
        work = OUT/'md0';work.mkdir(exist_ok=True)
        obj = work/'sweet_restart.o'
        shutil.copyfile(OUT/'restart-md0.o', obj)
        archive = work/'kernel.development.sweet.a'
        shutil.copyfile(original_archive, archive)
        members = subprocess.check_output([ar_tool,'-t',str(archive)],text=True).splitlines()
        if members.count('sweet_restart.o') != 1:
            raise SystemExit('Archive must have exactly one restart member')
        subprocess.run([ar_tool,'-r',str(archive),str(obj)],check=True)
        if subprocess.check_output([ar_tool,'-p',str(archive),'sweet_restart.o']) != obj.read_bytes():
            raise SystemExit('Archive replacement differs from pinned object')
    sets = OUT/'reference-symbolsets.plist'
    sets.write_bytes(section(reference,'__LINKINFO','__symbolsets'))
    flags = shlex.split((LINK/'kernel.development.sweet.linkarguments').read_text())
    # .linkarguments includes EXTRA_KC_LINKARGS for kcgen, not the source kernel.
    # MakeInc.kernel:193-215 and MakeInc.def:847-852 supply the source-only flags.
    flags = [f for f in flags if not f.startswith('-L/Users/runner') and f not in
             ('-lfirehose_kernel','-lcc_kext','-Wl,-new_linker','-Wl,-rename_segment,__LASTDATA_CONST,__LAST')]
    output = OUT/('kernel.md0-usb' if args.md0 else 'kernel.pie-baseline')
    cmd = [policy['tools']['clang']['path'],'-fuse-ld='+policy['tools']['ld64']['path']]+flags
    cmd += ['-Wl,-force_load,'+str(archive),str(OUT/'firehose_buffer.o'),
            str(OUT/'profile16/nonlto.o'),str(OUT/'profile16/chkstk_darwin.S.o'),
            str(OUT/'profile16/libkernel-profile16.a'),
            '-Wl,-alias_list,'+str(LINK/'kernel.development.sweet.alias.exp'),
            '-Wl,-sectcreate,__LINKINFO,__symbolsets,'+str(sets),
            '-Wl,-segprot,__LINKINFO,r--,r--','-o',str(output)]
    link_env = dict(os.environ)
    for name in ('SDKROOT','DEVELOPER_DIR','MACOSX_DEPLOYMENT_TARGET'):
        link_env.pop(name,None)
    subprocess.run(cmd,check=True,env=link_env)
    subprocess.run([policy['tools']['strip']['path'],'-S',str(output)],check=True,env=link_env)
    # Do not transplant CTF: generated per build; zero-vmsize CTF is omitted from
    # the original payload by mkpayload.build (line155), too.
    blob = output.read_bytes()
    if struct.unpack_from('<I',blob,24)[0] != 0x200001:
        raise SystemExit('Expected NOUNDEFS|PIE, rejecting output')
    audit = verify_output(reference,blob,args.md0)
    manifest = {'audit':audit,'input_policy_sha256':digest(ROOT/'docs/native-link-inputs.json'),'offline_only':True,'command':cmd,'sha256':hashlib.sha256(blob).hexdigest(),
                'reference_sha256':hashlib.sha256(reference).hexdigest(),
                'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                'firehose_sha256':hashlib.sha256((OUT/'firehose_buffer.o').read_bytes()).hexdigest(),
                'ctf':'Not transplanted; original zero-vmsize CTF is not loaded by payload generator.',
                'size':len(blob)}
    Path(str(output)+'.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Offline PIE relink:',output,'SHA256='+manifest['sha256'])


if __name__ == '__main__':
    main()
