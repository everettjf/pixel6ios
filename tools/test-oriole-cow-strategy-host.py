"""Offline host harness for a patched sweet_ufs.c (pass --source for CI artifacts).

The public repository stores XNU as numbered patches, so this focused harness
accepts a prepared patched source tree and executes its actual strategy body.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/pixelios-kernel"))
from tools.test_oriole_cow import cow_source

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path,
                    default=ROOT / "artifacts/fullroot-kernel/source/bsd/dev/sweet_ufs.c")
args = parser.parse_args()
source = args.source.read_text()
start = source.index("static void\nsweet_ufs_strategy(buf_t bp)\n")
end = source.index("\nstatic int\nsweet_ufs_ioctl", start)
strategy = source[start:end]

head = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#define UFS_BLOCK 4096u
#define BOUNCE_SIZE (1u << 20)
#define DMA_BOUNCE 0
#define B_READ 1
#define MIN(a,b) ((a)<(b)?(a):(b))
#define Z_NOWAIT 1
#define Z_WAITOK 4
#define Z_ZERO 2
typedef char *caddr_t;
typedef int64_t daddr64_t;
typedef struct fake_buf {
    int flags, error, finished;
    int64_t blkno;
    uint32_t count, resid;
    char *data;
} *buf_t;
struct {
    bool ready, writable, oriole_cow;
    uint64_t nblocks, first_block;
    uint32_t secsize;
    uint8_t *dma;
} su;
static int sweet_ufs_lock;
static uint8_t physical[4 * BOUNCE_SIZE], dma[BOUNCE_SIZE];
static unsigned media_reads, media_writes;
static int fail_after = -1;
static void *kalloc_data(size_t size, int flags) {
    if (fail_after == 0) return NULL;
    if (fail_after > 0) fail_after--;
    return flags & Z_ZERO ? calloc(1,size) : malloc(size);
}
static void kfree_data(void *p, size_t size) { (void)size; free(p); }
#define kalloc_type_2(type, flags) ((type *)kalloc_data(sizeof(type), flags))
#define kalloc_type_3(type, count, flags) ((type *)kalloc_data(sizeof(type)*(count),flags))
#define kalloc_type_choose(_1,_2,_3,name,...) name
#define kalloc_type(...) kalloc_type_choose(__VA_ARGS__,kalloc_type_3,kalloc_type_2)(__VA_ARGS__)
#define kfree_type(type,p) kfree_data((p),sizeof(type))
static int buf_flags(buf_t b) { return b->flags; }
static daddr64_t buf_blkno(buf_t b) { return b->blkno; }
static uint32_t buf_count(buf_t b) { return b->count; }
static void buf_setresid(buf_t b, uint32_t n) { b->resid=n; }
static int buf_map(buf_t b, caddr_t *p) { *p=b->data; return 0; }
static void buf_unmap(buf_t b) { (void)b; }
static void buf_seterror(buf_t b, int e) { b->error=e; }
static void buf_biodone(buf_t b) { b->finished++; }
static void lck_mtx_lock(int *p) { (void)p; }
static void lck_mtx_unlock(int *p) { (void)p; }
static int ufs_read_blocks(uint64_t lba, uint32_t blocks) {
    media_reads++;
    if (lba < su.first_block || blocks > BOUNCE_SIZE/UFS_BLOCK ||
        lba-su.first_block > sizeof(physical)/UFS_BLOCK-blocks) return EINVAL;
    memcpy(dma, physical+(lba-su.first_block)*UFS_BLOCK, blocks*UFS_BLOCK);
    return 0;
}
static int ufs_write_blocks(uint64_t lba, uint32_t blocks) {
    (void)lba; (void)blocks; media_writes++; abort();
}
'''

tail = r'''
static void io(int flags, int64_t sector, uint32_t count, char *data, int expected) {
    struct fake_buf b = {.flags=flags,.blkno=sector,.count=count,.data=data};
    sweet_ufs_strategy(&b);
    assert(b.finished==1 && b.error==expected);
    assert(b.resid==(expected ? count : 0));
}
int main(void) {
    su.ready=true; su.writable=true; su.oriole_cow=true;
    su.nblocks=sizeof(physical)/UFS_BLOCK; su.first_block=20;
    su.secsize=512; su.dma=dma;
    oriole_cow_buckets=calloc(ORIOLE_COW_BUCKETS,sizeof(*oriole_cow_buckets));
    assert(oriole_cow_buckets);
    memset(physical,'A',sizeof(physical));
    char write_data[1000], read_data[1500];
    memset(write_data,'Z',sizeof(write_data));
    io(0,1,sizeof(write_data),write_data,0);
    assert(physical[512]=='A' && media_writes==0 && oriole_cow_pages==1);
    memset(read_data,0,sizeof(read_data));
    io(B_READ,0,sizeof(read_data),read_data,0);
    for (int i=0;i<512;i++) assert(read_data[i]=='A');
    for (int i=512;i<1512 && i<(int)sizeof(read_data);i++) assert(read_data[i]=='Z');
    io(B_READ,-1,512,read_data,EINVAL);
    io(B_READ,INT64_MAX,512,read_data,EINVAL);
    io(0,(int64_t)(sizeof(physical)/512),512,write_data,EINVAL);
    fail_after=0;
    io(0,16,sizeof(write_data),write_data,ENOMEM);
    fail_after=-1;
    assert(physical[16*512]=='A' && oriole_cow_pages==1);
    assert(media_writes==0 && media_reads>0);
    puts("Exact sweet_ufs_strategy host integration PASS");
}
'''

with tempfile.TemporaryDirectory() as name:
    p = Path(name)
    c = p / "strategy.c"
    c.write_text(head + cow_source() + "\n" + strategy + "\n" + tail)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(c), "-o", str(p/"strategy")], check=True)
    subprocess.run([str(p/"strategy")], check=True)
