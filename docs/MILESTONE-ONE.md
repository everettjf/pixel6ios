# Milestone 1: iOS Home Screen on a Pixel 6

**Recorded October 29–30, 2026.** This document summarizes the first and, for now, final research milestone on one physical Google Pixel 6 (`oriole`). It is a status record, not a device installation procedure.

## Observed on hardware

- A temporary `fastboot boot` image passed through a GS101 shim into a patched XNU 8796.141.3 kernel.
- XNU mounted an iOS 16.7.16 (20H392) HFSX root volume from `userdata`, using physical UFS reads and a volatile 512 MiB copy-on-write layer for runtime writes.
- `launchd`, `backboardd`, and SpringBoard ran. The physical panel displayed the lock screen and Home Screen.
- An FTM5 touch driver delivered hardware events to the XNU HID path. In the 0134 experiment, the tester reported entering the Home Screen and opening Settings by touch; USB diagnostics recorded touch events and HID down/up coordinates during the same session.
- Later tester-supplied photographs show the Home Screen, Settings, and Settings → General → About. The tester swiped up from the lock screen, tapped to open apps, and navigated through Settings. This interaction was extremely slow.

![Physical Pixel 6 showing the iOS Home Screen and a live diagnostic overlay](../web/assets/gallery/pixel6-home-debug.jpg)

*Tester-supplied photograph of the physical device. This is evidence of a displayed Home Screen, not a claim that all applications work.*

## Limits of this result

The result was observed on one device and one development configuration. It has not been independently reproduced on another Pixel 6. Safari opened but displayed a blank content area at `google.com`; Internet access is not verified. The tested image overlaid diagnostic text on the graphical interface. A quieter 0135 candidate passed offline checks but was not boot-tested. Performance was extremely slow, including transitions and touch response. Multi-touch, sleep/wake, long-duration touch, wider application behavior, and stable daily use remain unverified.

The About photo shows iOS 16.7.16, Model Name “Pixel 6”, and Model Number `oriole`. Its editable device Name reads “Pixel 6a”; this is inherited presentation data, not evidence of Pixel 6a support. Some other About values are placeholders or incomplete and should not be treated as verified hardware properties.

The phone does not automatically boot iOS. The tested path uses a temporary boot image; a normal reboot may lead to Android Recovery because Android cannot use the experimental HFSX content in `userdata`. Preparing that partition for the experiment erased the prior Android user data.

The [Milestone 1 prerelease](https://github.com/everettjf/pixel6ios/releases/tag/v0.1.0-alpha.2) records this stage. It is a research release without an installable iOS image. Later documentation and host-side tests are on `main`.

## Evidence provenance

The photographs in `web/assets/` were supplied by the tester during the physical-device experiments. The seven October 30 photos in [`web/assets/gallery/`](../web/assets/gallery/) are 1,350 × 1,800 JPEG derivatives, resized and saved without the source EXIF metadata; the original downloads were not changed. They cover Home with a debug bar, a blurred transition, Settings with and without a debug bar, About, full-screen diagnostics, and Safari's blank page. Detailed boot and touch chronology, image hashes, and verification boundaries are preserved in the [touch bring-up research log](PIXEL6-TOUCH-BRINGUP.md) and [earlier Home Screen record](PIXEL6-IOS-HOMESCREEN.md). Those chronological logs contain Chinese prose from the original development sessions. Raw USB captures, original framebuffer samples, firmware, Apple images, and private build inputs remain outside Git.

## Closing status

This curiosity-driven, AI-assisted research experiment is paused after its first milestone. No practical use case or product roadmap has been identified. The technical work remains public so others can inspect the result and its limits. Before anyone else can install this port, the project would need a public reproducible build, a user-supplied iOS root image workflow, device and firmware preflight, repeatable recovery, verified networking and interaction, major performance improvements, and an independent second-device test. See [installation status](INSTALLATION-STATUS.md).
