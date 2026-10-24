# Pixel 6 (oriole): inventory bring-up

Status: OBSERVED ON HARDWARE 2026-10-24: headless inventory booted twice, USB log captured, returned automatically to Android. XNU has not run.

The device is GS101 with an unlocked slider-17.0-15199431 bootloader and Android
17 CP2A.260705.006. Current vendor_boot was fetched read-only and its first DTB
declares abl@f8800000 with size 0x2000000 (32 MiB). No device identifiers or
firmware are committed.

Only `shim/build.sh --board oriole --inventory --avb` is accepted. This mode
uses RAM/USB logging, no framebuffer/UART, no pstore, no storage, and no
secondary CPU, PMIC, touch, GPU, WLAN or DVFS experiments. USB must reuse the
live ABL event-buffer reservation and the existing overlap checks; a fixed
high-DMA override is rejected. Default USB window: 30 seconds, maximum: 60.

The source-candidate framebuffer/touch fields support the existing host
fixtures and are not enabled by inventory. Four 2 GiB DRAM banks and a 16 MiB live ABL reservation were measured (hardware/inventory-2026-10-24.txt). Static vendor_boot declares 32 MiB, so the live checks are essential. XNU RAM remains deliberately unconfigured until framebuffer measurement.

Reviewed independently with no remaining blocking source findings; negative
gate tests are in tools/test_oriole_inventory.py. The next opt-in --inventory-display reader samples RDMA configuration only, without writes or clock changes; see soc/google/gs101/docs/display-inventory.md. Its hardware result is pending.
