#pragma once
#include <stdint.h>
#include "fdt.h"

struct ufsi_avoid { uint64_t base, size; };
/* Pure range policy: no DMA until a complete live map proves this software
 * scratch allocation lies in DRAM, outside every reservation and live object. */
static inline int ufsi_range_free(const struct fdt_memmap *m, uint64_t base,
    uint64_t size, const struct ufsi_avoid *avoid, unsigned n)
{
    if (!size || base + size < base || !m->n_banks || m->n_banks>FDT_MAX_BANKS ||
        m->n_reserved>FDT_MAX_RESERVED || m->n_reserved_dropped)
        return 0;
    int bank = 0;
    for (unsigned i=0; i<m->n_banks; i++) {
        uint64_t b=m->banks[i].base, s=m->banks[i].size;
        if (s && b+s>=b && base>=b && base+size<=b+s) bank=1;
    }
    if (!bank) return 0;
    for (unsigned i=0; i<m->n_reserved; i++) {
        uint64_t b=m->reserved[i].base, s=m->reserved[i].size;
        if (s && (b+s<b || (base<b+s && b<base+size))) return 0;
    }
    for (unsigned i=0; i<n; i++) {
        uint64_t b=avoid[i].base, s=avoid[i].size;
        if (s && (b+s<b || (base<b+s && b<base+size))) return 0;
    }
    return 1;
}
