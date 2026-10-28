#!/usr/bin/env python3
"""Offline Oriole 0122 extended bounded GUI touch-window relink; output stays in ignored private/.

This builds a candidate kernel only. A phone boot is required for validation.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import tempfile
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'private/touch-xnu-source'
OLD = WORK / 'sweet_touch_gs101.pre0122.c'
NEW = WORK / 'bsd/dev/sweet_touch_gs101.c'
PATCH = ROOT / 'research/pixelios-kernel/xnu/patches/0122-oriole-touch-extended-gui-window.patch'
RECIPE = ROOT / 'artifacts/fullroot-kernel/sweet_ufs.oriole-ro-command.json'
FB = WORK / 'relink-0121'
OUT = WORK / 'relink-0122'
PINS = {
    OLD: 'bdac6f9670689972becedd007aac33976312f2b6c91cb1211e076775c4030f16',
    PATCH: '552e7d58d51c6970106e5496d60dd29804a1956e7c49dfc5c1e492a3fd3a6823',
    RECIPE: '695ffc39aa9a8e40c2e86b2ead926db91ef1832fc9189e9ada10150c0610712c',
    FB / 'kernel.development.sweet.a': '538889e69139f1f1505fa6d79d978da7d2b3b49a5415c49b2cf132dc10665103',
    FB / 'kernel.oriole-touch-0121.pending': '89da99e097276dc4d5731ebb586e4716efed8936b8d8d33dd81e5a714350f109',
}
EXPECTED_KERNEL_SHA256 = '62c47dd99e2cfd9bf763c0b03c618223ca4deb4d1ab34c24e81a0abea1115d56'
EXPECTED_KERNEL_SIZE = 16697320

# The 0121 archive already imports PE_parse_boot_arg_str. This update must
# retain its symbol inventory and loaded segment map. No local nlist records
# may be added or removed by the recompiled touch object.
EXPECTED_REMOVED_LOCALS = Counter()
EXPECTED_ADDED_LOCALS = Counter()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_env():
    env = dict(os.environ)
    for key in ('SDKROOT', 'DEVELOPER_DIR', 'MACOSX_DEPLOYMENT_TARGET',
                'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                'OBJC_INCLUDE_PATH', 'LIBRARY_PATH', 'COMPILER_PATH',
                'GCC_EXEC_PREFIX', 'IPHONEOS_DEPLOYMENT_TARGET'):
        env.pop(key, None)
    return env


def verify_symbol_delta(old, new, text_exec):
    if old.record_counts - new.record_counts != EXPECTED_REMOVED_LOCALS or \
            new.record_counts - old.record_counts != EXPECTED_ADDED_LOCALS:
        raise SystemExit('Unexpected local or global Mach-O symbol delta')
    if any(old[name][1] != new[name][1] for name in old.keys() & new.keys()):
        raise SystemExit('Mach-O symbol scope changed')
    base, size, fileoff, filesize, maxprot, initprot = text_exec
    if maxprot != 5 or initprot != 5 or filesize > size:
        raise SystemExit('Unexpected executable segment protections')
    if any(name in old or not base <= new[name][0] < base + filesize or new[name][1]
           for name, _ in EXPECTED_ADDED_LOCALS):
        raise SystemExit('New private symbol outside file-backed executable segment')
    if any(not base <= old[name][0] < base + filesize or old[name][1]
           for name, _ in EXPECTED_REMOVED_LOCALS):
        raise SystemExit('Removed private symbol outside executable segment')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    m = runpy.run_path(str(ROOT / 'tools/relink-oriole-cow-xnu.py'))
    policy = m['verify_inputs']()
    for path, expected in PINS.items():
        if sha(path) != expected:
            raise SystemExit(f'Unreviewed relink input: {path}')
    with tempfile.TemporaryDirectory() as directory:
        tree = Path(directory)
        source = tree / 'bsd/dev/sweet_touch_gs101.c'
        source.parent.mkdir(parents=True)
        source.write_bytes(OLD.read_bytes())
        subprocess.run([policy['tools']['git']['path'], 'apply', str(PATCH)], cwd=tree, check=True)
        if source.read_bytes() != NEW.read_bytes():
            raise SystemExit('0122 source reconstruction mismatch')
    command = json.loads(RECIPE.read_text())
    obj = OUT / 'sweet_touch_gs101.o'
    command[command.index('-c') + 1] = str(NEW)
    command[command.index('-o') + 1] = str(obj)
    command[command.index('-MF') + 1] = str(OUT / 'sweet_touch_gs101.d')
    command += ['-I', str(WORK), '-Os']
    with (OUT / 'compiler.warnings').open('w') as errors:
        subprocess.run(command, cwd=ROOT / 'research/xnu-8796-reference', check=True,
                       env=clean_env(), stdout=subprocess.DEVNULL, stderr=errors)
    ar = policy['tools']['ar']['path']
    baseline_archive = FB / 'kernel.development.sweet.a'
    member = 'sweet_touch_gs101.o'
    if subprocess.check_output([ar, '-t', str(baseline_archive)], text=True).splitlines().count(member) != 1:
        raise SystemExit('Expected one touch archive member')
    original = OUT / 'sweet_touch_gs101.archive.o'
    original.write_bytes(subprocess.check_output([ar, '-p', str(baseline_archive), member]))
    def names(path, flag):
        return {line.split()[-1] for line in subprocess.check_output(['nm', flag, str(path)], text=True).splitlines()}
    if names(original, '-gU') != names(obj, '-gU') or \
            names(original, '-u') != names(obj, '-u'):
        raise SystemExit('Touch object public ABI changed')
    archive = OUT / 'kernel.development.sweet.a'
    shutil.copyfile(baseline_archive, archive)
    subprocess.run([ar, '-r', str(archive), str(obj)], check=True)
    if subprocess.check_output([ar, '-p', str(archive), member]) != obj.read_bytes():
        raise SystemExit('Touch archive replacement failed')
    old_kernel = (FB / 'kernel.oriole-touch-0121.pending').read_bytes()
    link = m['LINK']; support = m['SUPPORT']
    symbolsets = OUT / 'reference-symbolsets.plist'
    symbolsets.write_bytes(m['section'](old_kernel, '__LINKINFO', '__symbolsets'))
    flags = shlex.split((link / 'kernel.development.sweet.linkarguments').read_text())
    flags = [f for f in flags if not f.startswith('-L/Users/runner') and f not in
             ('-lfirehose_kernel', '-lcc_kext', '-Wl,-new_linker',
              '-Wl,-rename_segment,__LASTDATA_CONST,__LAST')]
    output = OUT / 'kernel.oriole-touch-0122.pending'
    cmd = [policy['tools']['clang']['path'], '-fuse-ld=' + policy['tools']['ld64']['path']] + flags
    cmd += ['-Wl,-force_load,' + str(archive), str(support / 'firehose_buffer.o'),
            str(support / 'profile16/nonlto.o'), str(support / 'profile16/chkstk_darwin.S.o'),
            str(support / 'profile16/libkernel-profile16.a'),
            '-Wl,-alias_list,' + str(link / 'kernel.development.sweet.alias.exp'),
            '-Wl,-sectcreate,__LINKINFO,__symbolsets,' + str(symbolsets),
            '-Wl,-segprot,__LINKINFO,r--,r--', '-o', str(output)]
    subprocess.run(cmd, check=True, env=clean_env())
    subprocess.run([policy['tools']['strip']['path'], '-S', str(output)], check=True, env=clean_env())
    candidate = m['pin_reference_uuid'](old_kernel, output.read_bytes())
    output.write_bytes(candidate)
    old_segments, old_symbols, old_entry, old_commands = m['macho_info'](old_kernel)
    new_segments, new_symbols, new_entry, new_commands = m['macho_info'](candidate)
    if old_entry != new_entry or old_commands != new_commands or set(old_segments) != set(new_segments):
        raise SystemExit('Mach-O entry, command or segment set changed')
    if any(old_segments[key] != new_segments[key] for key in old_segments if key != '__LINKEDIT'):
        raise SystemExit('Loaded Mach-O segment layout changed')
    old_linkedit, new_linkedit = old_segments['__LINKEDIT'], new_segments['__LINKEDIT']
    if old_linkedit[0] != new_linkedit[0] or old_linkedit[2] != new_linkedit[2] or \
            old_linkedit[4:] != new_linkedit[4:] or \
            new_linkedit[2] + new_linkedit[3] != len(candidate):
        raise SystemExit('Unexpected LINKEDIT layout')
    verify_symbol_delta(old_symbols, new_symbols, old_segments['__TEXT_EXEC'])
    if m['section'](old_kernel, '__LINKINFO', '__symbolsets') != m['section'](candidate, '__LINKINFO', '__symbolsets'):
        raise SystemExit('Kernel symbolsets changed')
    final = OUT / 'kernel.oriole-touch-0122'
    if sha(output) != EXPECTED_KERNEL_SHA256 or output.stat().st_size != EXPECTED_KERNEL_SIZE:
        raise SystemExit('Kernel bytes differ from reviewed candidate')
    output.replace(final)
    manifest = {'sha256': sha(final), 'size': final.stat().st_size,
                'patch_sha256': sha(PATCH), 'object_sha256': sha(obj),
                'archive_sha256': sha(archive), 'offline_only': True}
    (OUT / 'kernel.oriole-touch.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(final, manifest)


if __name__ == '__main__':
    main()
