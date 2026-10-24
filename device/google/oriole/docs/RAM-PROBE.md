# Oriole RAM-only XNU experiment

Local wip work, 2026-10-24. Native XNU is still UNRUN on this phone.

Observed on hardware: four temporary inventory boots returned to Android;
measured RAM and framebuffer are recorded in hardware/. Read-only UFS high
DMA and CRC-validated GPT passed on5332b32; final DBR/RSR were0. No partitions
have been written. Pixel6 user explicitly authorized experiments/reflashing.

Read from source: the existing MockFS patches serve a static Mach-O RAM disk
as /sbin/launchd. rd=md0 avoids sweet_ufs_init. The new init prints its PID,
performs three five-second select waits, requests reboot and never exits.
No filesystem/media writer is present in this experiment. The ADT omits
sweet-ufs, sweet-usb, sweet-touch, sweet-keys; boot arguments use cpus=1,
sweetusb=0 and rd=md0. Reset uses the existing sourced gs101 PMU node.

Observed in QEMU (not Pixel6): exact kernel SHA256
8e4d38ea655930ef1da4998ab236962caabb9c8af1efaed6a96e243039af2292
reached PID1 and completed all three waits. After MACH Reboot the QEMU
profile reported Halt/Restart Timed Out (it has no sweet-reset node).
Real Oriole display, native kernel execution and reset callback remain
unverified. A kernel hang may require manual Power+VolumeDown recovery;
no watchdog or automatic recovery guarantee is made.

The tool tools/oriole_ramprobe.py builds or checks exactly one complete
payload SHA256, binding kernel, ADT, arguments and init. A changed binary
or policy requires another review. The runtime loader independently checks
all rounded copy/source/destination ranges before copying anything and
requires the entire selected2GiB bank to be free in the live FDT, excluding
all reservations and live shim/stack/FDT/initrd objects. A loader refusal,
return or shim exception gets a bounded USB log window and reset, without
pstore or normal peripheral-probe fallthrough.

Build inputs stay outside Git:

```sh
python3 tools/oriole_ramprobe.py --kernel LOCAL_KERNEL --out LOCAL_DIRECTORY
shim/build.sh --board oriole --avb --xnu-ramprobe LOCAL_DIRECTORY/oriole-payload.bin
```

Run focused tests and check-all, independently review, commit on local wip,
then rebuild this exact profile after the gate (which overwrites shim/out).
Verify image provenance, exact packaged payload and unlocked serial-specific
oriole before temporary fastboot boot. Generic oriole --boot-xnu stays closed.

## Transfer-boundary load check

The first a181884 temporary boot was accepted by fastboot, but no native
XNU execution evidence or automatic return was obtained. No screen report
was available at the time of this note. Android subsequently reconnected;
ro.boot.bootreason reported watchdog,apc,early. Whether the human pressed
buttons is unknown. No native execution milestone is inferred from this.

The opt-in --xnu-loadcheck profile uses the same fixed payload and loader
guards, copies every segment, builds boot_args, logs JUMP, then intentionally
returns before the CPU branch. The existing fallback USB gadget starts only
after this return, replays the RAM log and resets. It does not test kernel
execution. This avoids relying on best-effort USB stop before XNU: the
current gadget stop API cannot positively prove controller quiescence.
The rejected pre-jump USB draft was never booted.

Observed on hardware2026-10-24,9181290: the loader check completed all11
segment copies, boot_args and JUMP0x881493488; the intentional-return marker
and592bytes were received over USB, and Android returned. See
hardware/loadcheck-2026-10-24.txt. The approximately61s pre-USB path plus
30s USB window and18s to Android kernel startup explains the elapsed time.
The reset chain intentionally uses a CL0 WDT if both PSCI reset calls return;
watchdog classification therefore does not prove an independent timer.
No headless/display-removal change was made. NativeXNU remains unverified.

## Observed reset protocol candidate (not yet run)

--xnu-resetcheck implies the same fixed payload and no-entry loadcheck.
After validated fallback USB is configured with DTR, it reads SYSIP_DAT0,
issues the existing REBOOT_BL SMC write0xfc, records full return/readback,
and requires return0 plus successful0xfc readback. It drains the log for8s
with USB serviced and requires USB still ready before SWRESET_SYSTEM=2.
If reset returns, it logs/drains again and uses ordinary USBfinish/reset.
No USB controller is handed to XNU. The two volatile command/value pairs
are allowlisted again in the shim wrapper; no flash/misc write is involved.
Other RAM profile selections and all existing prohibited mixes are refused.

The addresses match the current vendor_boot pixel-reboot node (source
image SHA256f06ab190accef4f96e7504adbc7076612a07fcfe08694190f5c1a786b3c41db0):
PMU17460000, reboot-cmd-offset810, swreset-system-offset3a00/trigger2.
Prior bluejay acceptance is a reference observation, not proof onOriole.
The actual C protocol is host-tested with no host, read failures, bad
readback, bad SMC return, disconnect during drain and accepted exact writes.

Resetcheck build audit: source hook/profile placement, protocol source,
GCC16.2 protocol opcode stream, external relocation call order, stack-only
stores, undefined symbols, and the exact19-opcode writer (object+ELF) are
pinned. Every non-reset profile must omit all resetcheck symbols. Compiler
variation fails closed and requires independent review; the audit is not
a generic compiler portability promise. Mutation tests exercise the source
and compiled guards. Official Google reboot source corroborates the mode
and SMC sequence:
https://android.googlesource.com/kernel/google-modules/power/reset/+/refs/heads/android-gs-raviole-android14-release/exynos-gs101-reboot.c
The Android driver also performs ACPM coordination, which this isolated
experiment deliberately does not add; success on current firmware remains
a measured outcome rather than an assumption.
