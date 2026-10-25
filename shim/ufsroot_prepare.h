#pragma once
#include <stdint.h>
/* HCI offsets: existing shim/ufs.c. CP3A inventory measured an already-ready
 * host: HCE1, DP1, version300, 64AS, DBR0 and RSR0. This preflight is only
 * reads; neither a cold reset nor a new DMA list is needed before XNU. */
#define UR_HCI 0x14700000UL
#define UR_CAP (UR_HCI+0x00)
#define UR_VER (UR_HCI+0x08)
#define UR_HCS (UR_HCI+0x30)
#define UR_HCE (UR_HCI+0x34)
#define UR_DBR (UR_HCI+0x58)
#define UR_RSR (UR_HCI+0x60)
int ufsroot_hw_read(uintptr_t pa,uint32_t *value);

static inline int urs_quiet(void)
{
    uint32_t dbr,rsr;
    /* A foreign request must never be cleared or assigned to our ownership. */
    if (!ufsroot_hw_read(UR_DBR,&dbr) || dbr ||
        !ufsroot_hw_read(UR_RSR,&rsr)) return 0;
    return !(rsr&1);
}

static inline int urs_stop(volatile unsigned *active)
{
    if (!*active) return 1;
    /* 2 means unknown/foreign state or ownership transferred to XNU.
     * Reset directly; neither cleanup MMIO nor fallback USB is allowed. */
    if (*active!=1) return 0;
    if (!urs_quiet()) return 0;
    *active=0;
    return 1;
}

static inline int urs_prepare(volatile unsigned *active)
{
    uint32_t dbr,rsr,hce,hcs,cap,ver;
    /* Refuse stale activity; never write UFS registers in the shim. */
    unsigned prior=*active;
    *active=2; /* attempted but not yet proved safe: reset-only on refusal */
    if (prior || !ufsroot_hw_read(UR_DBR,&dbr) || dbr ||
        !ufsroot_hw_read(UR_RSR,&rsr) || (rsr&1)) return 0;
    if (!(ufsroot_hw_read(UR_HCE,&hce) && (hce&1) &&
        ufsroot_hw_read(UR_HCS,&hcs) && (hcs&1) &&
        ufsroot_hw_read(UR_CAP,&cap) && (cap&(1u<<24)) &&
        ufsroot_hw_read(UR_VER,&ver) && ver==0x300 &&
        urs_quiet())) return 0;
    *active=1;
    return 1;
}

static inline int urs_handoff(volatile unsigned *active)
{
    if (*active!=1) return 0;
    *active=2; /* XNU may now program request lists; shim must only reset. */
    return 1;
}
