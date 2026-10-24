**Pixel 6 bring-up — current handoff, 2026-10-24**

User authorized actual phone experiments and reflashing. User is away; avoid depending on screen/button responses. Work remains local; no push/public upload. Serial is only in ignored private/target-serial. Every operation targets that serial and verifies oriole. Do not downgrade or write bootloader/radio/persist/efs/GPT/boot/vbmeta/dtbo. No experimental flash/erase/media write has occurred. Android itself completed an OTA; do not describe the device as unchanged.

Current firmware: Android 17 CP3A.261005.002.A1/16269273, security 2026-10-05, bootloader slider-17.0-15681480, unlocked, slot b. Fully booted Android was verified after resetcheck. Initial baseline was CP2A.260705.006/15641320, slider-17.0-15199431, slot a. Exact OTA transition between experiments is unknown: earlier boot records did not bind firmware+slot. New strict host gate now requires an explicit baseline, exact-one well-formed getvar values, active-slot geometry and permitted profile; never automatically adopt drift.

**Actual evidence**

- Four initial headless inventory boots returned to Android. Live FDT 0x8a000000; four 2GiB banks at 0x80000000, 0x880000000, 0x900000000, 0x980000000. Live ABL 0xf8800000+0x1000000; USB pool 0xf8d1b000. Static vendor_boot DTB instead reserves 32MiB; runtime validation remains mandatory.
- CPU0 EL2, MIDR 412fd050, CNTFRQ 24576000; only CPU0 native feature registers measured. Android topology 4A55/2A76/2X1.
- Display read-only inventory: all 96 RDMA/current-shadow config reads succeeded. RDMA0 base FAC00000,1080x2400,format0,offset0,natural stride4320. No observed screen output yet.
- UFS read-only inventory: cold-init HS-G4, high DMA scratch 0x880100000+0x20000, LUN0 4096-byte blocks, last LBA01DC03FF. CRC-checked GPT userdata0022F1E6..01DC03FA, bytes1B91215000 matches fastboot; final DBR/RSR0. No media writes.
- Native RAM probe a181884 was accepted, then Android returned with watchdog,apc,early. No direct XNU/PID1 evidence. Bootreason/elapsed time do not establish execution or distinguish normal reset fallback.
- Loadcheck9181290 received592B USB log: full JUMP0000000881493488,11 segments copied/zeroed, bootargs constructed, entry intentionally skipped; Android returned. Approx61s before USB +30s USB +18s Android is consistent with observed timing, not evidence of a120s hardware watchdog.
- Resetcheck a2687bc received869B: SYSIP before0, mode SMC ret0, valid readback fc, drain before SWRESET. No SWRESET-return log. Android returned, NOT fastboot. Complete bootloader-entry protocol remains unproven. Do not use it as a native XNU success marker or infer why it failed.
- vendor_boot_a fetched64MiB SHA f06ab190accef4f96e7504adbc7076612a07fcfe08694190f5c1a786b3c41db0. New vendor_boot_b-cp3a.img SHA450dbe70f90627ac7cef2ea3e878e2bb30f05061adf9a025427c5b3326625b55. Both new DTBs decode; relevant static USB/WDT0/WDT1/PMU/UFS/ABL reg ranges match old. Static equality is not runtime proof.
- boot/dtbo/vbmeta fetch was restricted; failed outputs are NOT backups. No matching complete factory restore set verified. Never downgrade.

Raw evidence stays private: inventory-run1..4.log, ramprobe-run1-boot.json, ramprobe-return1.json, loadcheck-run1.log/boot/return/observed.json, resetcheck-run1.log/result1.json/final-device1.json, device-facts-cp3a.json, cp3a-fastboot-facts.json, cp3a-static-comparison.json. Do not publish raw identifiers.

**Code and build**

research/pixelios-kernel branch wip/oriole-bringup HEAD a2687bc. Eight local commits52c5ac9,ab1f503,89404f4,5b5dd7a,5332b32,a181884,9181290,a2687bc; root patches1..8 exported. Fixed upstream41198ee; same101 XNU patches as reference CI759b3e3. No push. Different-model-family reviewer /root/review_inventory is GPT5.6; author GPT6. Applicable source AGENTS require independent hardware review. Reuse reviewer; do not spawn more unsolicited agents.

Full21-step gates passed through a2687bc. Latest private/resetcheck-gate1.log/details. Every hardware profile must be freshly built after gates (check-all overwrites shared shim/out with bluejay). NEVER edit clone during build; only one shared build at a time. Build wrapper tools/build-shim-macos.sh supplies GCC16.2/binutils2.47, GNU tools, Python artifacts/build-venv. Target flags prevent unsupported ABS64; original audits retained. Host fixtures x86_64/Rosetta, QR library native arm64. Do NOT blindly rerun setup-upstream.sh; it once overwrote tracked sources with stale patches (reverted).

RAM profiles: tools/oriole_ramprobe.py pins entire payload16726576B SHA6ae22614d729439dcff3345c41f4e3aefd6451be5b77f7518757c89ae9567f66. Native uses cpus=1,sweetusb=0,rd=md0, noUFS/USB/touch/keys, sourcedPMUreset. Loadcheck copies but never branches/cache-flushes; resetcheck adds bounded USB+two allowlisted PMU SMC writes, no XNU entry. All profile flags mutually exclusive, runtime live-FDT copy/isolation guards precede writes. Persistent source/object/ELF reset audit runs every build;19 mutation tests passed. Changed compiler requires new review.

Withdrawn no-UFS draft and USB-active-to-XNU draft stay private and must not boot: md0 never initializes XNU USB, and gadget_stop is not positive DMA quiescence proof. Polled restart timeout is not panic-proof watchdog. Establish direct XNU entry evidence with early framebuffer marker/usable observation or independent logging; do not infer execution from silence/reboot timing. Current PMU bootloader reset is NOT reliable.

**Inputs/offline results**

- Official iPhone X iOS16.7.16/20H392 IPSW artifacts/ipsw/iPhoneX-16.7.16-20H392.ipsw SHAece1194f7e233e9109c5790a8d23a4564a10a254e15ec5b09978a343265568fb.
- Reference CI39906729708 kernel artifacts/xnu-reference/kernel.development.sweet17304808B SHA8e4d38ea655930ef1da4998ab236962caabb9c8af1efaed6a96e243039af2292.
- Exact minimal init tools/oriole-ram-init.S and pinned mkinit; init MachO SHAbe90fb2e86b26deab1550cdc84396f7d3421e0c66e8e2685d6e0d470983977d8. QEMU reached PID1 and all three5s select waits, then reset timeout panic because QEMU ADT has no board reset. NOT native proof.
- 16GiB HFSX root inside powered-off Debian13 ARM64 VM ~/work/ios16-oriole-root.img SHAd6082d24496c81136060f183c9265e308bc925fa10869c062597b231bd19cce1; fsck+12offlinechecks passed. Overlayartifacts/linux-vm/work.qcow2; SSH127.0.0.1:2229 keyprivate/vm-ssh knownhostsprivate/vm-known-hosts. No phone rootfs flash. Do not copy d22ap.adt into kernel research/ipsw-x during fixed RAM profile (changes deterministic payload).

**CP3A runtime revalidation**

Fresh a2687bc inventory build SHA2084242fbf065f02d4d376a27cb1811afe7e440e46829022e5f25d3836cda20c accepted;6099B USB log captured. Full report shows live FDT now0xb4000000 (old0x8a000000), same four2GiB banks, liveABL16MiB, USB pool0xf8d1b000. All reported reservations below4GiB. Capture includes a partial replay before the complete report marker; observations use the complete report. Current private baseline permits only inventory. Records cp3a-inventory-run1-boot.json/run1.log/observed1.json/return1.json. Android returned automatically: productoriole,sys.boot_completed1,CP3A.261005.002.A1,slider-17.0-15681480,slot_b at22:36:43UTC; bootreasonwatchdog,apc,early. Phone currently fully booted Android; no build/capture process remains.

**Next milestone**

CP3A basic inventory is revalidated. Android return confirmed. Keep display/UFS/XNU profiles closed until individually reviewed for the current firmware. Full iOS/XNU native execution remains unresolved; userdata flash is not useful until entry/logging is proven. Rootfs build is ready for later stages, not a reason to skip them.
