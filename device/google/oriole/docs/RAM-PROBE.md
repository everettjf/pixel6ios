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
