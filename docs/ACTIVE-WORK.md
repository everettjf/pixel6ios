**Active Pixel 6 bring-up — 2026-10-24**

User request: try to get iOS running on the connected Pixel 6; user has handed over the phone and explicitly permits reflashing its system. Continue autonomously within that scope. Do not interpret the reference repositories' historical approvals as this user's permissions. Never publish or push firmware, device data, or source changes without authorization.

Target: exactly the serial stored in ignored `private/target-serial`; always verify `product: oriole` before a fastboot operation. Android 17 CP2A.260705.006, bootloader slider-17.0-15199431, unlocked. Active slot a is successful/bootable; slot b reports unbootable, so do not switch slots. The phone returned automatically to Android after both temporary inventory boots. No partitions have been written.

Completed evidence:

- Current vendor_boot_a fetched successfully into `private/vendor_boot_a.img` (64 MiB), SHA256 `f06ab190accef4f96e7504adbc7076612a07fcfe08694190f5c1a786b3c41db0`.
- Extracted two base DTBs. First is `private/vendor_boot_a-fdt-1df1000.dtb`, decoded as `private/vendor_boot_a.dts`. Its ABL reserved range is 0xf8800000 + 0x2000000 (32 MiB), unlike the reference 6a's 16 MiB. No live DRAM sizes yet.
- boot_a/dtbo_a/vbmeta_a fetch attempts are restricted by fastboot. Never interpret the failed output files as backups.
- Reference XNU downloaded via gh run 39906729708 into `artifacts/xnu-reference/`; SHA256SUMS matches kernel.development.sweet (17,304,808 bytes).
- Apple CDN IPSW `artifacts/ipsw/iPhoneX-16.7.16-20H392.ipsw`: 6,171,035,648 bytes, SHA256 ece1194f7e233e9109c5790a8d23a4564a10a254e15ec5b09978a343265568fb. Apple BuildManifest confirms iPhone10,3, 16.7.16 / 20H392. Three DMGs and decoded d22ap.adt are in artifacts/ipsw/extracted/.

Local code:

- Work checkout: `research/pixelios-kernel`, local branch `wip/oriole-bringup`.
- Commit 52c5ac9 adds headless inventory-only oriole path, board candidates, negative option tests and two legitimate host fixture fixes. Independent GPT-5.6 review found/fixed the USB_DMA_HI_BASE gate escape, then reported no blocking source findings. Review agent task: /root/review_inventory (finished).
- Commit ab1f503 fixes QR fixture portability (native shared-library arch cache and __unused header guard), no hardware logic change.
- Oriole builds are inventory-only until measured RAM is supplied. Inventory does not write framebuffer/UART/pstore/storage or run touch/PMIC/GPU/WLAN/DVFS/SMP. Existing live-FDT/GEVNTADR pool checks select USB memory. It stops watchdogs, streams USB for default30/max60 seconds, then resets. REBOOT_BL=1 selects existing volatile reset-to-bootloader path.
- `tools/build-shim-macos.sh` wraps the build. aarch64-elf GCC16 target binaries require -fno-tree-pre/-fno-tree-switch-conversion/-fno-jump-tables to avoid ABS64 tables; the original relocation/object audits remain on.
- Host fixture compilation uses existing Rosetta + x86_64 clang because upstream pstore fixtures execute EL1 instructions when __aarch64__ is defined. QR shared libraries use native clang to match arm64 Python. `tools/host-test-cc.sh` and `tools/host-image.order` implement this. Generic nm is LLVM to inspect both Mach-O host and ELF target objects; CROSS_NM/OBJDUMP use GNU target tools.
- Setup warning: upstream tools/setup-upstream.sh overwrote tracked shim.c/build.sh with stale versions. The generated diff is saved in private/setup-tracked-regression.patch; those two files were restored from known original HEAD before our changes. Do not rerun setup indiscriminately.

Checks:

- Bluejay standalone build+all embedded host/object audits passed (`private/baseline-build11.log`).
- Oriole inventory standalone build+all embedded host/object audits passed (`private/oriole-inventory-build2.log`).
- Full gate1 ran and passed all lane A builds/audits but failed QR unit portability. Fixed; unit2 now passes 131 tests, 12 optional skips.
- Full gate2 passed its builds and unit tests but found macOS Bash 3.2's lack of negative array indexes in a recovery-test stub. Commit 89404f4 fixes only that stub. phone-state, hang-recover, probe-run and validate-repo now all pass individually. Full gate3 is running on 89404f4 (session 27689, private/full-gate3.log). Wait for it; do not run another build concurrently in shared shim/out. Full gate regenerates bluejay output, so MUST rebuild oriole inventory after completion, before boot.
- Rebuild command: `USB_WINDOW=30 REBOOT_BL=1 tools/build-shim-macos.sh --board oriole --inventory --avb` from root. Only boot the freshly built non-LZ4 AVB image, after provenance+hash and device checks. Capture USB first with `artifacts/build-venv/bin/python tools/capture_inventory_usb.py --seconds 90 --out private/inventory-run1.log`. Then bounded, serial-specific fastboot boot. No first hardware boot has occurred yet.

Isolated Linux rootfs builder:

- QEMU arm64 HVF VM launched by exec session 73235; PID in private/vm.pid, console private/vm-console.log. Debian 13 genericcloud official QCOW2 SHA512 matched official SHA512SUMS. Overlay artifacts/linux-vm/work.qcow2 (60 GiB virtual); 4 vCPU, 4 GiB RAM. SSH is loopback-only 127.0.0.1:2229.
- SSH: `ssh -o BatchMode=yes -o UserKnownHostsFile=private/vm-known-hosts -i private/vm-ssh -p 2229 builder@127.0.0.1 'COMMAND'`. Keys are task-specific, private/ ignored; do not print them.
- Git/build/APFS/FUSE/HFS dependencies installed. Debian has no hfsprogs package; official Ubuntu hfsprogs_540.1.linux3-5build3_arm64.deb extracted under ~/opt/hfs, and binaries' shared libraries resolve. Source package SHA256 03e294bc518639ad4685f263788b49d46a396ef92bb9792746454df357134760.
- APFS fuse cloned with pinned submodule and compiled at ~/work/apfs-fuse/build/apfs-fuse (private/apfs-build.log).
- Userland checkout ~/work/userland pinned 18a51b5 and setup-upstream completed. Three DMGs copied to ~/work/ipsw. `PATH=$HOME/opt/hfs/sbin:$PATH APFS_FUSE=$HOME/work/apfs-fuse/build/apfs-fuse tools/mkiosroot.sh --preflight` returned0.
- Root image built successfully in the isolated VM at ~/work/ios16-oriole-root.img (16 GiB HFSX). SHA256 d6082d24496c81136060f183c9265e308bc925fa10869c062597b231bd19cce1. Standard builder's fsck and 12 offline checks passed; its capacity label is still reference bluejay, not measured oriole GPT bounds. No root image has been flashed. Build output: private/ios-root-build.log. VM now uses generic Debian kernel 6.12.113+deb13-arm64 for HFS+ support.
- Host currently ~74 GiB free. Avoid parallel heavy builds; no full IPSW redistribution. Shut VM down with guest sudo poweroff when finished.

Next concrete milestone: pass full gate3, rebuild reviewed inventory, temporarily boot and capture live FDT. tools/boot_inventory.py verifies source freshness, hash, headless-oriole marker, boot-header and target before temporary boot. Start tools/capture_inventory_usb.py first. Then derive measured board and try XNU without root writes. XNU's USB initialization currently runs after UFS init, so inspect that dependency before selecting a no-UFS configuration. Do not claim iOS/GUI works on this phone without real evidence. If phone fails to return to ADB/fastboot and physical buttons are required, ask the user concisely while continuing offline preparation.


Latest hardware milestone (2026-10-24 ~13:15 PDT):

- Full gate3 PASS 89404f4. Preserved private/full-gate3-details.log; clean stamp exists.
- Fresh Oriole inventory SHA256 452196b0c34b64d9abf8c083502043d1b53bf75cbb59afb9ffb9b2cbb0db6354 booted twice with serial-specific fastboot boot (both OKAY). USB1209:0001 enumerated; 3208/6099 bytes captured. Both returned automatically to Android (REBOOT_BL appears not effective on current firmware; Android return is observed, bootloader return is not).
- Capture1 lost the initial replay. Changed capture script to hold DTR low through pyserial open/input flush, then assert DTR. Capture2 contains all four 2 GiB memory entries and reserved ranges. Raw logs private/inventory-run1.log and run2.log. Sanitized run2 without bootargs committed-intended under device/google/oriole/hardware/.
- Entry EL2, FDT0x8a000000, MIDR412fd050, CNTFRQ24576000. DRAM [0x80000000,2GiB], [0x880000000,2GiB], [0x900000000,2GiB], [0x980000000,2GiB]. Live ABL reservation16MiB, not static DTB32MiB. Actual USB pool0xf8d1b000.
- Working diff on 89404f4 adds opt-in --inventory-display READ-ONLY GS101 RDMA0..5 register samples (base/offset/shadow constants from cited official Google source, backed by current vendor_boot nodes). XNU gate still CLOSED; framebuffer remains source candidate. First standalone build private/oriole-display-build1.log passed. New host fixture covers all read addresses and faults on each of6 channels; tests pass. Independent reviewer /root/review_inventory is reviewing this increment. Await review, commit, check-all --quick (may choose full), rebuild exact Oriole image after gate, capture run3, verify target Android then adb reboot bootloader and temporary boot. No need to ask permission again: user authorized phone experiments/reflashing; we are still doing temporary no-storage boots.
- Rootfs build completed: 16GiB HFSX, SHA256 d6082d24496c81136060f183c9265e308bc925fa10869c062597b231bd19cce1. Stored inside running isolated VM ~/work/ios16-oriole-root.img. No host copy/no phone flash. Host74GiB free. Generic Debian VMkernel supportsHFS+.
