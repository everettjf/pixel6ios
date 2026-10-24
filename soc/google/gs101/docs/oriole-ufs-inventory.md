# Oriole UFS inventory — UNVERIFIED on hardware

OBSERVED: inventory-2026-10-24.txt proves0x880000000+0x80000000 is DRAM,
and display-2026-10-24.txt proves the framebuffer configuration. No UFS DMA
or GPT result has been observed yet.

SOFTWARE ALLOCATION: board.json reserves a128KiB experiment window at
0x880100000, inside that measured2GiB bank: UTRL+0 (1024B), UCD+0x1000
(1056B), data+0x4000 (8KiB), GPT entries+0x10000 (16KiB). Every buffer
fits with independent alignment/size assertions. This is not a peripheral
address. The experiment resets before loading any XNU, so no kernel is
resident there. No arbitrary environment override is allowed.

READ FROM SOURCE: the existing cold init is soc/google/gs101/shim/ufsinit.c
and its cited docs/07-gs101-ufs-bringup.md + docs/08-abl-ufs-shutdown.md.
It configures volatile clocks/host/PHY/UniPro, not storage blocks. The
existing shim/ufs.c doorbell-time UPIU/CDB allowlist is unchanged. A fresh
live FDT must prove the complete scratch range lies in DRAM and outside
all reserved ranges, live image/stacks, FDT and initrd BEFORE cold init.
The USB pool is necessarily inside the excluded live ABL reservation.
The legacy vendor survey is skipped because gated PHY reads can hang.

READ FROM SOURCE: GPT layout/CRC follow UEFI2.10 section5.3:
https://uefi.org/specs/UEFI/2.10/05_GUID_Partition_Table_Format.html
The same field offsets and CRC32 with zeroed header-CRC field were cross-checked against Linuxv6.12 block/partitions/efi.h and efi.c (https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux/+/refs/tags/v6.12/block/partitions/). Only LUN0 and4KiB blocks are supported. Capacity must answer first. Header
signature/revision/size/CRC/current/alternate LBAs and usable/table ranges
are checked before reading entries. Entries are capped at128 of128bytes,
CRC checked, and each used partition must be in-range and nonoverlapping.
Exactly one UTF16 userdata name must exist, with length matching the
serial-specific fastboot observation0x1b91215000. Only capacity and GPT
metadata are read; no media write, query command or userdata content dump.

UNVERIFIED: current firmware's cold-init behavior, high-bank DMA/S2MPU
acceptance, valid GPT bounds and reset after a UFS failure. The bounded
polled paths may still stop on an unrecoverable hardware bus hang. Do not
infer XNU/iOS readiness or flash userdata merely from a successful build.

On every normal/error return, the caller clears and bounded-verifies UTRLDBR,
stops UTRLRSR and verifies it. A failed cleanup requests immediate reset,
without keeping the USB window open. The panic path uses the same guarded
cleanup; recursive panic resets immediately. UTRLRDY is polled with100ms
bound after list start before issuing the first doorbell.
