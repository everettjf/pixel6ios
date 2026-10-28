# Pixel 6 touch bring-up

Updated 2026-10-27 PDT. This is a staged hardware investigation, not an installation recipe.

## Known state

- **Observed on Pixel 6:** iOS 16.7.16 reaches the lock screen and, after a timed software Home event, the home screen. A physical upward swipe did not unlock; app taps have not worked. See [the home-screen record](PIXEL6-IOS-HOMESCREEN.md).
- **Read from this repository:** the Oriole iOS payload generator removes `/sweet-touch` and `/sweet-keys` from the Apple device tree. The existing GS101 FTM5 XNU driver only starts if `/sweet-touch` is present. The current iOS image therefore cannot deliver physical touches to SpringBoard.
- **Read from Google device-tree source; ID now observed on this Pixel 6:** Oriole lists an STMicro FTM5 controller on SPI11, with `36 48` as the expected ID. `device/google/oriole/board.json` holds the source-derived pins and coordinates. The ninth Oriole temporary boot below independently read those ID bytes; Bluejay results were not used as a substitute.
- **Observed on Pixel 6, 2026-10-26:** a complete read-only inventory boot (image SHA-256 `adaedfa98ce3b8e09390a00ae1a59214b198b5ea434a1a60869aa2efb603188c`) found USI11 mode `0` rather than SPI mode `2`; all four SPI pads, reset and mux were function `0`. No read faults occurred. See [the sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-inventory-2026-10-26.txt). That initial probe deliberately did not read SPI engine registers in mode `0`; later runs established rail state, chip identity, and one boot-time FIFO response.
- **Observed on Pixel 6, 2026-10-26:** after an Android factory reset, the phone boots to Android initial setup. The earlier iOS HFSX root in `userdata` was erased by that reset. The read-only touch inventory ran from Fastboot and then returned to Android setup; an iOS interaction test will require a separately verified root-image reflash.
- **Observed on Pixel 6, 2026-10-27 (0118 synchronized run):** the 60-second XNU scan received real FTM5 `0x13` down, `0x23` move and `0x33` up records while the user touched the screen. Its HID path logged 277 down and 277 up reports, including coordinates and a second contact ID. No FIFO-read failure occurred; both touch rails were restored after the timer. The [0118 capture record](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-irq-sample-2026-10-27.txt) distinguishes this run from an earlier no-touch baseline. This proves physical events at the kernel/HID driver, but the diagnostic boot still had Android-formatted `userdata`; it did not test a gesture or app tap in iOS.
- **Observed on Pixel 6, 2026-10-26:** authorized, non-root Android ADB reports a direct multitouch input device named `fts` under `spi11.0`, with X coordinates 0–1079 and Y coordinates 0–2399. See [the sanitized Android record](../research/pixelios-kernel/device/google/oriole/hardware/android-touch-2026-10-26.txt). Android denies reads of the SPI driver link and live device-tree property values; this observation confirms the Android input path, not the bare-metal chip ID or iOS touch.
- **Observed on Pixel 6, 2026-10-26:** the descriptor-only temporary boot returned `ACPM DESC rc=0`, channel 2, queue length 5, element size 16 bytes, with both request and response queues empty at 3/3. It automatically returned to authorized Android ADB. The [sanitized ACPM capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-desc-2026-10-26.txt) records the exact image hash and raw fields. That first capture made no IPC request; rail state was established only by the later rail-read capture below.
- **Observed on Pixel 6, 2026-10-26:** a separately reviewed, hash-pinned ACPM inventory made exactly two bounded PMIC `FUNC_READ` requests. S2MPG10 LDO25M (`0x5C`) returned `0x2C`; LDO26M (`0x5D`) returned `0x3C`. Both replies succeeded, and the phone automatically returned to Android ADB. The [sanitized rail capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-touch-rails-2026-10-26.txt) records the image hash and raw values. **Read from source:** bit 7 enables each rail, so both were disabled at this handoff. Voltage was not directly measured; the later ninth run obtained an SPI response.
- **Observed on Pixel 6, 2026-10-26:** the isolated `--inventory-acpm-rail-cycle` image read both exact off values, enabled LDO25M then LDO26M under mask `0x80`, read back `0xAC` and `0xBC`, then restored them in reverse order and read back `0x3C` and `0x2C`. Every IPC request returned zero. See the [sanitized rail-cycle capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-touch-rail-cycle-2026-10-26.txt). The image had no SPI, XNU, UFS or touch-pad code. The first host report was a parser false negative: ACPM `published=2` means the doorbell was rung, whereas the parser expected 1. The corrected parser accepts the full captured log and still rejects missing or failed steps. This test establishes the power cycle, not chip identity or touch events.
- **Read from this repository:** the GS101 XNU FTM5 driver's `tg_run()` in [patch 0088](../research/pixelios-kernel/xnu/patches/0088-sweet-gs101-touch.patch) configures clocks, pads, SPI and the controller, but has no ACPM or regulator call. The optional `/sweet-touch` ADT node alone therefore cannot power the two rails that were measured off at handoff. An iOS boot profile needs a separately reviewed rail-ownership path that leaves them on while touch is active and restores them on failure or shutdown. The inventory rail-cycle image deliberately restores both rails before reset and cannot serve as that path.
- **Observed on Pixel 6, 2026-10-27:** the ninth isolated touch-ID boot returned `0x36 0x48` from one SPI command. Preparation and cleanup both reported `OK`, and both touch rails read back at their original disabled values. See the [sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-id-success-2026-10-27.txt) and [probe analysis](ORIOLE-TOUCH-ID-PROBE.md).
- **Observed on Pixel 6, 2026-10-27:** a later, separately pinned FIFO profile read `03 00 00 00 00 00 00 00` after the same verified ID exchange. The complete capture reports `OK` cleanup and both rails restored; the phone returned to Android. See [the FIFO capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-fifo-ready-2026-10-27.txt) and [probe analysis](ORIOLE-TOUCH-FIFO-PROBE.md). This is one controller-ready event after reset, not a physical finger event or working iOS input.
- **Observed on Pixel 6, 2026-10-27 (0110 candidate):** temporary boot image SHA-256 `6edd2799fe0517f72deb32ed89698634c646273468900d68d3ea1799801e7db4` reached XNU and its USB network answered. A listener started after boot captured repeated `BSD root: ufsroot0` and `unknown Volume Signature : ea94` / `cannot mount root, errno = 19`. This is consistent with the known Android-formatted userdata after factory reset. The listener missed early touch setup, so this boot does **not** establish whether the XNU FTM5 controller identified successfully. The raw UDP capture stays in ignored `private/touch-xnu-source/relink/touch-0110-udp.log`.
- **Observed on Pixel 6, 2026-10-27 (0110 repeat):** a second `fastboot boot` of that same hash-pinned image, with UDP reception armed first, captured the XNU touch phase. `/sweet-touch` started, USI11 entered SPI mode 2, `USI_OPTION=1` and `SPI_FB_CLK=1` read back. The reset/ready poll saw no ready event in 1.5 seconds, and the chip-ID read returned `00 00 00 00` instead of `36 48`; the driver stopped at identify-only phase 1. This is a real XNU communication failure, not evidence of working touch. The log cannot distinguish rail loss after shim handoff, reset sequencing, bus ownership or SPI timing. The full private capture is `private/touch-xnu-source/relink/touch-0110-repeat-udp.log`; [selected non-identifying lines](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-identify-failure-2026-10-27.txt) are tracked for review. `userdata` is still Android formatted, so this run cannot test iOS interaction.
- **Observed on Pixel 6, 2026-10-27 (0111 reset settle):** a temporary boot of commit `644a1fb` (image SHA-256 `1be8fc04e31de089a6b4f87f3c1dd2ade87c554ef24ae27ec4d0c1b015c1facd`) executed the additional 100 ms wait after reset release and read back reset GPIO as output/high. It still saw no controller-ready event and read ID `00 00`, then stopped before enabling scan. See the [sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-reset-settle-failure-2026-10-27.txt). The touch-rail state at XNU identify time was not measured, so this does not isolate the failure to SPI or power.

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

**Read from source, 2026-10-27:** the opt-in
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
kernel, and `check-all.sh` passed at `821f766+dirty`. The second temporary
boot captured the early XNU touch phase and established that this candidate
does **not** identify the controller. Patch 0111 added the successful
prekernel probe's 100 ms reset-release wait and an output/high GPIO readback.
Its exact payload and boot image passed the local gate at `a615eb8+dirty`,
but the temporary boot again read `00 00`. Compare the remaining clock, pad,
rail and SPI transaction sequence with the successful isolated prekernel
probe. In particular, measure whether the two touch rails remain enabled at
the XNU identify point before attributing `00 00` to a software SPI difference.
**Read from source, 2026-10-27:** the isolated probe
issues the ID command before its first FIFO read, whereas patches through
0111 poll FIFO for a ready event before identifying. Patch 0112 changes only
the Oriole identify path to pulse and settle reset, then issue ID first.
The identify-only profile still cannot enable scanning. Its local quality
gate passed at `778970c+dirty`; the exact temporary-boot image SHA-256 is
`c6ce44d277ad39bb7bed92dacca6ac00eb1e2296681baebe9539eea27e325f3c`.
**Observed on Pixel 6, 2026-10-27 (0112):** one temporary boot of that exact
image reached the intended reset-settle then ID-before-FIFO path. XNU still
read `00 00 00 00` instead of `36 48` and stopped before scan. See the
[sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-idfirst-failure-2026-10-27.txt).
This excludes FIFO-before-ID as the sole cause. It establishes no iOS touch,
gesture or app interaction.

**Observed on Pixel 6, 2026-10-27 (0113):**
[patch 0113](../research/pixelios-kernel/xnu/patches/0113-oriole-touch-id-mismatch-readback.patch)
adds a CMU, SPI and pad snapshot only after a completed but unmatched Oriole
chip-ID read. The first ID transaction therefore retains the 0112 ordering
and timing. A different model family independently reviewed the source and
the pinned local build profile. The kernel SHA-256 is
`075e96ae749269b0b067ca0cdf78f0f8146d0427813640adf6657438ddf0026a`;
the payload SHA-256 is
`006a69f04e03482b025e10ec41ec638d669d2f1bde4b5c03f7dcb1422183047d`.
The [sanitized hardware capture](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-idreadback-failure-2026-10-27.txt)
records the exact boot-image hash and USB log. The ID remained `00 00`; the
post-ID CMU mux was `0`, the divider was `5` with BUSY clear, reset read high,
and the AP/AOC mux read low. This excludes a still-busy divider at that
snapshot as the direct explanation. The XNU-time PMIC rail state remains
unmeasured. No physical touch, gesture or app interaction was observed.

**Observed on Pixel 6, 2026-10-27 (0114):**
[patch 0114](../research/pixelios-kernel/xnu/patches/0114-oriole-touch-acpm-snapshot.patch)
adds a bounded, read-only snapshot of the ACPM channel-2 descriptor and four
queue indices after an Oriole chip-ID mismatch. It checks the mapped SRAM
window and requires the descriptor's queue-pointer offsets to match the
2026-10-26 measured values before reading those indices. It sends no ACPM
request, writes no PMIC register and does **not** reveal whether LDO25M or
LDO26M is enabled. A different model family reviewed the mapping and bounds.
The local kernel SHA-256 is
`69f0919a63fd098bbdd4188390608c3490c067dbbf66613095b49347030f20aa`,
the payload SHA-256 is
`dd31877a7892baf6d4ee20540da2e1ebc15a3916b78d8f08915fb004c2446857`.
The exact temporary boot image SHA-256 is
`c09395f5e70da3e9e9c7dd93dc9d09dc7b1b2d57d0925fe710e316c82d6911c8`.
The [sanitized hardware capture](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-acpm-snapshot-2026-10-27.txt)
shows the ID still read `00 00 00 00`, while channel 2 was type 1 with five
16-byte entries and both request and response queues empty (`3/3`). This
confirms the descriptor and queue layout at the XNU identify point. It does
not measure the PMIC rails or prove that the APM responds to a new request.

**Read from source and the 0111 hardware capture, 2026-10-27:** the isolated
prekernel ID probe waits for the CMU mux and divider BUSY bit to clear after
each clock write (`shim/orioletouchid_hw.c:392-393`). The XNU experiment's
`sweettouchpoke` logs the immediate divider readback without that poll; its
0111 capture shows `0x10005`, including the transient BUSY bit. XNU then
spends at least 110 ms on the reset pulse and release settle before ID, so
this immediate readback **does not prove** the clock was still busy at the
transaction. Keep 0112 unchanged for its first hardware test. If it still
returns `00 00`, capture the CMU mux/divider state at the ID point and both
touch-rail readbacks before changing another clock or power writer.

**Observed on Pixel 6 Android, 2026-10-26 and repeated 2026-10-27:** read-only
`getevent -lp` showed an `fts` direct touchscreen with 10 slots and X/Y
ranges `0..1079` / `0..2399`. These match the current XNU driver's contact
count and raw coordinate range. See the [sanitized input inventory](../research/pixelios-kernel/device/google/oriole/hardware/android-touch-2026-10-26.txt).
This does not establish that XNU receives any touch event.

**Observed on Pixel 6, 2026-10-27 (0115):**
[patch 0115](../research/pixelios-kernel/xnu/patches/0115-oriole-touch-pmic-rail-read.patch)
adds one bounded ACPM channel-2 attempt after a failed Oriole ID read. It
checks the exact observed descriptor, empty queues and pointer offsets, then
requests the S2MPG10 LDO25M and LDO26M register values (`0x5c` and `0x5d`).
These are PMIC reads; the request publishes into shared SRAM and rings the
mailbox but does not issue a PMIC register write. A persistent atomic latch
prevents retries in the same boot, including after an uncertain timeout.
A different model family reviewed the revised patch. The pinned local kernel
SHA-256 is
`0e4e24b3ff98fa0f4ef6a813b98043de83c13564b1dba1ab408901daae6fb52e`;
the payload SHA-256 is
`6348489fad23c85f17c4123c5b3eca4069de1e2dd41564621ce58a49537b412a`.
The host build and payload guard passed. The first boot attempt used an
unwrapped 17 MB image and remained in Fastboot; the successful attempt used
the same payload in a 64 MB AVB-wrapped image, SHA-256
`a6e3013daf3fe848e3680dbbb474a2f2299b28b2cdc79fe0b3b1025dc3292caa`.
The [sanitized hardware capture](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-rail-read-2026-10-27.txt)
shows two successful PMIC reads at the failed XNU ID point: LDO25M `0x2c`
and LDO26M `0x3c`, both with enable bit 7 clear. The XNU-time rails are
therefore off at that moment. The prekernel rail-hold source requires on
readbacks before handing off to XNU, but its earlier screen output was not
captured in this USB log; where the state changed remains unmeasured.
The next gate is a reviewed handoff that measures or enables them at the
XNU touch init point, verifies on readbacks, and restores them on any failed
ID or later touch initialization. Do not change the SPI transaction first.

**Observed on Pixel 6, 2026-10-27 (0116):**
[patch 0116](../research/pixelios-kernel/xnu/patches/0116-oriole-touch-rail-cycle-id.patch)
adds an Oriole-only `sweettouchrailcycle=1` identify experiment. It requires
mode 1, the measured ACPM channel-2 descriptor, empty queues, exact initial
LDO25M/LDO26M off values (`0x2c`/`0x3c`), and the ABL-style reset path. It
enables LDO25M then LDO26M, verifies `0xac`/`0xbc`, performs at most one chip
ID attempt, and tries to restore LDO26M then LDO25M with off readbacks. A
published ACPM request with a missing or invalid reply poisons the client and
stops further writes; in that case **one or both rails may remain enabled
until reboot**. The image uses a 180-second auto-restart for this reason.
The candidate XNU SHA-256 is
`d21a69b6481bcdd4cb2e23556b9407ff3eebd456cf7d85e91dced3b854f44774`,
payload SHA-256 is
`0ccaac530588a86864258d00c35cf7e6aaf8964a4d1ba2d8eaa481027bdfc4a2`,
and AVB-wrapped boot-image SHA-256 is
`d4ee1fc635d7bb7c36907be417cd1148ace59f465914b76bafb8c72e1844b5e7`.
An independent different-model-family review found no remaining concrete
hardware-write blocker. The local relink preserves the prior loaded segment
addresses and permits only an exact private-symbol delta. The temporary
`fastboot boot` produced [sanitized hardware evidence](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-rail-cycle-id-2026-10-27.txt):
both rails read back on (`0xac`, `0xbc`), FTM5 returned `36 48 03 00` for the
chip ID, and both rails read back off after reverse-order restoration (`0x3c`,
`0x2c`). This proves XNU can communicate with the touch controller when its
rails are on. Scanning, physical events and iOS interaction remain untested.

**Observed on Pixel 6, 2026-10-27 (0117):**
[patch 0117](../research/pixelios-kernel/xnu/patches/0117-oriole-touch-rail-hold-scan.patch)
holds the verified rails for a bounded 60-second mode-2 scan, then restores
both rails. The temporary boot produced
[sanitized evidence](../research/pixelios-kernel/device/google/oriole/hardware/xnu-touch-rail-hold-scan-2026-10-27.txt):
chip ID `36 48 03 00`, controller-ready event `03`, scan mode entered, and
two FIFO status records (`43 05 ...` and `43 01 ...`). The 60-second timer
expired and the log confirmed reverse-order restoration to `0x3c`/`0x2c`.
No finger down/move/up event appeared. The timing of human screen touches
was not independently verified, so this does not yet distinguish an input
path fault from a missed test window. Gestures and app interaction remain
unverified. The image SHA-256 was
`d897fedbf6c1ef2478569f57846dcde1e48ae0c953a6dbf2f2901c5567083a2e`.

The Android factory reset also erased the iOS root in
`userdata`, so an iOS boot needs a freshly verified root image and a new
user confirmation immediately before any flash.

**Built locally, not yet run on hardware (0120 GUI trial, 2026-10-27):**
[patch 0120](../research/pixelios-kernel/xnu/patches/0120-oriole-touch-bounded-gui-window.patch)
adds an exact `sweettouchwindow=1200` boot argument for a best-effort 20-minute
powered touch window, timed from before the first rail-enable attempt. The
full-iOS profile keeps the 1800-second restart setting and does not inject a
software Home event. The kernel SHA-256 is
`b26952bb34e292b2cfea421ddf29efbb4d0509f042848dfdd2bc9db12d40327e`,
the payload SHA-256 is
`be6cd79bfd186f200b34bdef06d5c53c7b00e983348c86c2d354dd6d7c06acd8`,
and the selected 64 MiB temporary AVB boot image SHA-256 is
`b6b152dfba0228d1adf03339ad09493c5ccc96c2c0e10bcfceeb4d62c1dbfc11`.
The exact payload, runtime bounds guard, complete-image digest and AVB
footer/hash were checked locally; the repository gate printed
`GATE PASS fd5b540+dirty`. Independent different-model review found no
concrete blocker but emphasized that cleanup is best effort: a stalled thread,
uncertain ACPM state or earlier restart can prevent or preempt restoration.
The phone was in Android at the time of this update, and this image has **not**
demonstrated a physical iOS swipe, app launch or networking. The reviewed
source is on `main`; the device result remains pending.
Before another trial, `python3 tools/preflight_oriole_touch_gui.py --offline`
checks the two exact local images. With the phone attached in Fastboot, omit
`--offline` to additionally check that exactly the recorded unlocked `oriole`
is present, its bootloader and slot match the private baseline, and its boot
and userdata partition sizes are sufficient. This preflight uses only
`fastboot devices` and `getvar`; it never boots, flashes, or erases. A passing
preflight is not consent to flash `userdata` or evidence that the GUI works.

**Staged input-metadata candidate (0121, 2026-10-28; no Pixel 6 GUI result):**
The [0121 patch](../research/pixelios-kernel/xnu/patches/0121-sweet-hid-integrated-event-metadata.patch)
sets `IsBuiltIn` and `DigitizerIsDisplayIntegrated` on both the hand
collection and each finger event only when `/sweet-touch` has the exact
`pixelios,oriole-ftm5-spi` ADT compatible; the Bluejay event path remains
unchanged. The existing HID service publishes
`Built-In` and `DisplayIntegrated` as *service* properties, but its
`dispatchEvent` method only stamps the sender ID on each event. The
[reference input study](../research/pixelios-kernel/docs/research/22-hackios-reference-study.md#21-what-they-do)
found those two *event* fields in another iOS-on-Android touch bridge.
This is a source-backed candidate for events that reach HID but are ignored
by SpringBoard; it does not establish that this Pixel 6's GUI accepts them.
An independent different-model source review found no remaining issue after
the exact ADT gate was added; it did not compile or boot the change.
**Local build evidence, 2026-10-28:** the final stacked `SweetHID.cpp` compiled
with Xcode's ARM64 Mach-O C++ compiler and the repository's kernel include
configuration. The object SHA-256 is
`981d03e3937cd533a358c17b84b7850a3c3598dee24288b8fd8b7574d83ba639`;
its exported symbol names match the 0120 archive member. Replacing that one
member in the pinned 0120 archive and relinking succeeded. The resulting
offline kernel SHA-256 is
`89da99e097276dc4d5731ebb586e4716efed8936b8d8d33dd81e5a714350f109`
(16,697,320 bytes). Its entry point, load commands, loaded Mach-O segment
layouts, symbol names and `__LINKINFO` symbolsets match the 0120 kernel;
only `__LINKEDIT` size differs. The compiler command, logs, object, archive
and candidate kernel remain under ignored `private/touch-xnu-source/relink-0121/`.
This object check is **not** a complete XNU rebuild or device result. The Linux-only `xnu-local-build`
still cannot run directly on this Mac because its Linux host tools are absent.
**Local temporary-image build, 2026-10-28:** the 0121-specific payload checker
and runtime UFS-root bounds guard accepted the 16,713,664-byte payload SHA-256
`18c9801a52f33d39552302e16a5fd3db17664a06ae2735d44050e86a1268e5a2`.
The separate 0121 profile kept the same Oriole touch hardware flags as 0120,
while leaving 0120's 16,716,864-byte limit and checker unchanged. The shim
host tests and object audits passed. The selected 64 MiB AVB temporary image
SHA-256 is `a153da85ce9bbd3f519c83739e4d6cab1b1df7e220aa896f528c7c294bdb8d2d`;
the complete-image digest, embedded payload, Android v4 layout and local
image metadata were checked. The exact image and its metadata remain in
ignored `private/touch-xnu-source/relink-0121/`. A different-model review of
the profile and revised size guard found no actionable issue. This is still
an **unbooted** image and establishes no GUI touch behavior.
`python3 tools/preflight_oriole_touch_gui.py --offline --trial 0121` checks
the new image and the existing 16 GiB root-image hash locally. Trial `0120`
remains the default; selecting either trial leaves the other trial's SHA
unchanged. Omitting `--offline` adds the same read-only phone identity,
firmware, slot and partition-geometry checks as before.
Preserve the exact 0120 image as a baseline. A later 0121 trial must compare
the same physical lock-screen swipe and app tap, with the input window active,
and record both screen behavior and HID logs. If the 0120 baseline already
responds, the 0121 hypothesis is unnecessary.

1. **Extend the verified touch path to a full iOS boot:** the synchronized 0118 test established physical FIFO and HID events. The diagnostic's 60-second rail window is too short for the previously observed iOS startup. A separate, bounded GUI profile must keep the controller powered through startup, retain cleanup on failure/restart, and preserve a no-touch fallback. Have the hardware-writing change independently reviewed before a temporary boot.
2. **Verify GUI input:** after a freshly approved iOS root restore, test a physical lock-screen swipe, one app icon tap, and a return to Home. Capture both physical screen evidence and USB touch/HID logs; kernel coordinates alone do not establish that SpringBoard accepted a gesture.
3. **Observed iOS behavior:** restoring an iOS root to `userdata` requires a freshly verified image and new confirmation immediately before flashing. Then verify a physical swipe from lock screen to home screen, tap Settings, and return Home. A visible app launch and matching input logs are required before claiming interaction works.

Hardware-writing changes require the repository's independent review and stay on a local `wip/*` branch until it passes. The cycle capture helper, `tools/run_acpm_rail_cycle_inventory.py`, only accepts logs showing both exact on readbacks and both exact off readbacks after reverse restoration; a failed restoration remains an explicit failure. The current Android factory reset erased the earlier iOS root from `userdata`. Temporary inventory boots do not read or write `userdata`.
