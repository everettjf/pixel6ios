#pragma once
#include "payload_layout.h"

/* Software layout of the exact reviewed payload (oriole_ramprobe.py), not
 * hardware guesses. RAM bank observed in inventory-2026-10-24.txt. */
static inline int rp_inside(uint64_t off, uint64_t len, uint64_t limit)
{
    return off <= limit && len <= limit-off;
}

static inline int ramprobe_payload_ok(const struct payload *p, uint64_t available)
{
    const uint64_t size=16726576, vb=0xfffffe0006000000ULL;
    if (available < size || p->version!=1 || p->nsegs!=11 ||
        p->virt_base!=vb || p->phys_base!=0x880000000ULL ||
        p->mem_size!=0x80000000ULL || p->entry_va!=0xfffffe0007493488ULL ||
        p->kernel_end!=0xfffffe0008730000ULL || (p->adt_off&7) ||
        !p->adt_size || p->adt_size>0x10000 ||
        !rp_inside(p->adt_off,(p->adt_size+7)&~7ULL,size)) return 0;
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
        if (n>s->vmsize || !rp_inside(s->file_off,n,size) ||
            s->file_off<0x2a8+11*32 ||
            !rp_inside(dst,s->vmsize,end)) return 0;
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
