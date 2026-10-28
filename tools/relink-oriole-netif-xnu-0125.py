#!/usr/bin/env python3
"""Rebuild and audit the opt-in Oriole ue0 IORegistry candidate offline.

All output stays in ignored private/. No boot image is created and no device is
accessed. The candidate has no phone result and is not a networking claim.
"""

import hashlib
import json
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "private/netif-source"
OUT = ROOT / "private/oriole-net-route-source/relink-0125"
PATCH = ROOT / "research/pixelios-kernel/xnu/patches/0125-oriole-usb-network-interface-registry.patch"
ARCHIVE = ROOT / "private/oriole-net-route-source/relink-0124/kernel.development.sweet.a"
REFERENCE = ROOT / "private/oriole-net-route-source/relink-0124/kernel.oriole-usb-resource-0124.pending"
USB_RECIPE = ROOT / "artifacts/fullroot-kernel/sweet_usb.oriole-ro-command.json"
FB_RECIPE = ROOT / "artifacts/fullroot-kernel/sweet_ufs.oriole-ro-command.json"
USB_HEADER_DIR = ROOT / "private/oriole-net-route-source/bsd"
FB_HEADER_DIR = ROOT / "private/fbsnap-work/baseline/iokit/Kernel/arm"
FILES = ("bsd/dev/sweet_usb.c", "iokit/Kernel/arm/SweetFramebuffer.cpp")
PINS = {
    PATCH: "9418888581000e30214846640d48706df4323179793ef0e5e52438aac67fee2c",
    ARCHIVE: "72b879ba9a7441f42d7b9a541b74616191a7dad2e86a79e866a842c82aad3b93",
    REFERENCE: "6dc7bd5d718d6292cd41aeb924c9966bc822ab2067eae41f24663b26fb04046b",
    USB_RECIPE: "523b4cea05fa61732a5f0d0b4565e2bf892b3caba3bb643bdc5ddbc4d0d3575a",
    FB_RECIPE: "695ffc39aa9a8e40c2e86b2ead926db91ef1832fc9189e9ada10150c0610712c",
    USB_HEADER_DIR / "net/route_private.h": "7f9a16a310e2592cb38fe290e6c1e8cff37474788f950d1b268591cbe6428160",
    FB_HEADER_DIR / "SweetSurface.h": "3a3efd984200566285009001ca114aff39c3e6ee597a7ace9511ebdc75137425",
    SOURCE / "before/bsd/dev/sweet_usb.c": "f6d739115923d8a241a0a7bf6972e4f625cd3a01cd5f75f01f191cd51defb82a",
    SOURCE / "before/iokit/Kernel/arm/SweetFramebuffer.cpp": "424db20233c42c7aec368bd11a9ca22b4478a7daf9d127b44aed9e99385633ea",
    SOURCE / "after/bsd/dev/sweet_usb.c": "43c50dd7bdfcdb299659d7b2b816659200f338c85cfb230608846dc128a74827",
    SOURCE / "after/iokit/Kernel/arm/SweetFramebuffer.cpp": "6b00db8d581e5f694c99df67b8b6e873a9df876c94ffc050ad9689f2dbfda302",
}
EXPECTED_OBJECTS = {
    "sweet_usb.o": "0f182f9709cb6d6c9b22b41072b820832f430013b5f63fb98f667d5b995ad924",
    "SweetFramebuffer.cpo": "dcb3f798b9af7121cde314a794848c3bc5626a217a28a5bb368585c2dfb1feba",
}
EXPECTED_KERNEL = "a1036dba2c11af88587a72ad581339af09efbe9f39dd9c727279240056492df6"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_object(recipe_path, source, output, extra, environment):
    recipe = json.loads(recipe_path.read_text())
    if not isinstance(recipe, list) or any(recipe.count(flag) != 1 for flag in ("-c", "-o", "-MF")):
        raise SystemExit("Unexpected compiler recipe: " + str(recipe_path))
    for flag, path in (("-c", source), ("-o", output), ("-MF", output.with_suffix(".d"))):
        recipe[recipe.index(flag) + 1] = str(path)
    recipe[recipe.index("-I"):recipe.index("-I")] = extra
    with output.with_suffix(".warnings").open("w") as warnings:
        subprocess.run(recipe, cwd=ROOT / "research/xnu-8796-reference", env=environment,
                       stdout=subprocess.DEVNULL, stderr=warnings, check=True)


def check_geometry(reference, candidate, m):
    old, old_symbols, old_entry, old_commands = m["macho_info"](reference)
    new, new_symbols, new_entry, new_commands = m["macho_info"](candidate)
    if old_commands != new_commands or set(old) != set(new):
        raise SystemExit("Kernel load commands or segment set changed")
    if m["section"](reference, "__LINKINFO", "__symbolsets") != \
            m["section"](candidate, "__LINKINFO", "__symbolsets"):
        raise SystemExit("Kernel symbolsets changed")
    if old["__TEXT"] != new["__TEXT"]:
        raise SystemExit("Kernel header/text segment changed")
    if old_entry - old["__TEXT_EXEC"][0] != new_entry - new["__TEXT_EXEC"][0]:
        raise SystemExit("Kernel entry moved within executable segment")
    for label, segments, size in (("reference", old, len(reference)),
                                  ("candidate", new, len(candidate))):
        va = sorted((v[0], v[0] + v[1]) for v in segments.values())
        spans = sorted((v[2], v[2] + v[3]) for v in segments.values())
        if any(a[1] > b[0] for a, b in zip(va, va[1:])):
            raise SystemExit(label + " virtual segments overlap")
        if spans[0][0] != 0 or spans[-1][1] != size or \
                any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise SystemExit(label + " file segments overlap or do not cover EOF")
    if set(old_symbols) - set(new_symbols):
        raise SystemExit("Kernel symbol disappeared")
    if "_sweet_usb_publish_network_interface" not in new_symbols:
        raise SystemExit("New registry hook missing from kernel")


def main():
    m = runpy.run_path(str(ROOT / "tools/relink-oriole-cow-xnu.py"))
    policy = m["verify_inputs"]()
    clean_env = runpy.run_path(str(ROOT / "tools/relink-oriole-fbsnap-xnu.py"))["clean_build_env"]
    for path, expected in PINS.items():
        if digest(path) != expected:
            raise SystemExit("Unreviewed input: " + str(path))
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        for rel in FILES:
            dst = tree / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / "before" / rel, dst)
        subprocess.run([policy["tools"]["git"]["path"], "apply", str(PATCH)], cwd=tree, check=True)
        for rel in FILES:
            if (tree / rel).read_bytes() != (SOURCE / "after" / rel).read_bytes():
                raise SystemExit("Patch reconstruction mismatch: " + rel)

    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {name: OUT / name for name in EXPECTED_OBJECTS}
    compile_object(USB_RECIPE, SOURCE / "after/bsd/dev/sweet_usb.c", outputs["sweet_usb.o"],
                   ["-I", str(USB_HEADER_DIR)], clean_env())
    compile_object(FB_RECIPE, SOURCE / "after/iokit/Kernel/arm/SweetFramebuffer.cpp",
                   outputs["SweetFramebuffer.cpo"],
                   ["-I", str(FB_HEADER_DIR), "-std=gnu++17", "-fno-exceptions", "-fno-rtti",
                    "-DXNU_TARGET_OS_OSX"], clean_env())
    for name, expected in EXPECTED_OBJECTS.items():
        if digest(outputs[name]) != expected:
            raise SystemExit("Compiler output drift: " + name)

    archive = OUT / "kernel.development.sweet.a"
    shutil.copyfile(ARCHIVE, archive)
    ar = policy["tools"]["ar"]["path"]
    members = subprocess.check_output([ar, "-t", str(archive)], text=True).splitlines()
    if any(members.count(name) != 1 for name in EXPECTED_OBJECTS):
        raise SystemExit("Expected exactly one archive member for each replacement")
    for name, path in outputs.items():
        subprocess.run([ar, "-r", str(archive), str(path)], check=True, stdout=subprocess.DEVNULL)
        if subprocess.check_output([ar, "-p", str(archive), name]) != path.read_bytes():
            raise SystemExit("Archive member replacement failed: " + name)

    reference = REFERENCE.read_bytes()
    symbolsets = OUT / "reference-symbolsets.plist"
    symbolsets.write_bytes(m["section"](reference, "__LINKINFO", "__symbolsets"))
    link, support = m["LINK"], m["SUPPORT"]
    flags = shlex.split((link / "kernel.development.sweet.linkarguments").read_text())
    flags = [f for f in flags if not f.startswith("-L/Users/runner") and f not in
             ("-lfirehose_kernel", "-lcc_kext", "-Wl,-new_linker",
              "-Wl,-rename_segment,__LASTDATA_CONST,__LAST")]
    output = OUT / "kernel.oriole-netif-0125.pending"
    command = [policy["tools"]["clang"]["path"], "-fuse-ld=" + policy["tools"]["ld64"]["path"]] + flags
    command += ["-Wl,-force_load," + str(archive), str(support / "firehose_buffer.o"),
                str(support / "profile16/nonlto.o"), str(support / "profile16/chkstk_darwin.S.o"),
                str(support / "profile16/libkernel-profile16.a"),
                "-Wl,-alias_list," + str(link / "kernel.development.sweet.alias.exp"),
                "-Wl,-sectcreate,__LINKINFO,__symbolsets," + str(symbolsets),
                "-Wl,-segprot,__LINKINFO,r--,r--", "-o", str(output)]
    with (OUT / "link.log").open("w") as log:
        subprocess.run(command, check=True, env=clean_env(), stdout=log, stderr=subprocess.STDOUT)
    subprocess.run([policy["tools"]["strip"]["path"], "-S", str(output)], check=True)
    candidate = m["pin_reference_uuid"](reference, output.read_bytes())
    output.write_bytes(candidate)
    check_geometry(reference, candidate, m)
    if digest(output) != EXPECTED_KERNEL:
        raise SystemExit("Kernel output drift: " + digest(output))
    print("OFFLINE NETIF RELINK PASS " + EXPECTED_KERNEL)


if __name__ == "__main__":
    main()
