# Pixel 6 touch bring-up

Updated 2026-10-27 PDT. This is a staged hardware investigation, not an installation recipe.

## Known state

- **Observed on Pixel 6:** iOS 16.7.16 reaches the lock screen and, after a timed software Home event, the home screen. A physical upward swipe did not unlock; app taps have not worked. See [the home-screen record](PIXEL6-IOS-HOMESCREEN.md).
- **Read from this repository:** the Oriole iOS payload generator removes `/sweet-touch` and `/sweet-keys` from the Apple device tree. The existing GS101 FTM5 XNU driver only starts if `/sweet-touch` is present. The current iOS image therefore cannot deliver physical touches to SpringBoard.
- **Read from Google device-tree source; ID now observed on this Pixel 6:** Oriole lists an STMicro FTM5 controller on SPI11, with `36 48` as the expected ID. `device/google/oriole/board.json` holds the source-derived pins and coordinates. The ninth Oriole temporary boot below independently read those ID bytes; Bluejay results were not used as a substitute.
- **Observed on Pixel 6, 2026-10-26:** a complete read-only inventory boot (image SHA-256 `adaedfa98ce3b8e09390a00ae1a59214b198b5ea434a1a60869aa2efb603188c`) found USI11 mode `0` rather than SPI mode `2`; all four SPI pads, reset and mux were function `0`. No read faults occurred. See [the sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-inventory-2026-10-26.txt). That initial probe deliberately did not read SPI engine registers in mode `0`; later runs established rail state, chip identity, and one boot-time FIFO response.
- **Observed on Pixel 6, 2026-10-26:** after an Android factory reset, the phone boots to Android initial setup. The earlier iOS HFSX root in `userdata` was erased by that reset. The read-only touch inventory ran from Fastboot and then returned to Android setup; an iOS interaction test will require a separately verified root-image reflash.
- **Observed on Pixel 6, 2026-10-26:** authorized, non-root Android ADB reports a direct multitouch input device named `fts` under `spi11.0`, with X coordinates 0–1079 and Y coordinates 0–2399. See [the sanitized Android record](../research/pixelios-kernel/device/google/oriole/hardware/android-touch-2026-10-26.txt). Android denies reads of the SPI driver link and live device-tree property values; this observation confirms the Android input path, not the bare-metal chip ID or iOS touch.
- **Observed on Pixel 6, 2026-10-26:** the descriptor-only temporary boot returned `ACPM DESC rc=0`, channel 2, queue length 5, element size 16 bytes, with both request and response queues empty at 3/3. It automatically returned to authorized Android ADB. The [sanitized ACPM capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-desc-2026-10-26.txt) records the exact image hash and raw fields. That first capture made no IPC request; rail state was established only by the later rail-read capture below.
- **Observed on Pixel 6, 2026-10-26:** a separately reviewed, hash-pinned ACPM inventory made exactly two bounded PMIC `FUNC_READ` requests. S2MPG10 LDO25M (`0x5C`) returned `0x2C`; LDO26M (`0x5D`) returned `0x3C`. Both replies succeeded, and the phone automatically returned to Android ADB. The [sanitized rail capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-touch-rails-2026-10-26.txt) records the image hash and raw values. **Read from source:** bit 7 enables each rail, so both were disabled at this handoff. Voltage was not directly measured; the later ninth run obtained an SPI response.
- **Observed on Pixel 6, 2026-10-26:** the isolated `--inventory-acpm-rail-cycle` image read both exact off values, enabled LDO25M then LDO26M under mask `0x80`, read back `0xAC` and `0xBC`, then restored them in reverse order and read back `0x3C` and `0x2C`. Every IPC request returned zero. See the [sanitized rail-cycle capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-touch-rail-cycle-2026-10-26.txt). The image had no SPI, XNU, UFS or touch-pad code. The first host report was a parser false negative: ACPM `published=2` means the doorbell was rung, whereas the parser expected 1. The corrected parser accepts the full captured log and still rejects missing or failed steps. This test establishes the power cycle, not chip identity or touch events.
- **Read from this repository:** the GS101 XNU FTM5 driver's `tg_run()` in [patch 0088](../research/pixelios-kernel/xnu/patches/0088-sweet-gs101-touch.patch) configures clocks, pads, SPI and the controller, but has no ACPM or regulator call. The optional `/sweet-touch` ADT node alone therefore cannot power the two rails that were measured off at handoff. An iOS boot profile needs a separately reviewed rail-ownership path that leaves them on while touch is active and restores them on failure or shutdown. The inventory rail-cycle image deliberately restores both rails before reset and cannot serve as that path.
- **Observed on Pixel 6, 2026-10-27:** the ninth isolated touch-ID boot returned `0x36 0x48` from one SPI command. Preparation and cleanup both reported `OK`, and both touch rails read back at their original disabled values. See the [sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-id-success-2026-10-27.txt) and [probe analysis](ORIOLE-TOUCH-ID-PROBE.md).
- **Observed on Pixel 6, 2026-10-27:** a later, separately pinned FIFO profile read `03 00 00 00 00 00 00 00` after the same verified ID exchange. The complete capture reports `OK` cleanup and both rails restored; the phone returned to Android. See [the FIFO capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-fifo-ready-2026-10-27.txt) and [probe analysis](ORIOLE-TOUCH-FIFO-PROBE.md). This is one controller-ready event after reset, not a physical finger event or working iOS input.
- **Observed on Pixel 6, 2026-10-27 (0110 candidate):** temporary boot image SHA-256 `6edd2799fe0517f72deb32ed89698634c646273468900d68d3ea1799801e7db4` reached XNU and its USB network answered. A listener started after boot captured repeated `BSD root: ufsroot0` and `unknown Volume Signature : ea94` / `cannot mount root, errno = 19`. This is consistent with the known Android-formatted userdata after factory reset. The listener missed early touch setup, so this boot does **not** establish whether the XNU FTM5 controller identified successfully. The raw UDP capture stays in ignored `private/touch-xnu-source/relink/touch-0110-udp.log`.

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

**Read from source, 2026-10-27 (candidate, not an input result):** the opt-in
`--xnu-ufsroot-cow-pool512-fbsnap-touchid` build now binds a hash-pinned
identify-only payload to a separate Oriole rail-handoff path. The shim checks
both measured off values, enables LDO25M then LDO26M using the existing
audited ACPM writer, and refuses XNU entry if the check fails. If the loader
returns, it attempts reverse-order restoration and records any failure.
The exact payload passes both the hash checker and the *runtime* UFS-root
bounds guard in a host test. The old no-touch profile remains separate.
**No XNU touch identification, physical finger event, gesture, or app tap has
yet been observed with this candidate.** [Patch 0110](../research/pixelios-kernel/xnu/patches/0110-oriole-touch-feedback-order.patch)
now applies the prekernel-observed USI option and feedback-clock order only
when an Oriole-specific `/sweet-touch` compatible is present. The Oriole
identify payload emits that compatible; other boards retain the old path.
The source was independently reviewed, the local relink produced a pinned
kernel, and `check-all.sh` passed at `821f766+dirty`. The first temporary
boot reached XNU but the receiver missed early touch logging, so a second
capture with the UDP receiver armed *before* `fastboot boot` is required.
The Android factory reset also erased the iOS root in
`userdata`, so an iOS boot needs a freshly verified root image and a new
user confirmation immediately before any flash.

1. **Implementation and device test:** retain the separate rail-handoff and identify-only profiles, verify the XNU SPI reset/feedback-clock ordering against the successful prekernel trace, and test the hash-pinned image on a restored iOS root. Confirm XNU reports chip ID `36 48` and a controller-ready FIFO result before enabling one-finger events. Preserve the current no-touch profile as a fallback.
2. **Observed iOS behavior:** verify physical touch down/up and coordinate scaling in the USB log, then a physical swipe from lock screen to home screen, then tap Settings and return Home. A visible app launch and matching input logs are required before claiming interaction works.

Hardware-writing changes require the repository's independent review and stay on a local `wip/*` branch until it passes. The cycle capture helper, `tools/run_acpm_rail_cycle_inventory.py`, only accepts logs showing both exact on readbacks and both exact off readbacks after reverse restoration; a failed restoration remains an explicit failure. The current Android factory reset erased the earlier iOS root from `userdata`. Temporary inventory boots do not read or write `userdata`.
