"""Exercise the COW implementation from the numbered XNU patch on the host."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "xnu/patches/0105-oriole-ram-cow-root.patch"


def cow_source():
    lines = PATCH.read_text().splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("+/* Only the exact Oriole COW profile"))
    end = next(i for i in range(start, len(lines))
               if lines[i] == " static inline uint32_t")
    added = lines[start:end]
    if not added or any(not line.startswith("+") for line in added):
        raise AssertionError("COW implementation must be one complete added hunk")
    return "\n".join(line[1:] for line in added)


HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define UFS_BLOCK 4096u
#define Z_NOWAIT 1
#define Z_ZERO 2
static int fail_after = -1;
static void *kalloc_data(size_t size, int flags)
{
    if (fail_after == 0) return NULL;
    if (fail_after > 0) fail_after--;
    return flags & Z_ZERO ? calloc(1, size) : malloc(size);
}
static void kfree_data(void *p, size_t size) { (void)size; free(p); }
#define kalloc_type_2(type, flags) ((type *)kalloc_data(sizeof(type), flags))
#define kalloc_type_3(type, count, flags) ((type *)kalloc_data(sizeof(type) * (count), flags))
#define kalloc_type_choose(_1, _2, _3, name, ...) name
#define kalloc_type(...) kalloc_type_choose(__VA_ARGS__, kalloc_type_3, kalloc_type_2)(__VA_ARGS__)
#define kfree_type(type, p) kfree_data((p), sizeof(type))
__COW_SOURCE__
int main(void)
{
    oriole_cow_buckets = calloc(ORIOLE_COW_BUCKETS, sizeof(*oriole_cow_buckets));
    assert(oriole_cow_buckets);
    uint8_t physical[2 * UFS_BLOCK], changed[2 * UFS_BLOCK];
    memset(physical, 'A', UFS_BLOCK);
    memset(physical + UFS_BLOCK, 'B', UFS_BLOCK);
    memset(changed, 'X', UFS_BLOCK);
    memset(changed + UFS_BLOCK, 'Y', UFS_BLOCK);

    oriole_cow_overlay(10, 2, physical);
    assert(physical[0] == 'A' && physical[UFS_BLOCK] == 'B');
    assert(oriole_cow_store(10, 2, changed) == 0);
    assert(oriole_cow_pages == 2);
    oriole_cow_overlay(10, 2, physical);
    assert(physical[0] == 'X' && physical[UFS_BLOCK] == 'Y');

    memset(changed, 'M', UFS_BLOCK);
    memset(changed + UFS_BLOCK, 'N', UFS_BLOCK);
    fail_after = 0;
    assert(oriole_cow_store(10, 2, changed) == 0);
    assert(oriole_cow_pages == 2);
    assert(oriole_cow_find(10)->data[0] == 'M');
    assert(oriole_cow_find(11)->data[0] == 'N');

    fail_after = 1; /* new node succeeds; new data allocation fails */
    assert(oriole_cow_store(11, 2, changed) == ENOMEM);
    assert(oriole_cow_pages == 2 && oriole_cow_find(12) == NULL);
    assert(oriole_cow_find(11)->data[0] == 'N');

    fail_after = -1;
    uint32_t saved = oriole_cow_pages;
    oriole_cow_pages = ORIOLE_COW_MAX_PAGES;
    assert(oriole_cow_store(12, 1, changed) == ENOSPC);
    assert(oriole_cow_find(12) == NULL);
    oriole_cow_pages = saved;

    assert(oriole_cow_bucket(10) == oriole_cow_bucket(16395));
    assert(oriole_cow_store(16395, 1, changed) == 0);
    assert(oriole_cow_find(10)->data[0] == 'M');
    assert(oriole_cow_find(16395)->data[0] == 'M');
    puts("Oriole RAM COW host test PASS");
    return 0;
}
'''


class OrioleCowTests(unittest.TestCase):
    def test_cow_uses_ram_and_is_transactional_on_allocation_failure(self):
        source = HARNESS.replace("__COW_SOURCE__", cow_source())
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "cow.c"
            binary = Path(directory) / "cow"
            src.write_text(source)
            cc = os.environ.get("CC", "cc")
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(src), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_physical_write_barriers_and_exact_opt_in(self):
        patch = PATCH.read_text()
        self.assertIn("su.writable = su.oriole ? su.oriole_cow : (rw != 0)", patch)
        self.assertIn('oriole-cow-board', patch)
        self.assertIn('PE_parse_boot_argn("ufscow", &cow, sizeof(cow))', patch)
        self.assertIn('rootrw != (uint32_t)su.oriole_cow', patch)
        self.assertIn('if (su.oriole_cow) return 0;', patch)
        # Existing 0103 blocks every Oriole data-out UPIU and WRITE(10).
        ro = (ROOT / "xnu/patches/0103-oriole-readonly-ufs-root-validation.patch").read_text()
        self.assertIn("if (su.oriole && (write || !cdb_len", ro)
        self.assertIn("if (su.oriole || !su.writable", ro)


if __name__ == "__main__":
    unittest.main()
