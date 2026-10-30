# Milestone 1: iOS Home Screen on a Pixel 6

**Recorded October 29, 2026.** This document summarizes the first research milestone on one physical Google Pixel 6 (`oriole`). It is a status record, not a device installation procedure.

## Observed on hardware

- A temporary `fastboot boot` image passed through a GS101 shim into a patched XNU 8796.141.3 kernel.
- XNU mounted an iOS 16.7.16 (20H392) HFSX root volume from `userdata`, using physical UFS reads and a volatile 512 MiB copy-on-write layer for runtime writes.
- `launchd`, `backboardd`, and SpringBoard ran. The physical panel displayed the lock screen and Home Screen.
- An FTM5 touch driver delivered hardware events to the XNU HID path. In the 0134 experiment, the tester reported entering the Home Screen and opening Settings by touch; USB diagnostics recorded touch events and HID down/up coordinates during the same session.

![Physical Pixel 6 showing the iOS Home Screen](../web/assets/pixel6-ios-home.jpg)

*Tester-supplied photograph of the physical device. This is evidence of a displayed Home Screen, not a claim that all applications work.*

## Limits of this result

The result was observed on one device and one development configuration. It has not been independently reproduced on another Pixel 6. Safari displayed a blank content area when opening Google; Internet access is not verified. The 0134 image overlaid diagnostic text on the graphical interface. A quieter 0135 candidate passed offline checks but was not boot-tested. Multi-touch, additional applications, sleep/wake, long-duration touch, and stable daily use remain unverified.

The phone does not automatically boot iOS. The tested path uses a temporary boot image; a normal reboot may lead to Android Recovery because Android cannot use the experimental HFSX content in `userdata`. Preparing that partition for the experiment erased the prior Android user data.

The [Milestone 1 prerelease](https://github.com/everettjf/pixel6ios/releases/tag/v0.1.0-alpha.2) records this stage. It is a research release without an installable iOS image. Later documentation and host-side tests are on `main`.

## Evidence provenance

The photographs in `web/assets/` were supplied by the tester during the physical-device experiments. Detailed boot and touch chronology, image hashes, and verification boundaries are preserved in the [touch bring-up research log](PIXEL6-TOUCH-BRINGUP.md) and [earlier Home Screen record](PIXEL6-IOS-HOMESCREEN.md). Those chronological logs contain Chinese prose from the original development sessions. Raw USB captures, original framebuffer samples, firmware, Apple images, and private build inputs remain outside Git.

## Next gates

Before anyone else can install this port, the project needs a public reproducible build, a user-supplied iOS root image workflow, device and firmware preflight, repeatable recovery, verified networking and interaction, and an independent second-device test. See [installation status](INSTALLATION-STATUS.md).
