#!/usr/bin/env python3
"""Rebuild and audit the offline Oriole DWC3 resource-observation kernel.

All outputs remain in ignored private/. This does not make a boot image or
connect to a device; the patch has no hardware boot result yet.
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
PREVIOUS = ROOT / "private/oriole-net-route-source/relink-0123"
SOURCE = ROOT / "private/oriole-net-route-source"
OUT = SOURCE / "relink-0124"
PATCH = ROOT / "research/pixelios-kernel/xnu/patches/0124-oriole-usb-transfer-resource-observe.patch"
RECIPE = ROOT / "artifacts/fullroot-kernel/sweet_usb.oriole-ro-command.json"
BEFORE = PREVIOUS / "sweet_usb.c.before-0124"
AFTER = SOURCE / "bsd/dev/sweet_usb.c"
REFERENCE = PREVIOUS / "kernel.oriole-net-route-0123.pending"
BASE_ARCHIVE = PREVIOUS / "kernel.development.sweet.a"
PINS = {
    PATCH: "b4994afa838175cfa5cc7ec1677a63d900bf3894c4c4dbac0c36e612dcd42b3e",
    RECIPE: "523b4cea05fa61732a5f0d0b4565e2bf892b3caba3bb643bdc5ddbc4d0d3575a",
    BEFORE: "4feafdfbb47cb142873ae523f5b87f3db7c203137b96361806b78cc3d47a9b14",
    AFTER: "f6d739115923d8a241a0a7bf6972e4f625cd3a01cd5f75f01f191cd51defb82a",
    REFERENCE: "f68406db756901338eedec463cec3bf54c063f56c817c8fb5173398fb89a89ef",
    BASE_ARCHIVE: "9139adfb70aa71cffcde1c306a344ca63433474cbcaa3a0dd28162e4d1df4ec4",
}
EXPECTED_KERNEL_SHA256 = "6dc7bd5d718d6292cd41aeb924c9966bc822ab2067eae41f24663b26fb04046b"
EXPECTED_KERNEL_SIZE = 16697408


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_segments(reference, candidate, m):
    old, old_symbols, old_entry, old_commands = m["macho_info"](reference)
    new, new_symbols, new_entry, new_commands = m["macho_info"](candidate)
    if old_entry != new_entry or old_commands != new_commands or set(old) != set(new):
        raise SystemExit("Kernel entry, load commands or segment set changed")
    if m["section"](reference, "__LINKINFO", "__symbolsets") != \
            m["section"](candidate, "__LINKINFO", "__symbolsets"):
        raise SystemExit("Kernel symbolsets changed")
    old_public = {name for name, (_, public) in old_symbols.items() if public}
    new_public = {name for name, (_, public) in new_symbols.items() if public}
    if old_public != new_public:
        raise SystemExit("Linked public globals changed")
    for name in old:
        a, b = old[name], new[name]
        if a[4:] != b[4:] or b[3] > b[1]:
            raise SystemExit("Segment protection or file size changed: " + name)
        if name in ("__TEXT", "__DATA_CONST") and a != b:
            raise SystemExit("Early segment changed: " + name)
        if name == "__TEXT_EXEC" and \
                (b[0] - a[0], b[1] - a[1], b[2] - a[2], b[3] - a[3]) != \
                (0, -0x4000, 0, -0x4000):
            raise SystemExit("Unexpected executable segment change")
        if name not in ("__TEXT", "__DATA_CONST", "__TEXT_EXEC") and \
                (b[0] - a[0], b[2] - a[2]) != (-0x4000, -0x4000):
            raise SystemExit("Unexpected downstream segment shift: " + name)
        if name not in ("__TEXT", "__DATA_CONST", "__TEXT_EXEC", "__LINKEDIT") and \
                (b[1] - a[1], b[3] - a[3]) != (0, 0):
            raise SystemExit("Unexpected downstream segment size: " + name)
    if new["__LINKEDIT"][1] != old["__LINKEDIT"][1] or \
            new["__LINKEDIT"][3] - old["__LINKEDIT"][3] != -0x18:
        raise SystemExit("Unexpected LINKEDIT size")
    for label, segments, size in (("reference", old, len(reference)),
                                  ("candidate", new, len(candidate))):
        spans = sorted((segment[0], segment[0] + segment[1])
                       for segment in segments.values())
        files = sorted((segment[2], segment[2] + segment[3])
                       for segment in segments.values())
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise SystemExit(label + " VA segments overlap")
        if files[0][0] != 0 or files[-1][1] != size or \
                any(left[1] > right[0] for left, right in zip(files, files[1:])):
            raise SystemExit(label + " file segments overlap or do not cover EOF")


def main():
    m = runpy.run_path(str(ROOT / "tools/relink-oriole-cow-xnu.py"))
    previous = runpy.run_path(str(ROOT / "tools/relink-oriole-netroute-xnu-0123.py"))
    policy = m["verify_inputs"]()
    for path, expected in PINS.items():
        if sha(path) != expected:
            raise SystemExit("Unreviewed input: " + str(path))
    with tempfile.TemporaryDirectory() as td:
        source = Path(td) / "bsd/dev/sweet_usb.c"
        source.parent.mkdir(parents=True)
        shutil.copyfile(BEFORE, source)
        subprocess.run([policy["tools"]["git"]["path"], "apply", str(PATCH)],
                       cwd=td, check=True)
        if source.read_bytes() != AFTER.read_bytes():
            raise SystemExit("Patch reconstruction mismatch")

    OUT.mkdir(parents=True, exist_ok=True)
    recipe = json.loads(RECIPE.read_text())
    if not isinstance(recipe, list) or any(recipe.count(flag) != 1
                                           for flag in ("-c", "-o", "-MF")):
        raise SystemExit("Unexpected compiler recipe")
    object_file = OUT / "sweet_usb.o"
    command = recipe.copy()
    for flag, path in (("-c", AFTER), ("-o", object_file),
                       ("-MF", OUT / "sweet_usb.o.d")):
        command[command.index(flag) + 1] = str(path)
    command[41:41] = ["-I", str(SOURCE / "bsd")]
    with (OUT / "sweet_usb.o.warnings").open("w") as warnings:
        subprocess.run(command, cwd=ROOT / "research/xnu-8796-reference",
                       env=previous["clean_env"](), check=True,
                       stdout=subprocess.DEVNULL, stderr=warnings)

    archive = OUT / "kernel.development.sweet.a"
    shutil.copyfile(BASE_ARCHIVE, archive)
    ar = policy["tools"]["ar"]["path"]
    members = subprocess.check_output([ar, "-t", str(archive)], text=True).splitlines()
    if members.count("sweet_usb.o") != 1:
        raise SystemExit("Archive member missing or duplicated")
    original = OUT / "sweet_usb.o.original"
    original.write_bytes(subprocess.check_output([ar, "-p", str(archive), "sweet_usb.o"]))
    if previous["symbols"](original, "-u") != previous["symbols"](object_file, "-u") or \
            previous["symbols"](original, "-gU") != previous["symbols"](object_file, "-gU"):
        raise SystemExit("Unexpected sweet_usb.o import or public symbol delta")
    subprocess.run([ar, "-r", str(archive), str(object_file)], check=True)
    if subprocess.check_output([ar, "-p", str(archive), "sweet_usb.o"]) != object_file.read_bytes():
        raise SystemExit("Archive replacement failed")

    reference = REFERENCE.read_bytes()
    link, support = m["LINK"], m["SUPPORT"]
    symbolsets = OUT / "reference-symbolsets.plist"
    symbolsets.write_bytes(m["section"](reference, "__LINKINFO", "__symbolsets"))
    flags = shlex.split((link / "kernel.development.sweet.linkarguments").read_text())
    flags = [flag for flag in flags if not flag.startswith("-L/Users/runner") and flag not in
             ("-lfirehose_kernel", "-lcc_kext", "-Wl,-new_linker",
              "-Wl,-rename_segment,__LASTDATA_CONST,__LAST")]
    output = OUT / "kernel.oriole-usb-resource-0124.pending"
    cmd = [policy["tools"]["clang"]["path"],
           "-fuse-ld=" + policy["tools"]["ld64"]["path"]] + flags
    cmd += ["-Wl,-force_load," + str(archive), str(support / "firehose_buffer.o"),
            str(support / "profile16/nonlto.o"), str(support / "profile16/chkstk_darwin.S.o"),
            str(support / "profile16/libkernel-profile16.a"),
            "-Wl,-alias_list," + str(link / "kernel.development.sweet.alias.exp"),
            "-Wl,-sectcreate,__LINKINFO,__symbolsets," + str(symbolsets),
            "-Wl,-segprot,__LINKINFO,r--,r--", "-o", str(output)]
    subprocess.run(cmd, check=True, env=previous["clean_env"]())
    subprocess.run([policy["tools"]["strip"]["path"], "-S", str(output)],
                   check=True, env=previous["clean_env"]())
    candidate = m["pin_reference_uuid"](reference, output.read_bytes())
    output.write_bytes(candidate)
    check_segments(reference, candidate, m)
    if len(candidate) != EXPECTED_KERNEL_SIZE or sha(output) != EXPECTED_KERNEL_SHA256:
        raise SystemExit("Relink bytes differ from the audited offline candidate")
    print("OFFLINE USB RESOURCE RELINK PASS", sha(output), "(no device validation)")


if __name__ == "__main__":
    main()
