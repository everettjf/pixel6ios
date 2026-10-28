# 32 — Oriole BCM4389 reference and the next PCIe evidence gate

Status: source research only, 2026-10-27. No Oriole Wi-Fi hardware run or
iOS Wi-Fi scan is claimed here. The existing `WIFI-COVERAGE.md` A1–A5 device
observations are from **bluejay**; the target of the current iOS GUI trial is
**oriole**. Sharing GS101 does not transfer a Bluejay device result to Oriole.

## Pinned sources

- **Read from source:** Google's [GS101 PCIe device tree](https://android.googlesource.com/kernel/devices/google/gs101/+/f87212fc996b154b017736e5cd5497a943b82166/dts/gs101-pcie.dtsi#57)
  defines HSI2 `pcie_1` with DBI `0x14800000`, configuration window
  `0x60FFE000`, and a non-prefetchable memory range beginning at
  `0x60000000` with size `0xFF0000` (lines 57–80). It names the interrupt
  `IRQ_PCIE_GEN4A_1_HSI2`; this document does not substitute a numeric GIC
  interrupt without a pinned header and Oriole measurement.
- **Read from source:** the community [Raviole BCM4389 port at
  `43de0a21afd3`](https://github.com/m8l8th814n-eng/raviole_bcmd_postmarketos/tree/43de0a21afd3f5265038c493e93c548eddb9ee49)
  contains a Linux GS101 root-complex implementation and a port of Google's
  `bcmdhd` driver. Its [PCIe Linux attach path](https://github.com/m8l8th814n-eng/raviole_bcmd_postmarketos/blob/43de0a21afd3f5265038c493e93c548eddb9ee49/bcmdhd/dhd_pcie_linux.c#L1947-L1956)
  enables the endpoint, sets it bus master, maps resource 0 as registers,
  and maps resource 2 as TCM/backplane memory. Those are PCI resource
  **indices**, not raw BAR addresses. The author's README reports Wi-Fi
  association and traffic on Oriole under Linux; that is an external report,
  not an observation on our XNU build.
- **Read from source:** the same port's [Kconfig](https://github.com/m8l8th814n-eng/raviole_bcmd_postmarketos/blob/43de0a21afd3f5265038c493e93c548eddb9ee49/bcmdhd/Kconfig#L88-L101)
  names `/vendor/etc/wifi/fw_bcmdhd.bin` and `/vendor/etc/wifi/bcmdhd.cal` as
  default firmware and NVRAM paths. The port's own Kbuild overrides these
  for postmarketOS `/lib/firmware`. For our Pixel 6, paths and file hashes
  must be measured from the installed Android build or its matching factory
  image; neither firmware nor calibration belongs in Git.
- **Read from source:** Linux's [PCI BAR sizing code](https://android.googlesource.com/kernel/common/+/8c89d3ad3095808ac130c535ad7ed3d1344d5986/drivers/pci/probe.c)
  saves the command register, disables decode while sizing, probes the BAR
  masks, and restores decode. This is the model for a future bounded
  experiment, not permission to write configuration space today.

## What the current evidence permits

**Observed on bluejay, 2026-10-23:** the W3a S27 run read a BCM4389-family
endpoint at vendor `0x14E4`, device `0x4441`; BAR0 and BAR2 currently read
as `0x4` (64-bit memory BARs, unassigned). The host-side table refuses every
CFG write and every iATU region-1 write. No BAR size has been measured.
The endpoint configuration dump and its teardown are described in
`docs/reviews/wlan-stage1-review-8.md` and `docs/WIFI-COVERAGE.md`.

**Inference for Oriole, unverified:** the same GS101 HSI2 range and BCM4389
driver path are likely useful, but board power, endpoint identity, BAR sizes,
firmware revision, and interrupt routing must be verified on the Oriole.
In particular, do not allocate BAR0 or BAR2 merely from the unassigned
`0x4` readback. A value of `0x4` identifies the BAR type, not its size.

## Next evidence gate toward iOS networking

1. In a **read-only Oriole** diagnostic, identify the HSI2 PCIe link and
   endpoint; compare exact IDs, command register, BAR0–BAR3, and iATU reset
   values with the Bluejay record. Stop if the endpoint or firmware baseline
   differs. This has not been built or run.
2. Before any first CFG writer, pin the relevant Google/PCI source revision
   and review a transaction that saves command and all BAR dwords; disables
   memory and I/O decode; sizes both 64-bit BAR pairs with bounded readbacks;
   restores every original value in reverse order even on a refused/faulted
   path; and proves the final register state matches the entry state.
   Treat a failed restore as an unsafe run. Independently review the source
   and compiled object before a temporary boot, per `shim/AGENTS.md`.
3. Only after measured sizes fit the HSI2 `0x60000000..0x60FEFFFF` aperture,
   design a separate, reviewed assignment and outbound MEM iATU experiment.
   Do not infer a BAR base from that range alone. Revalidate the endpoint
   under Oriole before enabling MEM/MASTER or reading chip registers.
4. Firmware boot and real iOS networking remain separate work: an XNU PCIe
   and BCM4389 transport, firmware/NVRAM delivery, interrupts, IO80211
   integration, scan, WPA2 join, and traffic are all unimplemented. A Linux
   port is a reference, not a drop-in XNU driver.

No change in this document alters a device, ships firmware, or asserts that
Wi-Fi works in iOS.
