#!/usr/bin/env python3
"""Pin the one-shot Oriole SPI writer before it can enter a boot image."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess

SHIM = Path(__file__).resolve().parents[1] / "shim"
PINS = {
    "orioletouchid_hw.c": "b1029b50035eedcb5707f0b1162ca6041678cc461f94285aeed599ee9bce90fb",
    "orioletouchid_flow.c": "ebf428bc6b25217bb0954a87bdae25e700c35d39b9e6c3f1945d23841edadd15",
}
HW_U = frozenset(("acpm_cfg_init", "acpm_describe", "acpm_oriole_touch_rail_set",
                  "acpm_pmic_read", "con_hex2", "con_str", "counter_freq",
                  "fdt_memory_contains", "fdt_root_compatible", "oti_run", "touch_ticks",
                  "try_read32", "try_write32"))


def check_pins(texts):
    for name, pinned in PINS.items():
        if hashlib.sha256(texts[name].encode()).hexdigest() != pinned:
            raise AssertionError(f"{name} changed: independently review write sequence and repin")
    hw = texts["orioletouchid_hw.c"]
    flow = texts["orioletouchid_flow.c"]
    ordered = ("fdt_root_compatible(h->dtb", "fdt_memory_contains(h->dtb",
               "acpm_describe(&h->acpm", "static int shared_snapshot",
               "static int engine_snapshot", "static int spi_prepare", "static int spi_identify",
               "static int engine_restore", "static int shared_restore")
    if any(hw.count(word) != 1 for word in ordered):
        raise AssertionError("touch-ID safety gate or phase count drifted")
    if flow.count("o->rail_set(ctx, OTI_LDO25M, 1") != 1 or \
       flow.count("o->rail_set(ctx, OTI_LDO26M, 1") != 1 or \
       flow.count("o->rail_set(ctx, OTI_LDO26M, 0") != 1 or \
       flow.count("o->rail_set(ctx, OTI_LDO25M, 0") != 1:
        raise AssertionError("touch-ID rail sequence drifted")


def symbols(raw):
    defined, undefined = set(), set()
    for line in raw.splitlines():
        m = re.fullmatch(r"(?:[0-9a-fA-F]+\s+)?([A-Za-z])\s+([\w.]+)", line.strip())
        if not m:
            continue
        kind, name = m.groups()
        if kind == "U":
            undefined.add(name)
        elif kind.isupper():
            defined.add(name)
    return frozenset(defined), frozenset(undefined)


def check_symbols(hw, flow, image):
    if symbols(hw) != (frozenset(("oriole_touch_id_run",)), HW_U):
        raise AssertionError("touch-ID hardware object symbol surface drifted")
    if symbols(flow) != (frozenset(("oti_run",)), frozenset()):
        raise AssertionError("touch-ID flow object symbol surface drifted")
    image_names = symbols(image)[0]
    if "oriole_touch_id_run" not in image_names or \
       "touch_probe_run" in image_names or "acpm_rail_cycle_run" in image_names:
        raise AssertionError("touch-ID image includes an unrelated touch or rail writer")


def check_disasm(raw):
    current = ""
    sites = []
    for line in raw.splitlines():
        m = re.match(r"^[0-9a-fA-F]+ <([^>]+)>:$", line)
        if m:
            current = m.group(1)
        if "R_AARCH64_CALL26" in line and "try_write32" in line:
            sites.append(current)
        if "R_AARCH64_ABS64" in line:
            raise AssertionError("absolute pointer relocation in touch-ID object")
    if sites != ["guarded_write"]:
        raise AssertionError(f"try_write32 callers drifted: {sites}")


def check_stores(raw, sections, names):
    """Prove every store stays on stack/argument data, including the gate."""
    spec = importlib.util.spec_from_file_location(
        "bluejay_audit", Path(__file__).with_name("test-bluejay-boot.py"))
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    return audit.check_usb_object_text(
        raw, names, set(HW_U), sections, "orioletouchid_hw.o",
        allowed_undef=set(HW_U), trusted_args=frozenset(f"x{i}" for i in range(8)),
        allow_adrp=False, require_clean_data=True)


def expect_reject(fn, *args):
    try:
        fn(*args)
    except AssertionError:
        return
    raise AssertionError("touch-ID audit mutation escaped")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("nm", "objdump", "hw", "flow", "image"):
        ap.add_argument("--" + name, required=True)
    a = ap.parse_args()
    texts = {name: (SHIM / name).read_text() for name in PINS}
    check_pins(texts)
    hw = subprocess.check_output([a.nm, "-g", a.hw], text=True)
    flow = subprocess.check_output([a.nm, "-g", a.flow], text=True)
    image = subprocess.check_output([a.nm, "-g", a.image], text=True)
    disasm = subprocess.check_output([a.objdump, "-dr", a.hw], text=True)
    sections = subprocess.check_output([a.objdump, "-h", a.hw], text=True)
    local_names = {parts[2] for line in subprocess.check_output([a.nm, a.hw], text=True).splitlines()
                   if len(parts := line.split()) == 3 and parts[1] in ("t", "T")}
    check_symbols(hw, flow, image)
    check_disasm(disasm)
    stores = check_stores(disasm, sections, local_names)
    bad = dict(texts)
    bad["orioletouchid_hw.c"] = bad["orioletouchid_hw.c"].replace("0x20u", "0x21u", 1)
    expect_reject(check_pins, bad)
    expect_reject(check_symbols, hw + "\n00000000 T extra_writer", flow, image)
    expect_reject(check_disasm, disasm + "\n0000000000002000 <evil>:\n"
                  "  2000: R_AARCH64_CALL26 try_write32\n")
    bad_store = ("\n0000000000ffff00 <evil>:\n"
                 "  ffff00:\td2a22229 \tmovz\tx9, #0x1111, lsl #16\n"
                 "  ffff04:\tb9000120 \tstr\tw0, [x9]\n"
                 "  ffff08:\td65f03c0 \tret\n")
    expect_reject(check_stores, disasm + bad_store, sections, local_names | {"evil"})
    bad_branch = ("\n0000000000ffff00 <evil>:\n"
                  "  ffff00:\tb4000040 \tcbz\tx0, ffff08 <evil+0x8>\n"
                  "  ffff04:\td2a22229 \tmovz\tx9, #0x1111, lsl #16\n"
                  "  ffff08:\tb9000120 \tstr\tw0, [x9]\n"
                  "  ffff0c:\td65f03c0 \tret\n")
    expect_reject(check_stores, disasm + bad_branch, sections, local_names | {"evil"})
    print(f"PASS Oriole touch-ID source, object ({stores} checked stores), image and mutation audits")


if __name__ == "__main__":
    main()
