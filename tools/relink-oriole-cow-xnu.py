#!/usr/bin/env python3
"""Offline Oriole RAM-COW kernel relink; never prepares or boots a phone image.

Verifies the exact 0105 patch, reconstructed source, compiler recipe and
replacement object before linking. Success here is not hardware approval.
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
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'artifacts/xnu-reference'
LINK = REF / 'kernel.development.sweet.link'
SUPPORT = ROOT / 'artifacts/native-kernel'
OUT = ROOT / 'private/oriole-cow-work/relink'

PATCH = ROOT / 'research/pixelios-kernel/xnu/patches/0105-oriole-ram-cow-root.patch'
BEFORE = ROOT / 'private/oriole-cow-work/sweet_ufs.before.c'
SOURCE = ROOT / 'artifacts/fullroot-kernel/source/bsd/dev/sweet_ufs.c'
COMMAND = ROOT / 'artifacts/fullroot-kernel/sweet_ufs.oriole-ro-command.json'
OBJECT = ROOT / 'private/oriole-cow-work/sweet_ufs.cow.o'
COW_PINS = {
    PATCH: 'd9f06d73b1cc5dcfd9555d26ff658ca6250043055b5589b90f895587b274cced',
    BEFORE: '2fac79b55cf093b0d2fd7a7dcd4ddb924ce8f075975d0a02a0d6ffe634574d0d',
    SOURCE: 'a9599d919963ac916d0abebc9cea0a5874ab09561fd72442d65f6e86ca4f931b',
    COMMAND: '695ffc39aa9a8e40c2e86b2ead926db91ef1832fc9189e9ada10150c0610712c',
    OBJECT: '0ffe4b6657fea96766bbd954b19a769ffb7642cb68e2b8f48656ebe1d060323a',
}


def verify_cow_object():
    for path, expected in COW_PINS.items():
        if digest(path) != expected:
            raise SystemExit('Unreviewed COW input: ' + str(path))
    with tempfile.TemporaryDirectory() as name:
        directory = Path(name)
        reconstructed = directory / 'bsd/dev/sweet_ufs.c'
        reconstructed.parent.mkdir(parents=True)
        reconstructed.write_bytes(BEFORE.read_bytes())
        subprocess.run(['git', 'apply', str(PATCH)], cwd=directory, check=True)
        if reconstructed.read_bytes() != SOURCE.read_bytes():
            raise SystemExit('COW source does not match reviewed 0105 patch')
        cmd = json.loads(COMMAND.read_text())
        if not isinstance(cmd, list) or cmd.count('-o') != 1 or cmd.count('-MF') != 1:
            raise SystemExit('Unreviewed COW compiler recipe')
        if Path(cmd[-3]).resolve() != SOURCE:
            raise SystemExit('COW compiler source mismatch')
        cmd[cmd.index('-o') + 1] = str(directory / 'sweet_ufs.o')
        cmd[cmd.index('-MF') + 1] = str(directory / 'sweet_ufs.d')
        subprocess.run(cmd, cwd=SOURCE.parents[2], check=True, capture_output=True)
        if (directory / 'sweet_ufs.o').read_bytes() != OBJECT.read_bytes():
            raise SystemExit('COW replacement object is not reproducible')


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
    policy = json.loads((ROOT/'docs/oriole-storage-link-inputs.json').read_text())
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
        actual = subprocess.check_output([policy['tools']['git']['path'],'-C',str(ROOT/relative),'rev-parse','HEAD'],text=True).strip()
        if actual != expected:
            raise SystemExit('Unreviewed source revision: '+relative)
        if subprocess.check_output([policy['tools']['git']['path'],'-C',str(ROOT/relative),'status','--porcelain','--untracked-files=no'],text=True).strip():
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


def uuid_offset(blob):
    """Return the value of the sole, well-formed LC_UUID command."""
    if len(blob) < 32:
        raise SystemExit('Truncated Mach-O header')
    count, command_size = struct.unpack_from('<II', blob, 16)
    if 32 + command_size > len(blob):
        raise SystemExit('Invalid Mach-O command area')
    off = 32
    found = []
    for _ in range(count):
        if off + 8 > 32 + command_size:
            raise SystemExit('Invalid Mach-O command range')
        cmd, size = struct.unpack_from('<II', blob, off)
        if size < 8 or off + size > 32 + command_size:
            raise SystemExit('Invalid Mach-O command range')
        if cmd == 0x1b:
            if size != 24:
                raise SystemExit('Invalid LC_UUID size')
            found.append(off + 8)
        off += size
    if off != 32 + command_size or len(found) != 1:
        raise SystemExit('Expected exactly one LC_UUID')
    return found[0]


def pin_reference_uuid(reference, candidate):
    value = reference[uuid_offset(reference):uuid_offset(reference)+16]
    at = uuid_offset(candidate)
    pinned = bytearray(candidate)
    pinned[at:at+16] = value
    return bytes(pinned)


def verify_output(reference, blob, md0):
    if struct.unpack_from('<I',blob,24)[0] != 0x200001:
        raise SystemExit('Expected NOUNDEFS|PIE')
    rs,rn,re,rc = macho_info(reference)
    ss,sn,se,sc = macho_info(blob)
    if blob[uuid_offset(blob):uuid_offset(blob)+16] != reference[uuid_offset(reference):uuid_offset(reference)+16]:
        raise SystemExit('LC_UUID differs from reference')
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
    # Exact local-name/record deltas from reviewed replacement objects;
    # startup entry names include the source line in Apple's LCK macros.
    allowed = {'_ContinuouslySyncProfile','_PageSize','_TheBufferIO','_VPDataArray',
               '_sweet_md0_usb_ready','_sweet_md0_usb_ready.called',
               '_oriole_ufs_userdata','_sweet_log_start','_sweet_ufs_init.oriole_attempted',
               '_ufs_find_oriole_userdata.capacity','_ufs_find_partition',
               '_ufs_oriole_stop','_ufs_oriole_stop.cold.1','_ufs_oriole_stop.cold.2',
               '_ufs_oriole_stop.cold.3','_ufs_read_blocks','_ufs_take_over_host',
               '_oriole_cow_buckets','_oriole_cow_pages',
               '_oriole_cow_store.__startup_ZALLOC_entry___zone_site_register_179',
               '_oriole_cow_store.kalloc_type_view_177',
               '_oriole_cow_store.kalloc_type_view_180',
               '_oriole_cow_store.kalloc_type_view_203',
               '_oriole_cow_store.site',
               '_sweet_ufs_init.__startup_ZALLOC_entry___zone_site_register_857',
               '_sweet_ufs_init.kalloc_type_view_857',
               '_sweet_ufs_init.site'}
    if not md0:
        raise SystemExit('Only the exact Oriole read-only storage profile is supported')
    if set(rn)-set(sn) or set(sn)-set(rn) != allowed:
        raise SystemExit('Unreviewed local/runtime symbol delta')
    expected_extra = Counter({(name,0x0e):1 for name in allowed})
    expected_extra.update({('___startup_LOCKS_entry_lck_grp_startup_init_126',0x0e):1,
                           ('___startup_LOCKS_entry_lck_mtx_startup_init_127',0x0e):1})
    expected_removed = Counter({('__MergedGlobals',0x0e):2,('lJTI5_0',0x0e):1,
                                ('lJTI12_0',0x0e):1,
                                ('___startup_LOCKS_entry_lck_grp_startup_init_121',0x0e):1,
                                ('___startup_LOCKS_entry_lck_mtx_startup_init_122',0x0e):1})
    if (rn.record_counts-sn.record_counts != expected_removed or
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
    ap.parse_args()
    # Invalidate both published outputs before any input validation. A failed
    # run must never leave a prior success-looking kernel/manifest pair.
    OUT.mkdir(parents=True,exist_ok=True)
    published = OUT/'kernel.oriole-ufs-ro'
    output = OUT/'kernel.oriole-ufs-ro.pending'
    for path in (published, Path(str(published)+'.json'), output, Path(str(output)+'.json')):
        path.unlink(missing_ok=True)
    verify_cow_object()
    policy = verify_inputs()
    ar_tool = policy['tools']['ar']['path']
    reference = (REF/'kernel.development.sweet').read_bytes()
    if hashlib.sha256(reference).hexdigest() != '8e4d38ea655930ef1da4998ab236962caabb9c8af1efaed6a96e243039af2292':
        raise SystemExit('Unexpected reference kernel')
    OUT.mkdir(parents=True,exist_ok=True)
    original_archive = LINK/'kernel.development.sweet.a'
    archive = OUT/'kernel.development.sweet.a'
    shutil.copyfile(original_archive,archive)
    members = subprocess.check_output([ar_tool,'-t',str(archive)],text=True).splitlines()
    replacements = {
        'sweet_restart.o': SUPPORT/'restart-md0.o',
        'sweet_ufs.o': OBJECT,
        'sweet_usb.o': ROOT/'artifacts/fullroot-build-review/storage-objects/objects/patched/sweet_usb.o',
    }
    for name,source in replacements.items():
        if members.count(name)!=1:
            raise SystemExit('Archive must have exactly one '+name)
        obj=OUT/name;shutil.copyfile(source,obj)
        subprocess.run([ar_tool,'-r',str(archive),str(obj)],check=True)
        if subprocess.check_output([ar_tool,'-p',str(archive),name])!=source.read_bytes():
            raise SystemExit('Archive replacement differs from pinned object')
    sets = OUT/'reference-symbolsets.plist'
    sets.write_bytes(section(reference,'__LINKINFO','__symbolsets'))
    flags = shlex.split((LINK/'kernel.development.sweet.linkarguments').read_text())
    # .linkarguments includes EXTRA_KC_LINKARGS for kcgen, not the source kernel.
    # MakeInc.kernel:193-215 and MakeInc.def:847-852 supply the source-only flags.
    flags = [f for f in flags if not f.startswith('-L/Users/runner') and f not in
             ('-lfirehose_kernel','-lcc_kext','-Wl,-new_linker','-Wl,-rename_segment,__LASTDATA_CONST,__LAST')]
    cmd = [policy['tools']['clang']['path'],'-fuse-ld='+policy['tools']['ld64']['path']]+flags
    cmd += ['-Wl,-force_load,'+str(archive),str(SUPPORT/'firehose_buffer.o'),
            str(SUPPORT/'profile16/nonlto.o'),str(SUPPORT/'profile16/chkstk_darwin.S.o'),
            str(SUPPORT/'profile16/libkernel-profile16.a'),
            '-Wl,-alias_list,'+str(LINK/'kernel.development.sweet.alias.exp'),
            '-Wl,-sectcreate,__LINKINFO,__symbolsets,'+str(sets),
            '-Wl,-segprot,__LINKINFO,r--,r--','-o',str(output)]
    link_env = dict(os.environ)
    for name in ('SDKROOT','DEVELOPER_DIR','MACOSX_DEPLOYMENT_TARGET','CPATH',
                 'C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH',
                 'LIBRARY_PATH','COMPILER_PATH','GCC_EXEC_PREFIX',
                 'IPHONEOS_DEPLOYMENT_TARGET','TVOS_DEPLOYMENT_TARGET',
                 'WATCHOS_DEPLOYMENT_TARGET','DRIVERKIT_DEPLOYMENT_TARGET'):
        link_env.pop(name,None)
    subprocess.run(cmd,check=True,env=link_env)
    subprocess.run([policy['tools']['strip']['path'],'-S',str(output)],check=True,env=link_env)
    output.write_bytes(pin_reference_uuid(reference, output.read_bytes()))
    # Do not transplant CTF: generated per build; zero-vmsize CTF is omitted from
    # the original payload by mkpayload.build (line155), too.
    blob = output.read_bytes()
    if struct.unpack_from('<I',blob,24)[0] != 0x200001:
        raise SystemExit('Expected NOUNDEFS|PIE, rejecting output')
    audit = verify_output(reference,blob,True)
    manifest = {'audit':audit,'input_policy_sha256':digest(ROOT/'docs/oriole-storage-link-inputs.json'),
                'cow_inputs':{str(path.relative_to(ROOT)):digest(path) for path in COW_PINS},
                'offline_only':True,'command':cmd,'sha256':hashlib.sha256(blob).hexdigest(),
                'reference_sha256':hashlib.sha256(reference).hexdigest(),
                'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                'firehose_sha256':hashlib.sha256((SUPPORT/'firehose_buffer.o').read_bytes()).hexdigest(),
                'ctf':'Not transplanted; original zero-vmsize CTF is not loaded by payload generator.',
                'size':len(blob)}
    Path(str(output)+'.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # Publish the manifest last; interrupted publication has no valid pair.
    output.replace(published)
    Path(str(output)+'.json').replace(Path(str(published)+'.json'))
    print('Offline PIE relink:',published,'SHA256='+manifest['sha256'])


if __name__ == '__main__':
    main()
