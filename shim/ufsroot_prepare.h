#pragma once
#include <stdint.h>
/* HCI offsets: existing shim/ufs.c; GS101 cold init: soc/google/gs101/shim/ufsinit.c.
 * CP3A inventory measured HCI base14700000, version300 and64AS. No new DMA
 * list or media command is created here. Only RSR=0 is representable. */
#define UR_HCI 0x14700000UL
#define UR_CAP (UR_HCI+0x00)
#define UR_VER (UR_HCI+0x08)
#define UR_HCS (UR_HCI+0x30)
#define UR_HCE (UR_HCI+0x34)
#define UR_DBR (UR_HCI+0x58)
#define UR_RSR (UR_HCI+0x60)
int ufsroot_hw_read(uintptr_t pa,uint32_t *value);
int ufsroot_hw_write(uintptr_t pa,uint32_t value);
void ufsroot_wait_ms(unsigned ms);
int ufsroot_cold_init(void);

static inline int urs_quiet(void)
{
    uint32_t dbr,rsr;
    /* A foreign request must never be cleared or assigned to our ownership. */
    if (!ufsroot_hw_read(UR_DBR,&dbr) || dbr ||
        !ufsroot_hw_read(UR_RSR,&rsr)) return 0;
    if (rsr&1) {
        if (!ufsroot_hw_write(UR_RSR,0)) return 0;
        unsigned i;
        for (i=0;i<100;i++) {
            if (!ufsroot_hw_read(UR_RSR,&rsr)) return 0;
            if (!(rsr&1)) break;
            ufsroot_wait_ms(1);
        }
        if (i==100) return 0;
    }
    return ufsroot_hw_read(UR_DBR,&dbr) && !dbr &&
        ufsroot_hw_read(UR_RSR,&rsr) && !(rsr&1);
}

static inline int urs_stop(volatile unsigned *active)
{
    if (!*active) return 1;
    /*2 means preparation saw unknown/foreign state before taking ownership.
     * Reset directly; neither cleanup MMIO nor fallback USB is allowed. */
    if (*active!=1) return 0;
    if (!urs_quiet()) return 0;
    *active=0;
    return 1;
}

static inline int urs_prepare(volatile unsigned *active)
{
    uint32_t dbr,rsr,hce,hcs,cap,ver;
    /* Refuse stale activity BEFORE the existing cold-init reset writes. */
    unsigned prior=*active;
    *active=2; /* attempted but not yet proved safe: reset-only on refusal */
    if (prior || !ufsroot_hw_read(UR_DBR,&dbr) || dbr ||
        !ufsroot_hw_read(UR_RSR,&rsr) || (rsr&1)) return 0;
    *active=1;
    if (ufsroot_cold_init()!=0 || !urs_quiet()) return 0;
    return ufsroot_hw_read(UR_HCE,&hce) && (hce&1) &&
        ufsroot_hw_read(UR_HCS,&hcs) && (hcs&1) &&
        ufsroot_hw_read(UR_CAP,&cap) && (cap&(1u<<24)) &&
        ufsroot_hw_read(UR_VER,&ver) && ver==0x300;
}
