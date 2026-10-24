#!/usr/bin/env python3
"""Compile support objects for offline relinking experiments; never accesses a phone.

Uses the reference XNU's installed headers and original Apple release sources.
Outputs are experiments until independently reviewed and exercised under QEMU.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/native-kernel'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('target', choices=('firehose', 'restart', 'restart-md0'))
    a = ap.parse_args()
    sdk = Path(subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip())
    resource = Path(subprocess.check_output(['xcrun', 'clang', '-print-resource-dir'], text=True).strip())
    framework = OUT / 'fakeroot/System/Library/Frameworks/Kernel.framework'
    xnu = ROOT / 'research/xnu-8796-reference'
    includes = [framework / 'PrivateHeaders', framework / 'Headers', xnu / 'libkern',
                xnu / 'libkern/firehose', xnu / 'osfmk',
                ROOT / 'research/apple-libdispatch', sdk / 'usr/include', resource / 'include']
    cmd = ['xcrun', 'clang', '-target', 'arm64-apple-macos14.0', '-mkernel', '-nostdinc',
           '-fstack-protector-strong', '-fno-builtin', '-mgeneral-regs-only', '-O2', '-DKERNEL=1']
    for p in includes:
        cmd += ['-I', str(p)]
    if a.target == 'firehose':
        source = ROOT / 'research/apple-libdispatch/src/firehose/firehose_buffer.c'
        obj = OUT / 'firehose_buffer.o'
        cmd += ['-DDISPATCH_USE_DTRACE=0', '-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1',
                '-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0']
    else:
        # Reconstruct from the actual patch stack, not a hand-edited build copy.
        with tempfile.TemporaryDirectory(prefix='restart-source-', dir=OUT) as temporary:
            temporary = Path(temporary)
            subprocess.run(['git', 'init', '-q', str(temporary)], check=True)
            patches = ['0083-sweet-restart.patch', '0100-sweet-remote-reset.patch']
            if a.target == 'restart-md0':
                patches.append('0102-sweet-md0-usb-after-network.patch')
            for patch in patches:
                subprocess.run(['git', 'apply', '--include=bsd/dev/sweet_restart.c',
                                str(ROOT / 'research/pixelios-kernel/xnu/patches' / patch)],
                               cwd=temporary, check=True)
            content = (temporary / 'bsd/dev/sweet_restart.c').read_bytes()
        source = OUT / (a.target + '-source.c')
        source.write_bytes(content)
        obj = OUT / (a.target + '.o')
        # Exact declaration in xnu-8796.141.3 pexpert/pexpert/pexpert.h:343.
        # installhdrs strips XNU_KERNEL_PRIVATE declarations. No ABI is invented.
        compat = OUT / 'restart-compile-compat.h'
        compat.write_text('#include <mach/boolean.h>\n'
                          'extern boolean_t PE_parse_boot_arg_str(const char *, char *, int);\n')
        cmd += ['-DKERNEL_PRIVATE=1', '-DBSD_KERNEL_PRIVATE=1', '-D__APPLE_API_PRIVATE',
                '-DPRIVATE', '-include', str(compat)]
    cmd += ['-c', str(source), '-o', str(obj)]
    (OUT / (a.target + '-compile-command.json')).write_text(json.dumps(cmd, indent=2) + '\n')
    subprocess.run(cmd, check=True)
    Path(str(obj)+'.json').write_text(json.dumps({
        'offline_only': True, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'object_sha256': hashlib.sha256(obj.read_bytes()).hexdigest(), 'command': cmd
    }, indent=2)+'\n')
    print('Compiled offline experimental object:', obj)


if __name__ == '__main__':
    main()
