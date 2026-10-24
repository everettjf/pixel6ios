#!/usr/bin/env python3
"""Build LLVM16's documented freestanding Darwin kernel profile subset, offline only."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'research/llvm16-profile'
EXPECTED = '7cbf1a2591520c2491aa35339f227775f4d3adf6'
if subprocess.check_output(['git','-C',str(SRC),'rev-parse','HEAD'],text=True).strip() != EXPECTED:
    raise SystemExit('Wrong LLVM source revision')
OUT = ROOT / 'artifacts/native-kernel/profile16'
OUT.mkdir(exist_ok=True)
# compiler-rt/cmake/Modules/CompilerRTDarwinUtils.cmake:414-419,475-481:
# these exact six profile sources are included in the cc_kext library.
names = ['InstrProfiling','InstrProfilingBuffer','InstrProfilingPlatformDarwin',
         'InstrProfilingWriter','InstrProfilingInternal','InstrProfilingVersionVar']
commands, sources, objects = [], {}, []
for name in names:
    source = SRC / ('compiler-rt/lib/profile/'+name+'.c')
    obj = OUT / (name+'.o')
    cmd = ['xcrun','clang','-target','arm64-apple-macos14.0','-mkernel','-ffreestanding',
           '-fno-builtin','-mgeneral-regs-only','-fstack-protector-strong','-O2',
           '-I',str(SRC/'compiler-rt/include'),'-c',str(source),'-o',str(obj)]
    subprocess.run(cmd,check=True)
    sources[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
    commands.append(cmd);objects.append(str(obj))
# Only this 48-byte stack-check primitive is reused from the installed toolchain.
# Its linked bytes are required to match the pinned reference kernel exactly by
# relink-reference-xnu.py. No Xcode27 profile-runtime member is used.
runtime = Path(subprocess.check_output(['xcrun','clang','-print-resource-dir'],text=True).strip()) / 'lib/darwin/libclang_rt.cc_kext.a'
thin = OUT/'xcode27-runtime-arm64.a'
subprocess.run(['xcrun','lipo',str(runtime),'-thin','arm64','-output',str(thin)],check=True)
stack = subprocess.check_output(['xcrun','ar','-p',str(thin),'chkstk_darwin.S.o'])
if hashlib.sha256(stack).hexdigest() != 'b7fc5ad36c518de95448b4d3a386a9b79c6583757e358a47a8c6c8284fb29a52':
    raise SystemExit('Unreviewed stack-check builtin')
(OUT/'chkstk_darwin.S.o').write_bytes(stack)
archive = OUT/'libkernel-profile16.a'
if archive.exists():
    archive.unlink()
subprocess.run(['xcrun','ar','-rcs',str(archive)]+objects,check=True)
# MakeInc.kernel includes this non-LTO sentinel separately from the .link archive.
source = ROOT/'research/xnu-8796-reference/libsa/nonlto.c'
cmd = ['xcrun','clang','-target','arm64-apple-macos14.0','-mkernel','-ffreestanding',
       '-mgeneral-regs-only','-c',str(source),'-o',str(OUT/'nonlto.o')]
subprocess.run(cmd,check=True);commands.append(cmd)
(OUT/'manifest.json').write_text(json.dumps({'offline_only':True,'llvm_commit':EXPECTED,
    'commands':commands,'sources':sources,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},indent=2)+'\n')
print('Compiled LLVM16 freestanding profile runtime and original XNU non-LTO sentinel')
