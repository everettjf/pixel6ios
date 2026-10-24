# Read-only display inventory

READ FROM SOURCE: Google display module commit
[661047c0c1c4939aa81fcc822bb21dc5a484f913](https://android.googlesource.com/kernel/google-modules/display/+/661047c0c1c4939aa81fcc822bb21dc5a484f913/samsung/cal_9845/regs-dpp.h).
RDMA L0..L5 base is 0x1c0b0000, spacing 0x1000. The current fetched
vendor_boot_a DTB agrees (drmdpp0..5 DMA reg). Shadow offset is 0x400.
Read offsets: ENABLE 0x00, IN_CTRL_0 0x08, SRC_SIZE 0x10,
SRC_OFFSET 0x14, IMG_SIZE 0x18, BASEADDR_Y8 0x40, SRC_STRIDE_0 0x50,
SRC_STRIDE_1 0x54. These are configuration registers, not interrupt-clear
or FIFO registers. soc.json is the source of all numeric read addresses.

UNVERIFIED on Oriole until a capture: configuration values and whether
all RDMA blocks remain readable after ABL. A synchronous fault skips the
rest of that channel. There are six channels, two banks and eight offsets;
no waits, no writes, no clock/trigger/DSIM actions. Only opt-in
--inventory-display links this reader. Ordinary inventory is unchanged.

The extra generated macros intentionally affect GS101 headers; existing
non-inventory image code has no references to them. This does not enable
a display or grant permission to write the candidate framebuffer.
