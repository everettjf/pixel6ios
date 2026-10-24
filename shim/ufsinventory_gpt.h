#pragma once
#include <stdint.h>
/* UEFI2.10 section5.3: GPT header/partition layout and IEEE CRC32.
 * This experiment deliberately supports only 4KiB sectors and <=128 entries. */
struct ufsi_gpt { uint64_t table, first, last; uint32_t count, crc, bytes, blocks; };
static inline uint32_t ufsi_le32(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static inline uint64_t ufsi_le64(const uint8_t *p)
{ return ufsi_le32(p) | (uint64_t)ufsi_le32(p+4)<<32; }
static inline uint32_t ufsi_crc(const uint8_t *p, unsigned n, int header)
{
    uint32_t crc=~0u;
    for (unsigned i=0; i<n; i++) {
        crc ^= header && i>=16 && i<20 ? 0 : p[i];
        for (unsigned k=0; k<8; k++) crc=crc>>1 ^ (0xedb88320u & -(crc&1));
    }
    return ~crc;
}
static inline int ufsi_gpt_header(const uint8_t *p, uint32_t capacity_last, struct ufsi_gpt *g)
{
    const char sig[]="EFI PART";
    for (unsigned i=0;i<8;i++) if(p[i]!=(uint8_t)sig[i]) return 0;
    uint32_t hs=ufsi_le32(p+12);
    if(ufsi_le32(p+8)!=0x10000 || hs<92 || hs>4096 || ufsi_le32(p+20) ||
       ufsi_crc(p,hs,1)!=ufsi_le32(p+16) || ufsi_le64(p+24)!=1 ||
       ufsi_le64(p+32)!=capacity_last) return 0;
    g->first=ufsi_le64(p+40); g->last=ufsi_le64(p+48);
    g->table=ufsi_le64(p+72); g->count=ufsi_le32(p+80); g->crc=ufsi_le32(p+88);
    if(!g->count || g->count>128 || ufsi_le32(p+84)!=128 ||
       g->first<2 || g->first>g->last || g->last>=capacity_last) return 0;
    g->bytes=g->count*128; g->blocks=(g->bytes+4095)/4096;
    return g->table>=2 && g->table<g->first && g->blocks<=g->first-g->table &&
        g->blocks<=capacity_last-g->last-1;
}
static inline int ufsi_gpt_userdata(const uint8_t *p, const struct ufsi_gpt *g,
    uint64_t *first, uint64_t *last)
{
    if(ufsi_crc(p,g->bytes,0)!=g->crc) return 0;
    unsigned matches=0;
    for(unsigned i=0;i<g->count;i++) {
        const uint8_t *e=p+i*128; unsigned used=0;
        for(unsigned j=0;j<16;j++) used|=e[j];
        if(!used) continue;
        uint64_t a=ufsi_le64(e+32), b=ufsi_le64(e+40);
        if(a<g->first || a>b || b>g->last) return 0;
        for(unsigned j=0;j<i;j++) {
            const uint8_t *q=p+j*128; unsigned prior=0;
            for(unsigned k=0;k<16;k++) prior|=q[k];
            if(prior && a<=ufsi_le64(q+40) && ufsi_le64(q+32)<=b) return 0;
        }
        const char name[]="userdata"; unsigned match=1;
        for(unsigned j=0;j<9;j++)
            if(e[56+2*j]!=(uint8_t)name[j] || e[57+2*j]) match=0;
        if(match) { *first=a; *last=b; matches++; }
    }
    return matches==1;
}
