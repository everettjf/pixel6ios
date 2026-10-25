#pragma once
#include <stdint.h>
/* HCI offsets: existing shim/ufs.c. CP3A inventory measured an already-ready
 * host: HCE1, DP1, version300, 64AS, DBR0. UTRLRSR may be 0 or 1: bit0
 * runs the list, while DBR records outstanding requests. XNU checks DBR0,
 * stops the foreign list and verifies stop before programming its own base.
 * This shim preflight only reads; it does not change either list. */
#define UR_HCI 0x14700000UL
#define UR_CAP (UR_HCI+0x00)
#define UR_VER (UR_HCI+0x08)
#define UR_HCS (UR_HCI+0x30)
#define UR_HCE (UR_HCI+0x34)
#define UR_DBR (UR_HCI+0x58)
#define UR_RSR (UR_HCI+0x60)
int ufsroot_hw_read(uintptr_t pa,uint32_t *value);

/* Diagnostic code 1..8 identifies the check; bit 8 means its MMIO read
 * faulted. Values are copied only from successful reads. */
struct urs_diag { uint32_t code, value; };

static inline int urs_checked_read(uintptr_t pa,uint32_t *value,
                                   struct urs_diag *diag,uint32_t code)
{
    diag->code=code|0x100;
    diag->value=0;
    if (!ufsroot_hw_read(pa,value)) return 0;
    diag->code=code;
    diag->value=*value;
    return 1;
}

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

static inline int urs_prepare(volatile unsigned *active,struct urs_diag *diag)
{
    uint32_t dbr,rsr,hce,hcs,cap,ver;
    /* Refuse stale activity; never write UFS registers in the shim. */
    unsigned prior=*active;
    *active=2; /* attempted but not yet proved safe: reset-only on refusal */
    diag->code=0;diag->value=prior;
    if (prior || !urs_checked_read(UR_DBR,&dbr,diag,1) || dbr ||
        !urs_checked_read(UR_RSR,&rsr,diag,2) || rsr>1) return 0;
    uint32_t first_rsr=rsr;
    if (!urs_checked_read(UR_HCE,&hce,diag,3) || !(hce&1) ||
        !urs_checked_read(UR_HCS,&hcs,diag,4) || !(hcs&1) ||
        !urs_checked_read(UR_CAP,&cap,diag,5) || !(cap&(1u<<24)) ||
        !urs_checked_read(UR_VER,&ver,diag,6) || ver!=0x300 ||
        !urs_checked_read(UR_DBR,&dbr,diag,7) || dbr ||
        !urs_checked_read(UR_RSR,&rsr,diag,8) || rsr!=first_rsr) return 0;
    *active=1;
    diag->code=9;diag->value=0;
    return 1;
}

static inline int urs_handoff(volatile unsigned *active)
{
    if (*active!=1) return 0;
    *active=2; /* XNU may now program request lists; shim must only reset. */
    return 1;
}
