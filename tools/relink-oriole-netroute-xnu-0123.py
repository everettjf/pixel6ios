#!/usr/bin/env python3
"""Reproduce and audit the offline 0123 Oriole USB-route kernel and payload.

Outputs stay in ignored private/. This script does not build a phone image,
connect to a phone, or establish that networking works on hardware.
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


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "private/oriole-net-route-base"
SOURCE = ROOT / "private/oriole-net-route-source"
OUT = SOURCE / "relink-0123"
PREVIOUS = ROOT / "private/touch-xnu-source/relink-0122"
BASE_ADT = ROOT / "private/touch-xnu-source/relink-0121/oriole-touch-gui.adt"
BASE_PAYLOAD = PREVIOUS / "oriole-touch-gui-extended-payload.bin"
PATCH = ROOT / "research/pixelios-kernel/xnu/patches/0123-oriole-usb-owned-default-route.patch"
RECIPE = ROOT / "artifacts/fullroot-kernel/sweet_usb.oriole-ro-command.json"
FILES = ("bsd/dev/sweet_usb.c", "bsd/net/route.c", "bsd/net/route_private.h")
PINS = {
    PATCH: "a46a95a9d5ccfaef74b323ed1003d89a7eb6c01c9d636e3d170ae733e4670c4b",
    RECIPE: "523b4cea05fa61732a5f0d0b4565e2bf892b3caba3bb643bdc5ddbc4d0d3575a",
    BASE / FILES[0]: "9793df7f007429dfbb09c14a51161a4da540e94c1774a27c70959b4961e3aabf",
    BASE / FILES[1]: "bb86ba1c72b5634c7eef5b344d6253c18fc50082650c2bc7a05d70691ad656d1",
    BASE / FILES[2]: "d852c23c65b43447ec903d9229026b3d50ea2f05659daceffc97ac302c720280",
    SOURCE / FILES[0]: "4feafdfbb47cb142873ae523f5b87f3db7c203137b96361806b78cc3d47a9b14",
    SOURCE / FILES[1]: "fc5250b9b2bed171fbdfe551aaa8a131e3532bb3165ffd62bc9a370493b1abc5",
    SOURCE / FILES[2]: "7f9a16a310e2592cb38fe290e6c1e8cff37474788f950d1b268591cbe6428160",
    PREVIOUS / "kernel.development.sweet.a": "1e324190ad35a798ae11cd0f00869e60b192486fcd9be43dc53772eb169caa59",
    PREVIOUS / "kernel.oriole-touch-0122": "62c47dd99e2cfd9bf763c0b03c618223ca4deb4d1ab34c24e81a0abea1115d56",
    BASE_ADT: "b85187b0fb3eeec4129c896b508680b27392f2d79ccc24ea95e47e18aa0d4164",
    BASE_PAYLOAD: "6d114538e636421087bf86d634f851d564e9a6626d225cb0c987fff0ff75142d",
}
EXPECTED_SHA256 = "f68406db756901338eedec463cec3bf54c063f56c817c8fb5173398fb89a89ef"
EXPECTED_SIZE = 16713816
EXPECTED_PAYLOAD_SHA256 = "ac57f6084e49200079fc932433bef4bcaeca1da4a9c37cd02555725b8fd00e8f"
EXPECTED_PAYLOAD_SIZE = 16730160
EXPECTED_OBJECT_DELTA = {
    "route.o": {
        "globals_added": {"_rtrequest_add_gateway_on_ifindex", "_rtrequest_delete_if_same"},
        "imports_added": {"_ifnet_index", "_memset", "_printf"},
        "imports_removed": {"___memset_chk"},
    },
    "sweet_usb.o": {
        "globals_added": set(),
        "imports_added": {"_ifnet_index", "_rtfree", "_rtrequest_add_gateway_on_ifindex",
                          "_rtrequest_delete_if_same"},
        "imports_removed": set(),
    },
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_env():
    env = dict(os.environ)
    for key in ("SDKROOT", "DEVELOPER_DIR", "MACOSX_DEPLOYMENT_TARGET", "CPATH",
                "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH",
                "LIBRARY_PATH", "COMPILER_PATH", "GCC_EXEC_PREFIX",
                "IPHONEOS_DEPLOYMENT_TARGET"):
        env.pop(key, None)
    return env


def symbols(path, flag):
    lines = subprocess.check_output(["nm", flag, str(path)], text=True).splitlines()
    return {line.split()[-1] for line in lines}


def check_delta(before, after, expected):
    old_globals, new_globals = symbols(before, "-gU"), symbols(after, "-gU")
    old_imports, new_imports = symbols(before, "-u"), symbols(after, "-u")
    actual = {
        "globals_added": new_globals - old_globals,
        "imports_added": new_imports - old_imports,
        "imports_removed": old_imports - new_imports,
    }
    if actual != expected or old_globals - new_globals:
        raise SystemExit(f"Unexpected {after.name} ABI delta: {actual}")


def check_segments(reference, candidate, m):
    old, old_symbols, old_entry, old_commands = m["macho_info"](reference)
    new, new_symbols, new_entry, new_commands = m["macho_info"](candidate)
    if old_entry != new_entry or old_commands != new_commands or set(old) != set(new):
        raise SystemExit("Entry, commands or segment set changed")
    if m["section"](reference, "__LINKINFO", "__symbolsets") != \
            m["section"](candidate, "__LINKINFO", "__symbolsets"):
        raise SystemExit("Kernel symbolsets changed")
    old_globals = {name for name, (_, public) in old_symbols.items() if public}
    new_globals = {name for name, (_, public) in new_symbols.items() if public}
    if new_globals - old_globals != EXPECTED_OBJECT_DELTA["route.o"]["globals_added"] or \
            old_globals - new_globals:
        raise SystemExit("Unexpected linked global symbol delta")
    if old["__TEXT_EXEC"][0] != new["__TEXT_EXEC"][0] or \
            new["__TEXT_EXEC"][1] - old["__TEXT_EXEC"][1] != 0x4000:
        raise SystemExit("Unexpected executable text growth")
    for name in old:
        a, b = old[name], new[name]
        if a[4:] != b[4:] or b[3] > b[1]:
            raise SystemExit("Segment protection or file size changed: " + name)
        if name in ("__TEXT", "__DATA_CONST") and a != b:
            raise SystemExit("Early segment changed: " + name)
        if name not in ("__TEXT", "__DATA_CONST", "__TEXT_EXEC") and \
                (b[0] - a[0], b[2] - a[2]) != (0x4000, 0x4000):
            raise SystemExit("Unexpected downstream segment shift: " + name)
    for label, segments, size in (("reference", old, len(reference)),
                                  ("candidate", new, len(candidate))):
        spans = sorted((segment[0], segment[0] + segment[1], name)
                       for name, segment in segments.items())
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            raise SystemExit(label + " VA segments overlap")
        file_spans = sorted((segment[2], segment[2] + segment[3], name)
                            for name, segment in segments.items())
        if file_spans[0][0] != 0 or any(left[1] > right[0]
                                       for left, right in zip(file_spans, file_spans[1:])) or \
                file_spans[-1][1] != size:
            raise SystemExit(label + " file segments overlap or do not cover EOF")


def build_payload(kernel):
    profile = runpy.run_path(str(ROOT / "research/pixelios-kernel/tools/oriole_touch_gui_0123.py"))
    profile["check"](BASE_PAYLOAD.read_bytes())
    args = profile["ARGS"]
    if "sweetnetroute" in args or len((args + " sweetnetroute=1").encode()) >= 608:
        raise SystemExit("Unexpected or oversized network boot arguments")
    mkpayload = runpy.run_path(str(ROOT / "research/pixelios-kernel/tools/mkpayload.py"))
    blob, _ = mkpayload["build"](kernel, BASE_ADT, args + " sweetnetroute=1", board="bluejay")
    payload = OUT / "oriole-net-route-0123.payload.bin"
    payload.write_bytes(blob)
    if len(blob) != EXPECTED_PAYLOAD_SIZE or sha(payload) != EXPECTED_PAYLOAD_SHA256:
        raise SystemExit("Payload bytes differ from the audited offline candidate")
    print("OFFLINE PAYLOAD PASS", sha(payload), "(no device validation)")


def main():
    m = runpy.run_path(str(ROOT / "tools/relink-oriole-cow-xnu.py"))
    policy = m["verify_inputs"]()
    for path, expected in PINS.items():
        if sha(path) != expected:
            raise SystemExit("Unreviewed input: " + str(path))
    with tempfile.TemporaryDirectory() as path:
        tree = Path(path)
        for name in FILES:
            file = tree / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes((BASE / name).read_bytes())
        subprocess.run([policy["tools"]["git"]["path"], "apply", str(PATCH)],
                       cwd=tree, check=True)
        for name in FILES:
            if (tree / name).read_bytes() != (SOURCE / name).read_bytes():
                raise SystemExit("Patch reconstruction mismatch: " + name)

    OUT.mkdir(parents=True, exist_ok=True)
    recipe = json.loads(RECIPE.read_text())
    if not isinstance(recipe, list) or any(recipe.count(flag) != 1
                                           for flag in ("-c", "-o", "-MF")):
        raise SystemExit("Unexpected compiler recipe")
    archive = OUT / "kernel.development.sweet.a"
    shutil.copyfile(PREVIOUS / archive.name, archive)
    ar = policy["tools"]["ar"]["path"]
    members = subprocess.check_output([ar, "-t", str(archive)], text=True).splitlines()
    for member, source in (("route.o", SOURCE / FILES[1]),
                           ("sweet_usb.o", SOURCE / FILES[0])):
        if members.count(member) != 1:
            raise SystemExit("Archive member missing or duplicated: " + member)
        original = OUT / (member + ".original")
        original.write_bytes(subprocess.check_output([ar, "-p", str(archive), member]))
        command = recipe.copy()
        command[command.index("-c") + 1] = str(source)
        command[command.index("-o") + 1] = str(OUT / member)
        command[command.index("-MF") + 1] = str(OUT / (member + ".d"))
        command[41:41] = ["-I", str(SOURCE / "bsd")]
        if member == "route.o":
            command += ["-DNECP=1", "-DMACH_ASSERT=1"]
        with (OUT / (member + ".warnings")).open("w") as warnings:
            subprocess.run(command, cwd=ROOT / "research/xnu-8796-reference",
                           env=clean_env(), check=True, stdout=subprocess.DEVNULL,
                           stderr=warnings)
        check_delta(original, OUT / member, EXPECTED_OBJECT_DELTA[member])
        subprocess.run([ar, "-r", str(archive), str(OUT / member)], check=True)
        if subprocess.check_output([ar, "-p", str(archive), member]) != (OUT / member).read_bytes():
            raise SystemExit("Archive replacement failed: " + member)

    reference = (PREVIOUS / "kernel.oriole-touch-0122").read_bytes()
    link, support = m["LINK"], m["SUPPORT"]
    symbolsets = OUT / "reference-symbolsets.plist"
    symbolsets.write_bytes(m["section"](reference, "__LINKINFO", "__symbolsets"))
    flags = shlex.split((link / "kernel.development.sweet.linkarguments").read_text())
    flags = [flag for flag in flags if not flag.startswith("-L/Users/runner") and flag not in
             ("-lfirehose_kernel", "-lcc_kext", "-Wl,-new_linker",
              "-Wl,-rename_segment,__LASTDATA_CONST,__LAST")]
    output = OUT / "kernel.oriole-net-route-0123.pending"
    cmd = [policy["tools"]["clang"]["path"],
           "-fuse-ld=" + policy["tools"]["ld64"]["path"]] + flags
    cmd += ["-Wl,-force_load," + str(archive), str(support / "firehose_buffer.o"),
            str(support / "profile16/nonlto.o"), str(support / "profile16/chkstk_darwin.S.o"),
            str(support / "profile16/libkernel-profile16.a"),
            "-Wl,-alias_list," + str(link / "kernel.development.sweet.alias.exp"),
            "-Wl,-sectcreate,__LINKINFO,__symbolsets," + str(symbolsets),
            "-Wl,-segprot,__LINKINFO,r--,r--", "-o", str(output)]
    subprocess.run(cmd, check=True, env=clean_env())
    subprocess.run([policy["tools"]["strip"]["path"], "-S", str(output)],
                   check=True, env=clean_env())
    candidate = m["pin_reference_uuid"](reference, output.read_bytes())
    output.write_bytes(candidate)
    check_segments(reference, candidate, m)
    if len(candidate) != EXPECTED_SIZE or sha(output) != EXPECTED_SHA256:
        raise SystemExit("Relink bytes differ from the reviewed offline candidate")
    print("OFFLINE RELINK PASS", sha(output), "(no device validation)")
    build_payload(output)


if __name__ == "__main__":
    main()
