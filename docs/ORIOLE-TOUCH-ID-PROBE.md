# Oriole touch ID probe: implementation gate

Status: local work in progress, 2026-10-26 PDT. A candidate SPI writer, fake-hardware test, isolated `--inventory-touch-id` image profile, and pinned source/object/image audit exist on `wip/oriole-touch-id-hw`. The profile builds locally, but the revised writer has **not** had its required second independent review or run on Pixel 6. The physical phone remains available in Fastboot; no touch-ID image has been booted.

The first independent review identified missing live-FDT/RAM gates and incomplete restoration around USI reset. The candidate now requires the live root compatible token `google,GS101 Oriole` and a live `/memory` range containing the image, and refuses a non-default SPI engine before reset. It also marks all captured engine fields for restoration before reset and checks the untouched engine words remain zero. Host tests exercise these failures and a reset that clears fake SPI registers. This is **not** yet proof of real reset semantics: the second independent review and a physical measurement remain required. Google's [Oriole device-tree overlay](https://android.googlesource.com/kernel/devices/google/raviole/+/refs/tags/android-16.0.0_r0.9/dts/gs101-oriole.dts) is the source for the compatible string.

## Evidence and target

- **Observed on Pixel 6:** Android exposes `fts` at `spi11.0` and reports a 1080×2400 input range ([sanitized capture](../research/pixelios-kernel/device/google/oriole/hardware/android-touch-2026-10-26.txt)). A shim inventory found USI11 mode 0 and the SPI, mux and reset pads in function 0 at the bootloader handoff ([capture](../research/pixelios-kernel/device/google/oriole/hardware/touch-inventory-2026-10-26.txt)).
- **Observed on Pixel 6:** ACPM reads returned LDO25M `0x2c` and LDO26M `0x3c`, both disabled. A separate bounded image enabled them in that order, read back `0xac` and `0xbc`, then restored LDO26M and LDO25M to their exact initial values ([capture](../research/pixelios-kernel/device/google/oriole/hardware/acpm-touch-rail-cycle-2026-10-26.txt)).
- **Read from source:** Google's GS101 touch device tree maps those LDOs to the FTM5 supplies and maps the controller to SPI11. Its FTM5 probe enables `vdd` then `avdd`, drives reset low for 10 ms and then high. See the pinned links in [PIXEL6-TOUCH-BRINGUP.md](PIXEL6-TOUCH-BRINGUP.md).
- **Read from source:** the existing Bluejay `touchprobe.c` implements ABL-style manual CS, USI mode, clock, pads, reset and the `FB 20 00 00 00` chip-ID request. It is not an Oriole image: `build.sh` currently refuses an Oriole `run` profile. On Bluejay, the SPI engine stalled in earlier experiments; the full writer sequence has not been proved on Oriole ([research 21](../research/pixelios-kernel/docs/research/21-touch-spi-stall-investigation.md)).

The next evidence needed is a bounded SPI response with the expected `36 48` ID (or a precise failure trace). An Android input device alone does not establish that XNU can talk to the controller.

## Proposed isolated image

Use a **new, explicit Oriole inventory profile**, separate from `--inventory-acpm-rail-cycle` and `--touch-probe=run`. Link only the code required for ACPM, USB logging, USI11/SPI11, and the touch pads. No payload, XNU, UFS, userdata access, or generic register poke belongs in this image. Keep the existing Oriole guard; a new allowlist and source/object audit must recognize this profile specifically.

The bounded run should:

1. Validate the same live FDT, RAM, ACPM channel, empty queues, rail registers and exact disabled values as the successful rail-cycle image. Refuse with zero **rail-update, SPI, pad and clock writes** on a mismatch. ACPM `FUNC_READ` itself writes the transport SRAM and mailbox, so a literal zero-MMIO-write claim would be false; its existing bounded transport audit still applies.
2. Snapshot all readable shared state that the SPI probe will modify before the first write: the AP/AOC mux GPIO, four SPI pads, reset GPIO, USI11 mode, CMU_TOP gate, USI11 CMU mux/divider and gates. Do not read USI/SPI engine registers until the USI mode is SPI. Log each snapshot and abort before writing if one fails.
3. Enable LDO25M then LDO26M via the existing gated ACPM client and verify both readbacks. Track publication of *each* request, including uncertain replies, so every possibly enabled rail receives a reverse-order restore attempt.
4. Configure only the source-backed ABL/Linux SPI11 path: AP bus ownership, bounded CMU mux/divider waits at a rate no greater than the device-tree limit, USI SPI mode, pad functions, manual CS and one controller reset pulse. Use the existing five-byte FTM5 hardware-register request. Cap all polls and log the exact first failure.
5. Stop after one chip-ID read or one bounded timeout. Do not scan addresses, retry indefinitely, or start an iOS payload.
6. In a single cleanup path, disable TX/RX, deassert CS, restore reset/pads/mux/CMU/USI fields in reverse dependency order, then restore LDO26M and LDO25M. Read back all restorable fields and both rails. If any restoration is uncertain, emit an explicit failure and never report success. A device reset remains the final containment step.

The existing `touch_probe_run()` is **not** directly callable for this profile: several early returns skip restoration, and it retains mux/clock changes after some transfers. Reuse only individually audited mechanisms or add an independently tested cleanup path. In particular, no SPI register snapshot may be taken while USI mode is 0.

## Review and acceptance

Before hardware: fake-MMIO/APM tests must cover an initial-state mismatch, failed snapshot, published update with a missing reply, each SPI timeout, cleanup after every failure stage, and a failed restore. The source and object audit must prove every MMIO store goes through a profile-specific allowlist and every ACPM update is one of the two bit-7 rail changes. `tools/check-all.sh` must pass, then build the exact Oriole image **after** the gate because the gate overwrites `shim/out/`. A different model family must independently review the hardware writer before it leaves a local `wip/*` branch.

For a real run: verify exactly one fastboot target reports `product: oriole` and an unlocked bootloader; pin the exact image SHA-256 in the private baseline; arm USB capture before `fastboot boot`. Accept the capture only if the full boot marker, ID bytes, bounded cleanup and two exact rail restorations are present. A partial log or timeout is a failed test. Keep serials and raw logs out of Git.

Only after this measurement should an iOS boot profile power the rails for the lifetime of the XNU touch driver, retain a no-touch fallback, and test a physical lock-screen swipe and app tap. The current Android reset erased the prior iOS root in `userdata`; any reflash requires a separate exact-image verification and user confirmation immediately before it.
