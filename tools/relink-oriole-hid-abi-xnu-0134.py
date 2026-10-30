#!/usr/bin/env python3
"""Reproduce the ABI-correct Oriole HID kernel offline; never access a phone.

Apple/XNU objects remain in ignored private/ and are not redistributed. This
script checks the 0130 source patch and the C++ vtable slot that caused the
0133 hardware panic before accepting the exact 0134 relink.
"""

import hashlib
import json
from pathlib import Path
import runpy
import shlex
import shutil
import struct
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "private/touch-hid-0134-work"
BASE = ROOT / "private/touch-hid-0132-work/iokit/Kernel/arm/hid/SweetHID.cpp"
SOURCE = ROOT / "private/touch-hid-0133-work/iokit/Kernel/arm/hid/SweetHID.cpp"
PATCH = ROOT / "research/pixelios-kernel/xnu/patches/0130-oriole-hid-catalog-probe.patch"
RECIPE = ROOT / "private/touch-xnu-source/relink-0121/compile-command.json"
ARCHIVE = ROOT / "private/touch-hid-0133-work/kernel.development.sweet.a"
REFERENCE = ROOT / "private/touch-hid-0133-work/kernel.oriole-hid-probe-0133.pending"
PINS = {
    BASE: "c86d06e374c7ecd8e2c6afd27b9c85a60db7b074899456d46be8ca68143a253e",
    SOURCE: "1bbe378502b2f918990858314490a70e6e807b961343cd44de132adf2c29f365",
    PATCH: "ae59951140e80974bffd115a5272b38d6e871d74add5cb5d59677dac79700992",
    RECIPE: "ff6da1a839708a6c9417f443a0070ed37a5c175b8d1b51bb11d2d3d0aa920c9a",
    ARCHIVE: "f96e64335a7bf1b026905a030f9e8d032693efaa633903445967595381cee270",
    REFERENCE: "50930206a85b9225d912fff5461b8598dce5b52b50788e41359ab3d3c92ea1d1",
}
OBJECT_SHA = "a38ad020fc0fa10ae8066479cb5b00ae849a82c25e5f41212b4342e528f20c22"
KERNEL_SHA = "f49ac09d591b577872ff009c9ee77c5e287ee4bb6873099ff82ffffa3d291c4e"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(path, expected):
    if digest(path) != expected:
        raise SystemExit("Unreviewed input or output: " + str(path))


def read_va(blob, segments, address):
    for base, _, fileoff, filesize, _, _ in segments.values():
        if base <= address and address + 8 <= base + filesize:
            return struct.unpack_from("<Q", blob, fileoff + address - base)[0]
    raise SystemExit("Vtable slot is not file-backed")


def main():
    m = runpy.run_path(str(ROOT / "tools/relink-oriole-cow-xnu.py"))
    clean_env = runpy.run_path(str(ROOT / "tools/relink-oriole-fbsnap-xnu.py"))["clean_build_env"]
    policy = m["verify_inputs"]()
    for path, expected in PINS.items():
        require(path, expected)
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        reconstructed = tree / "iokit/Kernel/arm/hid/SweetHID.cpp"
        reconstructed.parent.mkdir(parents=True)
        shutil.copyfile(BASE, reconstructed)
        subprocess.run([policy["tools"]["git"]["path"], "apply", str(PATCH)],
                       cwd=tree, check=True, stdout=subprocess.DEVNULL)
        if reconstructed.read_bytes() != SOURCE.read_bytes():
            raise SystemExit("0130 patch reconstruction mismatch")

    WORK.mkdir(parents=True, exist_ok=True)
    obj = WORK / "SweetHID.cpo"
    recipe = json.loads(RECIPE.read_text())
    if not isinstance(recipe, list) or any(recipe.count(x) != 1 for x in ("-MD", "-MF", "-c", "-o")):
        raise SystemExit("Unexpected SweetHID compiler recipe")
    recipe[recipe.index("-MD"):recipe.index("-MD")] = ["-DXNU_TARGET_OS_OSX=1"]
    for flag, value in (("-MF", WORK / "SweetHID.d"), ("-c", SOURCE), ("-o", obj)):
        recipe[recipe.index(flag) + 1] = str(value)
    # The checked source uses the local header set named in the private recipe.
    if recipe[recipe.index("-o") + 2] != "-I" or not \
            (Path(recipe[recipe.index("-o") + 3]) / "IOHIDEventService.h").is_file():
        raise SystemExit("SweetHID header directory unavailable")
    (WORK / "compile-command.json").write_text(json.dumps(recipe, indent=2) + "\n")
    with (WORK / "compile.log").open("w") as log:
        subprocess.run(recipe, cwd=ROOT / "research/xnu-8796-reference",
                       env=clean_env(), stdout=log, stderr=subprocess.STDOUT, check=True)
    require(obj, OBJECT_SHA)

    archive = WORK / "kernel.development.sweet.a"
    shutil.copyfile(ARCHIVE, archive)
    ar = policy["tools"]["ar"]["path"]
    if subprocess.check_output([ar, "-t", str(archive)], text=True).splitlines().count("SweetHID.cpo") != 1:
        raise SystemExit("Expected one SweetHID archive member")
    subprocess.run([ar, "-r", str(archive), str(obj)], check=True, stdout=subprocess.DEVNULL)
    if subprocess.check_output([ar, "-p", str(archive), "SweetHID.cpo"]) != obj.read_bytes():
        raise SystemExit("SweetHID archive replacement failed")
    # ar records member timestamps; the member bytes and final kernel are the
    # reproducible parts of this relink, not the archive container's SHA-256.

    reference = REFERENCE.read_bytes()
    symbolsets = WORK / "reference-symbolsets.plist"
    symbolsets.write_bytes(m["section"](reference, "__LINKINFO", "__symbolsets"))
    link, support = m["LINK"], m["SUPPORT"]
    flags = shlex.split((link / "kernel.development.sweet.linkarguments").read_text())
    flags = [f for f in flags if not f.startswith("-L/Users/runner") and f not in
             ("-lfirehose_kernel", "-lcc_kext", "-Wl,-new_linker",
              "-Wl,-rename_segment,__LASTDATA_CONST,__LAST")]
    output = WORK / "kernel.oriole-hid-abi-0134.pending"
    command = [policy["tools"]["clang"]["path"],
               "-fuse-ld=" + policy["tools"]["ld64"]["path"]] + flags
    command += ["-Wl,-force_load," + str(archive), str(support / "firehose_buffer.o"),
                str(support / "profile16/nonlto.o"),
                str(support / "profile16/chkstk_darwin.S.o"),
                str(support / "profile16/libkernel-profile16.a"),
                "-Wl,-alias_list," + str(link / "kernel.development.sweet.alias.exp"),
                "-Wl,-sectcreate,__LINKINFO,__symbolsets," + str(symbolsets),
                "-Wl,-segprot,__LINKINFO,r--,r--", "-o", str(output)]
    (WORK / "link-command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (WORK / "link.log").open("w") as log:
        subprocess.run(command, env=clean_env(), stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([policy["tools"]["strip"]["path"], "-S", str(output)], check=True)
    candidate = m["pin_reference_uuid"](reference, output.read_bytes())
    output.write_bytes(candidate)
    require(output, KERNEL_SHA)
    old_segments, old_symbols, old_entry, old_commands = m["macho_info"](reference)
    segments, symbols, entry, commands = m["macho_info"](candidate)
    if entry != old_entry or commands != old_commands or set(segments) != set(old_segments) or \
            set(symbols) != set(old_symbols) or \
            m["section"](reference, "__LINKINFO", "__symbolsets") != \
            m["section"](candidate, "__LINKINFO", "__symbolsets"):
        raise SystemExit("Unexpected kernel layout, symbol, or entry delta")
    slot = symbols["__ZTV12OSOrderedSet"][0] + 0x10 + 0x150
    target = symbols["__ZNK12OSOrderedSet8getCountEv"][0]
    if read_va(candidate, segments, slot) != target:
        raise SystemExit("OSOrderedSet getCount vtable slot does not match")
    print("OFFLINE HID ABI RELINK PASS " + KERNEL_SHA)


if __name__ == "__main__":
    main()
