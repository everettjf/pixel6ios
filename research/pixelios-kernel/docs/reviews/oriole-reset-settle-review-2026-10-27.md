# Oriole reset-settle writer review — 2026-10-27

Independent different-model review of the `ORIOLE_TOUCH_ID_RESET_SETTLE`
candidate in `shim/orioletouchid_hw.c`, its host test, isolated build flag, and
source-hash audit. This is a source/host-test review, **not a hardware result**.

**Decision: GO for one bounded temporary `fastboot boot` only after the full
repository gate, fresh isolated build and object audit, exact-image hash,
product, unlock-state, and firmware checks pass.** The reviewer did not edit
files, commit, push, or run device commands.

- **Read from source:** the candidate retains the same reset DAT address and
  mask, and the same single SPI ID attempt. It waits a nominal 1 ms for
  readback, then another nominal 9 ms on mismatch; read errors or a persistent
  mismatch fail closed. The cleanup flag clears only after delayed readback
  matches. Rails are still restored after GPIO cleanup failure. No additional
  MMIO address, bit permission, SPI command byte, rail value, or retry was
  introduced.
- **Observed on hardware (prior eighth run):** reset-release DAT read high at
  nominal 1 ms and 10 ms, and reset-restore DAT read low at nominal 10 ms.
  The cause of this lag is unknown. The new code has **not** yet been tested
  on hardware.
- **Host-tested:** normal, diagnostic, and reset-settle fake-MMIO tests pass;
  source hash pins and build marker check pass; `bash -n shim/build.sh` and
  `git diff --check` pass. The fake lag uses read count rather than elapsed
  time, so it does not prove wall-clock settling on the device.

The reviewer found no blocking safety or correctness defect. The driver must
still inspect the full gate result and the exact boot image before any
physical run. An image that passes the audit can still fail at the next
unmeasured hardware state; it must not be described as enabling physical
touch until verified on-device.
