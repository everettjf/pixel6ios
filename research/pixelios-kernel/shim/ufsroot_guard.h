#pragma once
#include "payload_layout.h"

/* Software layout of the dedicated storage-root payload (oriole_ufsroot.py), not
 * hardware guesses. RAM bank observed in inventory-2026-10-24.txt. */
static inline int ur_inside(uint64_t off, uint64_t len, uint64_t limit)
{
    return off <= limit && len <= limit-off;
}

static inline int ufsroot_payload_ok(const struct payload *p, uint64_t available)
{
#ifdef ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_HID_REMATCH_0131
    /* The 0131 profile has a separately checked payload and shim. */
    const uint64_t size=16753872;
    const uint64_t kernel_end=0xfffffe0008730000ULL;
    const uint64_t entry_va=0xfffffe0007497488ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_HID_DIAG_0128)
    /* Exact 0128 HID bridge diagnostic payload; entry and end match 0127. */
    const uint64_t size=16753760;
    const uint64_t kernel_end=0xfffffe0008730000ULL;
    const uint64_t entry_va=0xfffffe0007497488ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETIF_0126)
    /* Exact offline-audited 0126 IORegistry trial; entry moved with __TEXT_EXEC. */
    const uint64_t size=16753584;
    const uint64_t kernel_end=0xfffffe0008730000ULL;
    const uint64_t entry_va=0xfffffe0007497488ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETROUTE_RESOURCE_0125)
    /* Exact offline-audited resource-observation payload. */
    const uint64_t size=16713744;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETROUTE_0124)
    /* Exact offline-audited 0124 USB-route payload; other profiles stay fixed. */
    const uint64_t size=16730160;
    const uint64_t kernel_end=0xfffffe000872c000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_GUI_0121)
    /* Exact 0121 HID event-metadata payload; keep 0120's bound separate. */
    const uint64_t size=16713664;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_GUI)
    /* Exact 0120 bounded physical-touch trial with full iOS root. */
    const uint64_t size=16716864;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID_SYSINFO)
    /* Exact 0119 bounded scan plus read-only controller system-info sample. */
    const uint64_t size=16716832;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID_RAILHOLD)
    /* Exact 0117/0118 bounded rail-hold scan payloads. */
    const uint64_t size=16716800;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID_RAILCYCLE)
    /* Exact 0116 rail-cycle payload; all previous profiles keep their cap. */
    const uint64_t size=16716768;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCHID)
    /* Oriole FTM5 identify payload layout. The selected build checker pins
     * its exact bytes; never widen other payload profiles. */
    const uint64_t size=16716528;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP)
    /* Exact 0109 panel-snapshot payload. Other COW profiles retain their cap. */
    const uint64_t size=16714672;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_POOL)
    /* Exact 0107 preallocated COW payload; previous profiles stay pinned. */
    const uint64_t size=16714528;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW_TRACE)
    /* Exact 0106 diagnostic payload; the original COW limit remains fixed. */
    const uint64_t size=16714368;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#elif defined(ORIOLE_UFSROOT_COW)
    /* Exact RAM-COW payload from oriole_ufsroot_cow.py. The original root
     * profile remains pinned to its independently checked payload length. */
    const uint64_t size=16714240;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#else
    const uint64_t size=16713568;
    const uint64_t kernel_end=0xfffffe0008728000ULL;
#endif
    const uint64_t vb=0xfffffe0006000000ULL;
#if !defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_NETIF_0126) && !defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_HID_DIAG_0128) && !defined(ORIOLE_UFSROOT_COW_POOL512_FBSNAP_TOUCH_HID_REMATCH_0131)
    const uint64_t entry_va=0xfffffe0007493488ULL;
#endif
    if (available < size || p->version!=1 || p->nsegs!=10 ||
        p->virt_base!=vb || p->phys_base!=0x880000000ULL ||
        p->mem_size!=0x80000000ULL || p->entry_va!=entry_va ||
        p->kernel_end!=kernel_end || (p->adt_off&7) ||
        !p->adt_size || p->adt_size>0x10000 ||
        !ur_inside(p->adt_off,(p->adt_size+7)&~7ULL,size)) return 0;
    uint64_t end=p->kernel_end-vb;
    /* ADT plus alignment and one complete boot_args page inside DRAM. */
    uint64_t top=((end+p->adt_size+0x3fff)&~0x3fffULL)+0x4000;
    if (top>p->mem_size) return 0;
    int entry=0;
    for (unsigned i=0;i<p->nsegs;i++) {
        const struct payload_seg *s=&p->segs[i];
        if (s->file_size>size || s->vmaddr<vb || (s->vmaddr&7) ||
            (s->file_off&7) || (s->vmsize&7)) return 0;
        uint64_t n=(s->file_size+7)&~7ULL, dst=s->vmaddr-vb;
        if (n>s->vmsize || !ur_inside(s->file_off,n,size) ||
            s->file_off<0x2a8+10*32 ||
            !ur_inside(dst,s->vmsize,end)) return 0;
        if (p->entry_va>=s->vmaddr && p->entry_va-s->vmaddr<s->file_size)
            entry=1;
        for (unsigned j=0;j<i;j++) {
            const struct payload_seg *t=&p->segs[j];
            if (s->vmaddr<t->vmaddr+t->vmsize &&
                t->vmaddr<s->vmaddr+s->vmsize) return 0;
        }
    }
    return entry;
}
