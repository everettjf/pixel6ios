# Pixel 6 touch bring-up

Updated 2026-10-26 PDT. This is a staged hardware investigation, not an installation recipe.

## Known state

- **Observed on Pixel 6:** iOS 16.7.16 reaches the lock screen and, after a timed software Home event, the home screen. A physical upward swipe did not unlock; app taps have not worked. See [the home-screen record](PIXEL6-IOS-HOMESCREEN.md).
- **Read from this repository:** the Oriole iOS payload generator removes `/sweet-touch` and `/sweet-keys` from the Apple device tree. The existing GS101 FTM5 XNU driver only starts if `/sweet-touch` is present. The current iOS image therefore cannot deliver physical touches to SpringBoard.
- **Read from Google device-tree source, unverified on this Pixel 6:** Oriole lists an STMicro FTM5 controller on SPI11, with `36 48` as the expected ID. `device/google/oriole/board.json` holds the source-derived pins and coordinates. Bluejay probe results do not establish Oriole rail or pin state.
- **Observed on Pixel 6, 2026-10-26:** a complete read-only inventory boot (image SHA-256 `adaedfa98ce3b8e09390a00ae1a59214b198b5ea434a1a60869aa2efb603188c`) found USI11 mode `0` rather than SPI mode `2`; all four SPI pads, reset and mux were function `0`. No read faults occurred. See [the sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-inventory-2026-10-26.txt). The probe deliberately did not read SPI engine registers in mode `0`. Controller identity, rails and event FIFO remain unknown.
- **Observed on Pixel 6, 2026-10-26:** after an Android factory reset, the phone boots to Android initial setup. The earlier iOS HFSX root in `userdata` was erased by that reset. The read-only touch inventory ran from Fastboot and then returned to Android setup; an iOS interaction test will require a separately verified root-image reflash.
- **Observed on Pixel 6, 2026-10-26:** authorized, non-root Android ADB reports a direct multitouch input device named `fts` under `spi11.0`, with X coordinates 0–1079 and Y coordinates 0–2399. See [the sanitized Android record](../research/pixelios-kernel/device/google/oriole/hardware/android-touch-2026-10-26.txt). Android denies reads of the SPI driver link and live device-tree property values; this observation confirms the Android input path, not the bare-metal chip ID or iOS touch.

## Safe first measurement

The Oriole inventory image accepts `--touch-probe` with **no options**. It runs the existing phase-1 `touch_probe_dump()` inside the already bounded inventory path, after live FDT and RAM checks. That function reads CMU, USI mode and GPIO pad registers; it reads SPI registers only when the USI mode is already SPI. The Oriole inventory guard rejects `--touch-probe=run`, `railsr`, `rails`, a payload, and other peripheral experiments. This change does not add a touch node to the iOS image.

```sh
cd research/pixelios-kernel
tools/check-all.sh                  # must print GATE PASS
shim/build.sh --board oriole --avb --usb-gadget --inventory --touch-probe
```

`check-all.sh` overwrites `shim/out/`, so build the probe again afterwards. Before a temporary `fastboot boot`, verify that exactly one attached device reports `product: oriole`, the bootloader is unlocked, and the image hash matches the freshly built probe. Capture the USB/RAM log and record the CMU, USI mode, seven pad values and any read faults. This phase does not read or write storage and does not modify partitions. The 2026-10-26 result above is from one such complete capture; it establishes the handoff state, not working touch.

After capture, run `python3 tools/report_touch_inventory.py private/<capture>.log --out private/touch-inventory.json` from the root checkout. The report keeps the raw touch lines and flags missing fields or read faults; `complete` means the log contains one whole read-only dump, **not** that the controller is identified or touch works. A truncated capture exits nonzero and must be repeated. Keep the raw log and report private until device identifiers have been reviewed.

The root-level `tools/boot_inventory.py --touch` helper requires the image's touch marker, a separate `inventory-touch` entry **and the exact SHA-256 image hash** in the private firmware baseline (`inventory_touch_image_sha256`). A generic `inventory` allowance or a linked marker alone cannot authorize the profile. The helper refuses firmware or slot drift and boots only the recorded serial. Add the mode and hash to a host's private baseline only after reviewing the exact built image; the helper checks phone identity again before temporary boot.

On macOS, `tools/run_touch_inventory.py --seconds 180` arms the CDC-ACM log receiver first, invokes that verified `--touch` boot helper, then runs the completeness report. It requires exactly the recorded serial in fastboot, no other connected inventory gadget, and `pyserial==3.5` in `private/gate-venv` (install locally with `uv pip install --python private/gate-venv/bin/python 'pyserial==3.5'`). It refuses to start when the phone remains in Android Recovery. Capture output stays under `private/touch-inventory/`; inspect the generated `capture.txt`, `usb.log` and `report.json` before drawing any hardware conclusion.

## Next gates

1. **Next measurement:** compare the new USI11/pad handoff state with the Oriole device tree and known Bluejay baseline. Android has now confirmed `fts` input under SPI11 on this phone, and `/proc/interrupts` names the `gpa9` line `fts` (*observed on hardware*, 2026-10-26). The new `--inventory-acpm-desc` profile is **built but not yet run on hardware**: it prints the ACPM SRAM channel descriptor and queue indices without sending an IPC request. Its separately compiled `acpm_desc.o` must have only `try_read32` as an undefined hardware accessor; the ordinary `acpm.o` remains available for the existing writer audit and is not linked into this profile. It does not read the touch rail registers; even an ACPM PMIC *read* requires writing a request into SRAM and ringing a mailbox doorbell. The root-level boot helper now requires an explicit `--acpm-desc`, an `inventory-acpm-desc` allowance and `inventory_acpm_desc_image_sha256` in the private firmware baseline. That allowance and pin remain unset. Run this profile only after reviewing and pinning the exact freshly built image, while someone can recover a hung phone. The current Android installation stays intact until then.
2. **Observed hardware:** identify `36 48` on this Pixel 6 with a bounded, reviewed SPI/clock/reset probe. The existing `touchprobe.c` has these writer paths, but Oriole still forbids them; do not bypass the inventory guard or assume the Bluejay sequence is safe here.
3. **Implementation:** only after a successful chip-ID and event-FIFO measurement, add an Oriole touch ADT node and a separate iOS boot profile. Preserve the existing no-touch profile as a fallback. Start with identify-only mode, then one-finger events.
4. **Observed iOS behavior:** verify touch down/up and coordinate scaling in the USB log, then a physical swipe from lock screen to home screen, then tap Settings and return Home. A visible app launch and matching input logs are required before claiming interaction works.

Hardware-writing changes require the repository's independent review and stay on a local `wip/*` branch until it passes. The iOS root on `userdata` remains read-only at the UFS layer during these temporary boots; the RAM COW layer handles runtime writes.
