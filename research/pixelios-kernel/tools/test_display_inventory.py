"""Execute the display reader with fake MMIO, including each channel's fault path."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools import boards

ROOT = Path(__file__).resolve().parents[1]


class DisplayInventoryTests(unittest.TestCase):
    def test_addresses_and_fault_isolation(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / 'board.h').write_text(boards.c_header('oriole'))
            (work / 'fixture.c').write_text(r'''
#include <stdint.h>
#include <stdlib.h>
#include <assert.h>
#include "console.h"
static unsigned counts[6];
static int fault_channel;
int try_read32(uintptr_t pa, uint32_t *v) {
    assert(pa >= 0x1c0b0000 && pa < 0x1c0b6000);
    unsigned ch = (pa - 0x1c0b0000) / 0x1000;
    unsigned off = (pa - 0x1c0b0000) % 0x1000;
    const unsigned order[] = {0,8,16,20,24,64,80,84};
    assert(counts[ch] < 16);
    assert(off == order[counts[ch] % 8] + (counts[ch] / 8) * 0x400);
    counts[ch]++;
    if ((int)ch == fault_channel) return 0;
    *v = 0;
    return 1;
}
void con_str(const char *a, const char *b) {(void)a;(void)b;}
void con_hex(const char *a, uint64_t b) {(void)a;(void)b;}
void con_hex2(const char *a, const char *b, uint32_t c, const char *d, uint32_t e)
{(void)a;(void)b;(void)c;(void)d;(void)e;}
void gs101_display_inventory(void);
int main(int argc, char **argv) {
    assert(argc == 2); fault_channel = atoi(argv[1]);
    gs101_display_inventory();
    for (int ch=0; ch<6; ch++) assert(counts[ch] == (ch == fault_channel ? 1 : 16));
    return 0;
}
''')
            exe = work / 'fixture'
            cc = os.environ.get('HOST_CC', 'cc')
            subprocess.run([cc, '-O1', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'shim'),
                            '-include', str(work / 'board.h'), str(work / 'fixture.c'),
                            str(ROOT / 'soc/google/gs101/shim/displayinventory.c'), '-o', str(exe)], check=True)
            for fault in range(-1, 6):
                subprocess.run([str(exe), str(fault)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
