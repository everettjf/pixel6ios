"""Independently generate UEFI GPT CRC fixtures and test no-DMA placement failures."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


class UfsInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp.name)
        source = cls.work / 'fixture.c'
        source.write_text(r'''
#include <stdio.h>
#include <assert.h>
#include "ufsinventory_guard.h"
#include "ufsinventory_gpt.h"
int main(int argc,char **argv) {
 if(argc==1) {
  struct fdt_memmap m={0}; struct ufsi_avoid a={0x880100000,0x1000};
  m.n_banks=1;m.banks[0].base=0x880000000;m.banks[0].size=0x80000000;
  assert(ufsi_range_free(&m,0x880100000,0x20000,0,0));
  assert(!ufsi_range_free(&m,0x880100000,0x20000,&a,1));
  assert(!ufsi_range_free(&m,0,0x20000,0,0));
  assert(!ufsi_range_free(&m,0xffffffffffffffff,2,0,0));
  assert(!ufsi_range_free(&m,0x880100000,0,0,0));
  m.n_reserved=1;m.reserved[0].base=0x880110000;m.reserved[0].size=0x1000;
  assert(!ufsi_range_free(&m,0x880100000,0x20000,0,0));
  m.n_reserved=0;m.n_reserved_dropped=1;
  assert(!ufsi_range_free(&m,0x880100000,0x20000,0,0));
  m.n_reserved_dropped=0;m.n_banks=0;
  assert(!ufsi_range_free(&m,0x880100000,0x20000,0,0));
  return 0;
 }
 unsigned char h[4096],e[16384];FILE *f=fopen(argv[1],"rb");assert(f);
 assert(fread(h,1,sizeof h,f)==sizeof h);assert(fread(e,1,sizeof e,f)==sizeof e);fclose(f);
 struct ufsi_gpt g;uint64_t first=0,last=0;
 if(!ufsi_gpt_header(h,100000,&g)||!ufsi_gpt_userdata(e,&g,&first,&last))return 1;
 return first==100&&last==999 ? 0 : 2;
}
''')
        cls.exe = cls.work / 'fixture'
        subprocess.run(['cc', '-O1', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'shim'),
                        str(source), '-o', str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fixture(self):
        e = bytearray(16384)
        e[0] = 1
        struct.pack_into('<2Q', e, 32, 100, 999)
        name = 'userdata\0'.encode('utf-16le')
        e[56:56+len(name)] = name
        h = bytearray(4096)
        struct.pack_into('<8s4I4Q', h, 0, b'EFI PART', 0x10000, 92, 0, 0,
                         1, 100000, 34, 99998)
        struct.pack_into('<Q3I', h, 72, 2, 4, 128, zlib.crc32(e[:512]))
        self.header_crc(h)
        return h, e

    @staticmethod
    def header_crc(h):
        struct.pack_into('<I', h, 16, 0)
        struct.pack_into('<I', h, 16, zlib.crc32(h[:92]))

    def run_fixture(self, h, e):
        path = self.work / 'gpt.bin'
        path.write_bytes(h+e)
        return subprocess.run([str(self.exe), str(path)], timeout=5).returncode

    def test_free_ram_and_fail_closed_dma_cases(self):
        subprocess.run([str(self.exe)], check=True, timeout=5)

    def test_valid_header_and_userdata(self):
        self.assertEqual(self.run_fixture(*self.fixture()), 0)

    def test_header_crc_and_signature_corruption(self):
        for offset in [0, 16, 40, 72]:
            h,e=self.fixture();h[offset]^=1
            with self.subTest(offset=offset):self.assertEqual(self.run_fixture(h,e),1)

    def test_header_capacity_and_table_bounds(self):
        for offset,fmt,value in [(32,'Q',100001),(40,'Q',100000),(48,'Q',100000),
                                 (72,'Q',0xffffffff),(80,'I',0x80000001),(84,'I',256)]:
            h,e=self.fixture();struct.pack_into('<'+fmt,h,offset,value);self.header_crc(h)
            with self.subTest(offset=offset):self.assertEqual(self.run_fixture(h,e),1)

    def test_entry_crc_corruption(self):
        h,e=self.fixture();e[80]^=1
        self.assertEqual(self.run_fixture(h,e),1)

    def test_partition_range_overlap_duplicate_or_missing(self):
        for kind in ['reverse','outside','overlap','duplicate','missing']:
            h,e=self.fixture()
            if kind=='reverse':struct.pack_into('<2Q',e,32,1000,999)
            if kind=='outside':struct.pack_into('<2Q',e,32,100,100000)
            if kind in ['overlap','duplicate']:
                e[128:256]=e[:128]
                if kind=='duplicate':struct.pack_into('<2Q',e,160,2000,2999)
            if kind=='missing':e[56]=ord('x')
            struct.pack_into('<I',h,88,zlib.crc32(e[:512]));self.header_crc(h)
            with self.subTest(kind=kind):self.assertEqual(self.run_fixture(h,e),1)


if __name__ == '__main__':unittest.main()
