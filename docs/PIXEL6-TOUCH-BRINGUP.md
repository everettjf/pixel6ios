# Pixel 6 touch bring-up

Updated 2026-10-25 PDT. This is a staged hardware investigation, not an installation recipe.

## Known state

- **Observed on Pixel 6:** iOS 16.7.16 reaches the lock screen and, after a timed software Home event, the home screen. A physical upward swipe did not unlock; app taps have not worked. See [the home-screen record](PIXEL6-IOS-HOMESCREEN.md).
- **Read from this repository:** the Oriole iOS payload generator removes `/sweet-touch` and `/sweet-keys` from the Apple device tree. The existing GS101 FTM5 XNU driver only starts if `/sweet-touch` is present. The current iOS image therefore cannot deliver physical touches to SpringBoard.
- **Read from Google device-tree source, unverified on this Pixel 6:** Oriole lists an STMicro FTM5 controller on SPI11, with `36 48` as the expected ID. `device/google/oriole/board.json` holds the source-derived pins and coordinates. Bluejay probe results do not establish Oriole rail or pin state.

## Safe first measurement

The Oriole inventory image now accepts `--touch-probe` with **no options**. It runs the existing phase-1 `touch_probe_dump()` inside the already bounded inventory path, after live FDT and RAM checks. That function reads CMU, USI mode and GPIO pad registers; it reads SPI registers only when the USI mode is already SPI. The Oriole inventory guard rejects `--touch-probe=run`, `railsr`, `rails`, a payload, and other peripheral experiments. This change does not add a touch node to the iOS image.

```sh
cd research/pixelios-kernel
tools/check-all.sh                  # must print GATE PASS
shim/build.sh --board oriole --avb --usb-gadget --inventory --touch-probe
```

`check-all.sh` overwrites `shim/out/`, so build the probe again afterwards. Before a temporary `fastboot boot`, verify that exactly one attached device reports `product: oriole`, the bootloader is unlocked, and the image hash matches the freshly built probe. Capture the USB/RAM log and record the CMU, USI mode, seven pad values and any read faults. This phase does not read or write storage and does not modify partitions. No Pixel 6 result is claimed until that capture exists.

## Next gates

1. **Observed hardware:** compare the read-only register dump with the Oriole device tree and the known Bluejay baseline. Check the current touchscreen rail state using a separately reviewed ACPM read path only after its layout gate is satisfied.
2. **Observed hardware:** identify `36 48` on this Pixel 6 with a bounded, reviewed SPI/clock/reset probe. The existing `touchprobe.c` has these writer paths, but Oriole still forbids them; do not bypass the inventory guard or assume the Bluejay sequence is safe here.
3. **Implementation:** only after a successful chip-ID and event-FIFO measurement, add an Oriole touch ADT node and a separate iOS boot profile. Preserve the existing no-touch profile as a fallback. Start with identify-only mode, then one-finger events.
4. **Observed iOS behavior:** verify touch down/up and coordinate scaling in the USB log, then a physical swipe from lock screen to home screen, then tap Settings and return Home. A visible app launch and matching input logs are required before claiming interaction works.

Hardware-writing changes require the repository's independent review and stay on a local `wip/*` branch until it passes. The iOS root on `userdata` remains read-only at the UFS layer during these temporary boots; the RAM COW layer handles runtime writes.
