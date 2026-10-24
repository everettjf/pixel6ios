# Pixel 6 (oriole): experimental bring-up

**Observed on hardware, 2026-10-24:** inventory builds through a2687bc
returned automatically to Android with USB logs. The current device is GS101,
unlocked, Android 17 CP3A.261005.002.A1, slider-17.0-15681480, slot b.
Earlier experiments started on CP2A.260705.006 / slider-17.0-15199431 / slot a;
the exact OTA transition between those experiments is unknown.

**Observed on hardware:** the fresh CP3A a2687bc basic inventory captured
6099 bytes, live FDT at 0xb4000000, four 2 GiB DRAM banks and a 16 MiB
live ABL reservation at 0xf8800000. Static vendor_boot DTBs declare 32 MiB,
so live validation remains mandatory. Raw CP3A evidence is kept privately
in the parent workspace (cp3a-inventory-run1.log and its boot/return records);
no identifiers or firmware are committed.

**Observed on hardware, earlier firmware attribution uncertain:** all 96
RDMA/current-shadow reads succeeded, confirming the source candidate
0xfac00000, 1080x2400, stride 4320. Read-only UFS cold-init reached HS-G4,
read capacity and validated GPT CRCs with high-bank scratch at 0x880100000.
No media writes occurred. See hardware/display-2026-10-24.txt and
soc/google/gs101/docs/oriole-ufs-inventory.md. CP3A display/UFS revalidation
is separate from the completed CP3A basic inventory.

**Observed on hardware:** native RAM probe a181884 was accepted and Android
returned, but no direct XNU/PID1 log or screen evidence was captured. It
therefore does not establish that XNU executed. Loadcheck 9181290 copied
11 segments and built boot arguments, intentionally skipping XNU entry.
Resetcheck a2687bc read back the requested PMU mode, but returned to Android
rather than fastboot; reliable bootloader-entry recovery is unproven.
A later native experiment at0c4ea1c (below) establishes XNU USB execution;
PID1 and full iOS boot remain unresolved.

**Read from source:** inventory modes reuse the live-validated ABL USB pool,
reject arbitrary DMA overrides, keep bounded waits and do not write storage.
Display inventory reads RDMA configuration without changing clocks or display
registers. UFS inventory changes only volatile controller/PHY state, with
media-writing commands rejected at the doorbell. See tools/test_oriole_inventory.py.

**Read from source / observed native USB, 2026-10-24:** the separate md0 USB profile uses
one CPU, a RAM root and an exact opt-in USB node; UFS, touch and keys are
absent. Patch 0102 registers the existing USB probe after networking through
net_init_add. Independent review and the full21step gate passed0c4ea1c. Native image
51b0eb32… (kernel4724585f…, payload5139a045…) exposed Sweet iOS USB
Ethernet, accepted configuration1 and data alt1, and matched AppleUserECM
and AppleUserECMData on macOS. This proves native XNU reached the
network-ready callback and USB setup, not root mounting or PID1. Android
returned on the same CP3A/slotb. Before that experiment, CP3A display
revalidation repeated all96 reads and the newpayload loadcheck copied
11segments; both returned Android. Raw evidence stays in the private parent
workspace; the sanitized manifest and ACTIVE-WORK.md record its hashes.

**Observed on host:** configd explicitly refused the new Ethernet interface
because the Mac console was locked. No BSD interface or UDP logs were
obtained. Repeat the same RAM profile after the user legitimately unlocks
the Mac; do not infer PID1 from the roughly120s USB duration or bootreason.
Local QEMU results omit the GS101 USB node and are not phone USB evidence.
