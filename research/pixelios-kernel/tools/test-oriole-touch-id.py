#!/usr/bin/env python3
"""Pin the one-shot Oriole SPI writer before it can enter a boot image."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

SHIM = Path(__file__).resolve().parents[1] / "shim"
PINS = {
    "orioletouchid_hw.c": "dc53a66f0441561cf7b045c03a649bf57256bf46ec8e641c5e0afad5b8196fba",
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
    check_symbols(hw, flow, image)
    check_disasm(disasm)
    bad = dict(texts)
    bad["orioletouchid_hw.c"] = bad["orioletouchid_hw.c"].replace("0x20u", "0x21u", 1)
    expect_reject(check_pins, bad)
    expect_reject(check_symbols, hw + "\n00000000 T extra_writer", flow, image)
    expect_reject(check_disasm, disasm + "\n0000000000002000 <evil>:\n"
                  "  2000: R_AARCH64_CALL26 try_write32\n")
    print("PASS Oriole touch-ID source, object, image and mutation audits")


if __name__ == "__main__":
    main()
