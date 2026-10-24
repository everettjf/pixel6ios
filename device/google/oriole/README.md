# Pixel 6 (oriole): inventory bring-up

Status: OBSERVED ON HARDWARE 2026-10-24: headless inventory booted twice, USB log captured, returned automatically to Android. XNU has not run.

The device is GS101 with an unlocked slider-17.0-15199431 bootloader and Android
17 CP2A.260705.006. Current vendor_boot was fetched read-only and its first DTB
declares abl@f8800000 with size 0x2000000 (32 MiB). No device identifiers or
firmware are committed.

`--inventory` and opt-in `--inventory-display` collect read-only observations. These modes
use RAM/USB logging, no framebuffer/UART, no pstore, no storage, and no
secondary CPU, PMIC, touch, GPU, WLAN or DVFS experiments. USB must reuse the
live ABL event-buffer reservation and the existing overlap checks; a fixed
high-DMA override is rejected. Default USB window: 30 seconds, maximum: 60.

The source-candidate framebuffer/touch fields support the existing host
fixtures and are not enabled by inventory. Four 2 GiB DRAM banks and a 16 MiB live ABL reservation were measured (hardware/inventory-2026-10-24.txt). Static vendor_boot declares 32 MiB, so the live checks are essential. RDMA0 and shadow now confirm the framebuffer source candidate at 0xfac00000,1080x2400. The first high2GiB bank is selected for the next single-core XNU probe.

Reviewed independently with no remaining blocking source findings; negative
gate tests are in tools/test_oriole_inventory.py. The next opt-in --inventory-display reader samples RDMA configuration only, without writes or clock changes; see soc/google/gs101/docs/display-inventory.md. All96 RDMA reads succeeded; see hardware/display-2026-10-24.txt.


XNU remains gated off pending storage/DMA bring-up. No XNU image has booted.


--inventory-ufs is the next, UNVERIFIED hardware stage. It uses a fixed,
live-map-validated128KiB scratch allocation at0x880100000 in the first high
bank. Existing GS101 cold-init writes only volatile controller/PHY state;
existing doorbell allowlist still rejects every media-writing command.
The legacy vendor/PHY survey is skipped. Capacity and CRC-validated GPT
metadata are read; userdata contents are not dumped. No arbitrary DMA,
reset-mode or peripheral overrides are accepted. A synchronous panic emits
the RAM log through the bounded gadget and resets, without pstore/pager.
See soc/google/gs101/docs/oriole-ufs-inventory.md. XNU remains disabled.
