#!/usr/bin/env python3
"""Offline, pinned 0109 framebuffer relink for local Pixel 6 builds.

Builds no phone image and touches no device. The result is a candidate, not a
substitute for a hardware result. All output stays in ignored private/.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import struct
import subprocess
import tempfile
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'private/fbsnap-work'
SOURCE = WORK / 'baseline/iokit/Kernel/arm/SweetFramebuffer.cpp'
HEADER = SOURCE.with_name('SweetSurface.h')
OLD = ROOT / 'private/framebuffer-source/iokit/Kernel/arm/SweetFramebuffer.cpp'
PATCH = ROOT / 'research/pixelios-kernel/xnu/patches/0109-sweet-fb-panel-snapshot.patch'
RECIPE = ROOT / 'artifacts/fullroot-kernel/sweet_ufs.oriole-ro-command.json'
BASE = ROOT / 'private/oriole-cow512-work/relink'
OUT = WORK / 'local-relink'
PINS = {
    OLD: '5a3c4bf3c2e8500636887ea8b59f9f7481180c4abd5b32f8f238c525d21eb716',
    SOURCE: '424db20233c42c7aec368bd11a9ca22b4478a7daf9d127b44aed9e99385633ea',
    HEADER: '3a3efd984200566285009001ca114aff39c3e6ee597a7ace9511ebdc75137425',
    PATCH: 'ace0de2eb958fb5e9a861049cc02e9f8f2819dea54b503dc09187e5a34458ca7',
    RECIPE: '695ffc39aa9a8e40c2e86b2ead926db91ef1832fc9189e9ada10150c0610712c',
    BASE / 'kernel.development.sweet.a': '8505152cdb78dd1439055df1d7d95e1f9ee4062407ea225f2eef4a64e3fdfeff',
    BASE / 'kernel.oriole-ufs-ro': 'eb38bc975e299f83c94c7e83a332f484d414bdc209064b30bf87e15f0ab1dd1c',
}
EXPECTED_KERNEL_SHA256 = '822584e5de35ff7172102ef43352c0f6ddfc6ffcff254836645740c7d0e49b2a'
EXPECTED_KERNEL_SIZE = 16700232


def clean_build_env():
    env = dict(os.environ)
    for name in ('SDKROOT', 'DEVELOPER_DIR', 'MACOSX_DEPLOYMENT_TARGET', 'CPATH',
                 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                 'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX',
                 'IPHONEOS_DEPLOYMENT_TARGET', 'TVOS_DEPLOYMENT_TARGET',
                 'WATCHOS_DEPLOYMENT_TARGET', 'DRIVERKIT_DEPLOYMENT_TARGET'):
        env.pop(name, None)
    return env


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_fb(source, output, suffix):
    command = json.loads(RECIPE.read_text())
    command[command.index('-c') + 1] = str(source)
    command[command.index('-o') + 1] = str(output)
    command[command.index('-MF') + 1] = str(OUT / (suffix + '.d'))
    # MakeInc.def selects XNU_TARGET_OS_OSX for the macOS XNU build. Without
    # it the baseline omits ~6 KiB of reserved C++ vtable slots.
    command += ['-I', str(HEADER.parent), '-std=gnu++17', '-fno-exceptions',
                '-fno-rtti', '-DXNU_TARGET_OS_OSX']
    with (OUT / (suffix + '.warnings')).open('w') as errors:
        subprocess.run(command, cwd=ROOT / 'research/xnu-8796-reference', check=True,
                       env=clean_build_env(), stdout=subprocess.DEVNULL, stderr=errors)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    published = OUT / 'kernel.oriole-fbsnap'
    manifest_path = OUT / 'kernel.oriole-fbsnap.json'
    output = OUT / 'kernel.oriole-fbsnap.pending'
    pending_manifest = OUT / 'kernel.oriole-fbsnap.json.pending'
    for path in (published, manifest_path, output, pending_manifest):
        path.unlink(missing_ok=True)
    # Reuse the previously pinned COW relink policy and Mach-O parser.
    m = runpy.run_path(str(ROOT / 'tools/relink-oriole-cow-xnu.py'))
    policy = m['verify_inputs']()
    for path, expected in PINS.items():
        if digest(path) != expected:
            raise SystemExit(f'Unreviewed framebuffer input: {path}')
    with tempfile.TemporaryDirectory() as name:
        tree = Path(name)
        reconstructed = tree / 'iokit/Kernel/arm/SweetFramebuffer.cpp'
        reconstructed.parent.mkdir(parents=True)
        reconstructed.write_bytes(OLD.read_bytes())
        subprocess.run([policy['tools']['git']['path'], 'apply', '--include=iokit/Kernel/arm/SweetFramebuffer.cpp',
                        str(PATCH)], cwd=tree, check=True)
        if reconstructed.read_bytes() != SOURCE.read_bytes():
            raise SystemExit('0109 source reconstruction mismatch')
    original = OUT / 'SweetFramebuffer.baseline.cpo'
    replacement = OUT / 'SweetFramebuffer.cpo'
    compile_fb(OLD, original, 'baseline')
    compile_fb(SOURCE, replacement, 'candidate')
    if digest(original) != '108d908b91f0be22c0eca1985706badbb7dd03996126bcdcef33de2b6099391f':
        raise SystemExit('Baseline framebuffer object differs from reviewed compiler output')
    if digest(replacement) != '7138bd1c451eb972ff65b9a117bb3d2805b6a0a236f96133aa16bfa75a2ca9c8':
        raise SystemExit('Candidate framebuffer object differs from reviewed compiler output')
    ar = policy['tools']['ar']['path']
    original_member = subprocess.check_output([ar, '-p', str(BASE / 'kernel.development.sweet.a'),
                                                'SweetFramebuffer.cpo'])
    if hashlib.sha256(original_member).hexdigest() != '6e271119679c0b9005b6b24f6ed9de6d3c661d10131ce8d5a5d69477bb76ba9d':
        raise SystemExit('Unexpected original framebuffer archive member')
    if subprocess.check_output([ar, '-t', str(BASE / 'kernel.development.sweet.a')], text=True).splitlines().count('SweetFramebuffer.cpo') != 1:
        raise SystemExit('Expected one original framebuffer member')
    # Ignore addresses; names and binding are the ABI baseline.
    def export_names(blob):
        with tempfile.NamedTemporaryFile(suffix='.cpo') as file:
            Path(file.name).write_bytes(blob)
            return {line.split()[-1] for line in subprocess.check_output(['nm', '-gU', file.name], text=True).splitlines()}
    if export_names(original.read_bytes()) != export_names(original_member):
        raise SystemExit('Local compiler changed baseline framebuffer exports')
    with tempfile.NamedTemporaryFile(suffix='.cpo') as file:
        Path(file.name).write_bytes(original_member)
        original_imports = subprocess.check_output(['nm', '-u', file.name])
        if (original_imports != subprocess.check_output(['nm', '-u', str(original)]) or
                original_imports != subprocess.check_output(['nm', '-u', str(replacement)])):
            raise SystemExit('Framebuffer undefined imports differ')
        def const_size(path):
            sizes = subprocess.check_output(['size', '-m', str(path)], text=True)
            for line in sizes.splitlines():
                if line.startswith('\tSection (__DATA, __const):'):
                    return int(line.split(':', 1)[1].strip())
            raise SystemExit('Missing vtable section')
        if const_size(file.name) != const_size(original) or const_size(file.name) != const_size(replacement):
            raise SystemExit('Framebuffer vtable section changed')
        def vtable_relocations(path):
            raw = subprocess.check_output(['otool', '-rv', str(path)], text=True)
            return raw.split('Relocation information (__DATA,__const)', 1)[1].split(
                'Relocation information (__DWARF', 1)[0]
        # The original archive carries DWARF and local Clang does not. All
        # baseline vtable relocations must match despite text codegen changes.
        if vtable_relocations(file.name) != vtable_relocations(original):
            raise SystemExit('Local baseline vtable relocations differ')
    old_exports = export_names(original_member)
    new_exports = export_names(replacement.read_bytes())
    if (old_exports - new_exports or new_exports - old_exports !=
            {'__ZN9AppleCLCD9snapFiredEP8OSObjectP18IOTimerEventSource'}):
        raise SystemExit('Unexpected framebuffer export delta')
    archive = OUT / 'kernel.development.sweet.a'
    shutil.copyfile(BASE / 'kernel.development.sweet.a', archive)
    subprocess.run([ar, '-r', str(archive), str(replacement)], check=True)
    if subprocess.check_output([ar, '-p', str(archive), 'SweetFramebuffer.cpo']) != replacement.read_bytes():
        raise SystemExit('Archive member mismatch')
    link = m['LINK']; support = m['SUPPORT']
    old_kernel = (BASE / 'kernel.oriole-ufs-ro').read_bytes()
    symbolsets = OUT / 'reference-symbolsets.plist'
    symbolsets.write_bytes(m['section'](old_kernel, '__LINKINFO', '__symbolsets'))
    flags = shlex.split((link / 'kernel.development.sweet.linkarguments').read_text())
    flags = [f for f in flags if not f.startswith('-L/Users/runner') and f not in
             ('-lfirehose_kernel', '-lcc_kext', '-Wl,-new_linker',
              '-Wl,-rename_segment,__LASTDATA_CONST,__LAST')]
    cmd = [policy['tools']['clang']['path'], '-fuse-ld=' + policy['tools']['ld64']['path']] + flags
    cmd += ['-Wl,-force_load,' + str(archive), str(support / 'firehose_buffer.o'),
            str(support / 'profile16/nonlto.o'), str(support / 'profile16/chkstk_darwin.S.o'),
            str(support / 'profile16/libkernel-profile16.a'),
            '-Wl,-alias_list,' + str(link / 'kernel.development.sweet.alias.exp'),
            '-Wl,-sectcreate,__LINKINFO,__symbolsets,' + str(symbolsets),
            '-Wl,-segprot,__LINKINFO,r--,r--', '-o', str(output)]
    env = clean_build_env()
    subprocess.run(cmd, check=True, env=env)
    subprocess.run([policy['tools']['strip']['path'], '-S', str(output)], check=True, env=env)
    candidate = m['pin_reference_uuid'](old_kernel, output.read_bytes())
    output.write_bytes(candidate)
    old_segments, old_symbols, old_entry, old_commands = m['macho_info'](old_kernel)
    new_segments, new_symbols, new_entry, new_commands = m['macho_info'](candidate)
    if struct.unpack_from('<I', candidate, 24)[0] != 0x200001:
        raise SystemExit('Expected NOUNDEFS|PIE')
    if old_entry != new_entry or old_commands != new_commands or set(old_segments) != set(new_segments):
        raise SystemExit('Mach-O entry, commands or segment set changed')
    if any(old_segments[k] != new_segments[k] for k in old_segments if k != '__LINKEDIT'):
        raise SystemExit('Loaded segment layout changed')
    old_linkedit, new_linkedit = old_segments['__LINKEDIT'], new_segments['__LINKEDIT']
    if (old_linkedit[0] != new_linkedit[0] or old_linkedit[4:] != new_linkedit[4:] or
            ((old_linkedit[1] + 0x3fff) & ~0x3fff) !=
            ((new_linkedit[1] + 0x3fff) & ~0x3fff) or
            new_linkedit[2] != new_segments['__LINKINFO'][2] + new_segments['__LINKINFO'][3] or
            new_linkedit[2] + new_linkedit[3] != len(candidate) or
            not 0 <= new_linkedit[1] - new_linkedit[3] < 0x4000):
        raise SystemExit('LINKEDIT layout changed unexpectedly')
    if set(new_symbols) - set(old_symbols) != {
            '__ZN9AppleCLCD9snapFiredEP8OSObjectP18IOTimerEventSource',
            '__ZZN9AppleCLCD9snapFiredEP8OSObjectP18IOTimerEventSourceE6digits'}:
        raise SystemExit('Unexpected new kernel symbols')
    if set(old_symbols) - set(new_symbols):
        raise SystemExit('Existing kernel symbols removed')
    old_globals = {n for n, (_, global_) in old_symbols.items() if global_}
    new_globals = {n for n, (_, global_) in new_symbols.items() if global_}
    expected_new = '__ZN9AppleCLCD9snapFiredEP8OSObjectP18IOTimerEventSource'
    if new_globals - old_globals != {expected_new} or old_globals - new_globals:
        raise SystemExit('Unexpected global-symbol scope change')
    if new_symbols.record_counts - old_symbols.record_counts != Counter({
            (expected_new, 0x0f): 1,
            ('__ZZN9AppleCLCD9snapFiredEP8OSObjectP18IOTimerEventSourceE6digits', 0x0e): 1}) or \
            old_symbols.record_counts - new_symbols.record_counts != Counter({('lJTI91_0', 0x0e): 1}):
        raise SystemExit('Unexpected symbol-record delta')
    if m['section'](old_kernel, '__LINKINFO', '__symbolsets') != \
            m['section'](candidate, '__LINKINFO', '__symbolsets'):
        raise SystemExit('Kernel symbolsets changed')
    def read_symbol(data, segments, symbols, name, count):
        address = symbols[name][0]
        for va, _, file_offset, file_size, _, _ in segments.values():
            if va <= address and address + count <= va + file_size:
                return data[file_offset + address - va:file_offset + address - va + count]
        raise SystemExit('ABI symbol not file-backed: ' + name)
    if (read_symbol(candidate, new_segments, new_symbols, '___llvm_profile_raw_version', 8) !=
            struct.pack('<Q', 8) or
            read_symbol(old_kernel, old_segments, old_symbols, '___llvm_profile_raw_version', 8) !=
            struct.pack('<Q', 8)):
        raise SystemExit('Compiler profile ABI changed')
    if read_symbol(old_kernel, old_segments, old_symbols, '___chkstk_darwin', 48) != \
            read_symbol(candidate, new_segments, new_symbols, '___chkstk_darwin', 48):
        raise SystemExit('Stack-check implementation changed')
    manifest = {'sha256': hashlib.sha256(candidate).hexdigest(), 'size': len(candidate),
                'patch': digest(PATCH), 'archive': digest(archive),
                'compiler': digest(Path(policy['tools']['clang']['path'])),
                'baseline_kernel': digest(BASE / 'kernel.oriole-ufs-ro'),
                'offline_only': True, 'ci_green': False}
    if manifest['sha256'] != EXPECTED_KERNEL_SHA256 or manifest['size'] != EXPECTED_KERNEL_SIZE:
        raise SystemExit('Kernel bytes differ from audited candidate')
    pending_manifest.write_text(json.dumps(manifest, indent=2) + '\n')
    output.replace(published)
    pending_manifest.replace(manifest_path)
    print('Offline framebuffer relink:', published, 'SHA256=' + manifest['sha256'])


if __name__ == '__main__':
    main()
