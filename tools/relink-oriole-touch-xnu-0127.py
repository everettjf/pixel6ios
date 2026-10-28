#!/usr/bin/env python3
"""Offline relink of the 0126 FTM5 event-class fix into the Oriole GUI kernel.

This does not create a boot image or access a phone. Output stays in private/.
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
WORK = ROOT / "private/touch-xnu-source"
OUT = ROOT / "private/oriole-net-route-source/relink-0127"
PATCH_0088 = ROOT / "research/pixelios-kernel/xnu/patches/0088-sweet-gs101-touch.patch"
PATCH_0126 = ROOT / "research/pixelios-kernel/xnu/patches/0126-sweet-ftm5-point-class-decode.patch"
HEADER = WORK / "bsd/dev/sweet_ftm5.h"
SOURCE = WORK / "bsd/dev/sweet_touch_gs101.c"
RECIPE = ROOT / "artifacts/fullroot-kernel/sweet_ufs.oriole-ro-command.json"
PREV = ROOT / "private/oriole-net-route-source/relink-0125"
ARCHIVE = PREV / "kernel.development.sweet.a"
KERNEL = PREV / "kernel.oriole-netif-0125.pending"
PINS = {
    PATCH_0126: "630af74acfeab1d2af896d512ab2946f40f84ec15b2297543b1f3976a5d8f822",
    HEADER: "b510eeb343a58beb587757d8b5b54cc641df5c3a2015825a6b9d66dcd12d5699",
    SOURCE: "fc707c7f13e9192ca536878782eac25e4053223c7613575813708f3c639a0ba4",
    RECIPE: "695ffc39aa9a8e40c2e86b2ead926db91ef1832fc9189e9ada10150c0610712c",
    ARCHIVE: "2ffdd415fc079da742083c41a423fad3ec5518be2d40a87c6e74cfc4cdc8c4ad",
    KERNEL: "a1036dba2c11af88587a72ad581339af09efbe9f39dd9c727279240056492df6",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_from_0088():
    lines = PATCH_0088.read_text().splitlines(keepends=True)
    start = lines.index("+++ b/bsd/dev/sweet_ftm5.h\n") + 1
    output = []
    for line in lines[start:]:
        if line.startswith("--- "):
            break
        if line.startswith("@@"):
            continue
        if line.startswith("+"):
            output.append(line[1:])
    return "".join(output)


def verify_patch(git):
    with tempfile.TemporaryDirectory() as directory:
        tree = Path(directory)
        header = tree / "bsd/dev/sweet_ftm5.h"
        header.parent.mkdir(parents=True)
        header.write_text(source_from_0088())
        subprocess.run([git, "apply", "--check", str(PATCH_0126)], cwd=tree, check=True)
        subprocess.run([git, "apply", str(PATCH_0126)], cwd=tree, check=True)
        if header.read_bytes() != HEADER.read_bytes():
            raise SystemExit("0126 header reconstruction mismatch")


def main():
    m = runpy.run_path(str(ROOT / "tools/relink-oriole-cow-xnu.py"))
    policy = m["verify_inputs"]()
    clean_env = runpy.run_path(str(ROOT / "tools/relink-oriole-fbsnap-xnu.py"))["clean_build_env"]
    for path, expected in PINS.items():
        if sha(path) != expected:
            raise SystemExit("Unreviewed relink input: " + str(path))
    verify_patch(policy["tools"]["git"]["path"])
    OUT.mkdir(parents=True, exist_ok=True)

    recipe = json.loads(RECIPE.read_text())
    obj = OUT / "sweet_touch_gs101.o"
    for flag, path in (("-c", SOURCE), ("-o", obj), ("-MF", obj.with_suffix(".d"))):
        if recipe.count(flag) != 1:
            raise SystemExit("Unexpected compiler recipe flag: " + flag)
        recipe[recipe.index(flag) + 1] = str(path)
    recipe += ["-I", str(WORK), "-Os"]
    with (OUT / "compiler.warnings").open("w") as log:
        subprocess.run(recipe, cwd=ROOT / "research/xnu-8796-reference", env=clean_env(),
                       stdout=subprocess.DEVNULL, stderr=log, check=True)

    ar = policy["tools"]["ar"]["path"]
    member = "sweet_touch_gs101.o"
    if subprocess.check_output([ar, "-t", str(ARCHIVE)], text=True).splitlines().count(member) != 1:
        raise SystemExit("Expected exactly one touch archive member")
    original = OUT / "sweet_touch_gs101.archive.o"
    original.write_bytes(subprocess.check_output([ar, "-p", str(ARCHIVE), member]))
    def names(path, flag):
        return {line.split()[-1] for line in subprocess.check_output(["nm", flag, str(path)], text=True).splitlines()}
    if names(original, "-gU") != names(obj, "-gU") or names(original, "-u") != names(obj, "-u"):
        raise SystemExit("Touch object public ABI changed")
    archive = OUT / "kernel.development.sweet.a"
    shutil.copyfile(ARCHIVE, archive)
    subprocess.run([ar, "-r", str(archive), str(obj)], check=True)
    if subprocess.check_output([ar, "-p", str(archive), member]) != obj.read_bytes():
        raise SystemExit("Touch archive replacement failed")

    reference = KERNEL.read_bytes()
    symbolsets = OUT / "reference-symbolsets.plist"
    symbolsets.write_bytes(m["section"](reference, "__LINKINFO", "__symbolsets"))
    link, support = m["LINK"], m["SUPPORT"]
    flags = shlex.split((link / "kernel.development.sweet.linkarguments").read_text())
    flags = [f for f in flags if not f.startswith("-L/Users/runner") and f not in
             ("-lfirehose_kernel", "-lcc_kext", "-Wl,-new_linker",
              "-Wl,-rename_segment,__LASTDATA_CONST,__LAST")]
    output = OUT / "kernel.oriole-touch-0127.pending"
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
    output.write_bytes(m["pin_reference_uuid"](reference, output.read_bytes()))
    netif = runpy.run_path(str(ROOT / "tools/relink-oriole-netif-xnu-0125.py"))
    netif["check_geometry"](reference, output.read_bytes(), m)
    manifest = {"kernel_sha256": sha(output), "kernel_size": output.stat().st_size,
                "touch_object_sha256": sha(obj), "archive_sha256": sha(archive),
                "patch_sha256": sha(PATCH_0126), "offline_only": True}
    (OUT / "kernel.oriole-touch-0127.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("OFFLINE TOUCH RELINK PASS", manifest)


if __name__ == "__main__":
    main()
