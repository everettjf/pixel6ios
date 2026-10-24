/* Read-only GS101 RDMA inventory. No framebuffer or MMIO stores.
 * Register source: Google display commit 661047c0c1c4939aa81fcc822bb21dc5a484f913,
 * samsung/cal_9845/regs-dpp.h: RDMA(L0~L5), DMA_SHD_OFFSET, RDMA_ENABLE,
 * RDMA_IN_CTRL_0, RDMA_SRC_SIZE/OFFSET, RDMA_IMG_SIZE, RDMA_BASEADDR_Y8,
 * RDMA_SRC_STRIDE_0/1. Base/stride also match current vendor_boot drmdpp0..5.
 * See soc/google/gs101/docs/display-inventory.md. A fault stops that channel.
 */
#include <stdint.h>
#include "console.h"
int try_read32(uintptr_t address, uint32_t *value);

void gs101_display_inventory(void)
{
    const unsigned offsets[] = { DISPLAY_INV_REG_OFFSETS };
    con_str("DISPLAY inventory", "read only; no clocks or triggers changed");
    for (unsigned ch = 0; ch < DISPLAY_INV_RDMA_COUNT; ch++) {
        uintptr_t base = DISPLAY_INV_RDMA_BASE + ch * DISPLAY_INV_RDMA_STRIDE;
        con_hex("RDMA channel", ch);
        int fault = 0;
        for (unsigned shadow = 0; shadow < 2 && !fault; shadow++) {
            for (unsigned n = 0; n < sizeof(offsets) / sizeof(offsets[0]); n++) {
                uintptr_t address = base + shadow * DISPLAY_INV_SHADOW_OFFSET + offsets[n];
                uint32_t value;
                if (!try_read32(address, &value)) {
                    con_hex("RDMA read fault", address);
                    fault = 1;
                    break;
                }
                con_hex2("RDMA", "address=", address, "value=", value);
            }
        }
    }
}
