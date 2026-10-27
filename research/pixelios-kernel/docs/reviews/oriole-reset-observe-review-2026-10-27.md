# Oriole reset-readback diagnostic review — 2026-10-27

Scope: the `ORIOLE_TOUCH_ID_RESET_OBSERVE` branch in `shim/orioletouchid_hw.c`, its isolated build flag, host tests, and source/object audit. Reviewed independently by a different model family before physical execution. This is source and host-test evidence, not a hardware result.

Decision: **GO for one bounded temporary boot**, after the full gate and exact-image identity/hash checks. The reviewer found no blocking safety defect. The diagnostic uses the existing allowlisted reset-DAT write, samples immediately and after nominal 1 ms and 10 ms delays, then unconditionally fails preparation before `spi_identify`. Cleanup still attempts reverse-order GPIO/engine and rail restoration; a late matching sample does not clear an earlier restore error. The normal-path host test still exercises the original chip-ID flow; the separate diagnostic test confirms zero SPI commands even when all samples match, and covers one-read lag, stuck-low output, failed writes, post-application write errors, and read faults.

Verification: `git diff --check`, both host-test variants, isolated Oriole build with source/object/image and mutation audits, and full repository gate (`GATE PASS 3eff9ed+dirty`). The labels `us=1000` and `us=10000` denote requested minimum waits, not measured wall-clock timestamps; console output adds unspecified time.

Remaining limit: no physical readback has yet been observed for this candidate. This review does not establish a correct touch-chip ID, restoration on real hardware, iOS touch, gestures, or app launches.
