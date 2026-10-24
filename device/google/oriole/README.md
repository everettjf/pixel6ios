# Pixel 6 (oriole): inventory bring-up

Status: host build and object audits passed on 2026-10-24; first hardware run pending.

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
fixtures and are not enabled by inventory. Physical DRAM bank sizes and XNU
RAM remain deliberately unconfigured until a live-FDT report is captured.

Reviewed independently with no remaining blocking source findings; negative
gate tests are in tools/test_oriole_inventory.py. Hardware behavior is unknown.
