#!/usr/bin/env python3
"""Exercise the actual draft Oriole GPT parser with independent disk fixtures.

Offline only: reconstructs source from numbered patches in a temporary directory.
No Apple binary input, phone, MMIO, disk image or filesystem mount is used.
"""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'research/pixelios-kernel/xnu/patches'
CAPACITY = 0x1dc03ff
FIRST, LAST = 0x22f1e6, 0x1dc03fa


class OrioleStorageRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='oriole-storage-test-')
        cls.work = Path(cls.tmp.name)
        subprocess.run(['git', 'init', '-q', str(cls.work)], check=True)
        for patch in sorted(PATCHES.glob('*.patch')):
            if int(patch.name[:4]) > 103:
                break
            subprocess.run(['git', 'apply', '--include=bsd/dev/sweet_ufs.c',
                            '--include=bsd/dev/oriole_ufs_guard.h', str(patch)],
                           cwd=cls.work, check=True, capture_output=True)
        source = (cls.work / 'bsd/dev/sweet_ufs.c').read_text()
        start = source.index('static int\nufs_find_oriole_userdata(')
        end = source.index('\n}\n', start) + 3
        parser = source[start:end]
        fixture = cls.work / 'fixture.c'
        fixture.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include "bsd/dev/oriole_ufs_guard.h"
#define DMA_BOUNCE 0
#define UFS_BLOCK 4096
static unsigned char bounce[16384], input[8+4096+16384];
static struct { uintptr_t dma; uint64_t first_block, nblocks; } su;
static int fail_at, reads;
static int ufs_scsi(const uint8_t *cdb, unsigned n, uint32_t len, bool write) {
 assert(n==10 && cdb[0]==0x25 && len==8 && !write);
 if(fail_at==1)return EIO;
 memcpy(bounce,input,8);return 0;
}
static int ufs_read_blocks(uint64_t lba,uint32_t count) {
 reads++;
 if(reads==1){assert(lba==1 && count==1);if(fail_at==2)return EIO;
  memcpy(bounce,input+8,4096);return 0;}
 assert(reads==2 && lba==2 && count>=1 && count<=4);
 if(fail_at==3)return EIO;
 memcpy(bounce,input+8+4096,count*4096);return 0;
}
''' + parser + r'''
int main(int argc,char **argv) {
 if(argc==1){
  const uint64_t base=0x880000000ULL,size=0x80000000ULL;
  assert(oriole_ufs_dma_ok(base,0x104000));
  assert(oriole_ufs_dma_ok(base+size-0x104000,0x104000));
  assert(!oriole_ufs_dma_ok(base+size-0x104000+1,0x104000));
  assert(!oriole_ufs_dma_ok(base-1,0x104000));
  assert(!oriole_ufs_dma_ok(base+size,1));
  assert(!oriole_ufs_dma_ok(base,0));
  assert(!oriole_ufs_dma_ok(base,UINT64_MAX));
  assert(!oriole_ufs_dma_ok(UINT64_MAX,2));
  return 0;
 }
 assert(argc==4);fail_at=atoi(argv[2]);
 FILE *f=fopen(argv[1],"rb");assert(f);
 assert(fread(input,1,sizeof(input),f)==sizeof(input));fclose(f);
 su.dma=(uintptr_t)bounce;
 int result=ufs_find_oriole_userdata(argv[3]);
 if(result){assert(!su.first_block && !su.nblocks);return 1;}
 assert(reads==2 && su.first_block==ORIOLE_USERDATA_FIRST);
 assert(su.nblocks==ORIOLE_USERDATA_LAST-ORIOLE_USERDATA_FIRST+1);
 return 0;
}
''')
        cls.exe = cls.work / 'fixture'
        subprocess.run(['cc', '-O1', '-Wall', '-Wextra', '-Werror',
                        '-Wno-format', '-I', str(cls.work), str(fixture),
                        '-o', str(cls.exe)], check=True)
        cls.build_takeover_fixture(source)
        cls.build_stop_and_opcode_fixture(source)

    @classmethod
    def build_stop_and_opcode_fixture(cls, source):
        start = source.index('static void\nufs_oriole_stop(')
        end = source.index('\n}\n', start) + 3
        stop = source[start:end]
        start = source.index('static int\nufs_scsi(')
        end = source.index('\n\t/* gs101:', start)
        # Execute the actual pre-DMA opcode gate. The subsequent SCSI builder
        # is deliberately excluded: this fixture never simulates media I/O.
        gate = source[start:end] + '\n return 0;\n}\n'
        constants = '\n'.join(line for line in source.splitlines()
                              if line.startswith('#define REG_'))
        fixture = cls.work / 'stop-and-opcode.c'
        fixture.write_text(r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <assert.h>
#include <errno.h>
#include <setjmp.h>
''' + constants + r'''
static struct {bool oriole,own_list;} su;
static uint32_t dbr,rsr;
static unsigned mode,writes,delays;
static jmp_buf panic_return;
static void panic(const char *message) {(void)message;longjmp(panic_return,1);}
static uint32_t ufs_rd(unsigned reg) {
 assert(reg==REG_UTRLDBR || reg==REG_UTRLRSR);
 return reg==REG_UTRLDBR?dbr:rsr;
}
static void ufs_wr(unsigned reg,uint32_t value) {
 writes++;
 if(reg==REG_UTRLCLR){assert(value==2);if(mode!=2)dbr=0;return;}
 assert(reg==REG_UTRLRSR && value==0);if(mode!=3)rsr=0;
}
static void delay(unsigned us) {assert(us==10);delays++;assert(delays<=20000);}
''' + stop + gate + r'''
int main(int argc,char **argv) {
 assert(argc==2);mode=(unsigned)atoi(argv[1]);su.oriole=su.own_list=true;
 if(mode==8){
  for(unsigned opcode=0;opcode<256;opcode++){
   uint8_t cdb[10]={(uint8_t)opcode};
   bool allowed=opcode==0 || opcode==0x25 || opcode==0x28;
   assert(ufs_scsi(cdb,10,0,false)==(allowed?0:EPERM));
   assert(ufs_scsi(cdb,10,0,true)==EPERM);
   assert(ufs_scsi(cdb,0,0,false)==EPERM);
  }
  assert(!writes && !delays);return 0;
 }
 rsr=1;if(mode==1 || mode==2)dbr=2;if(mode==4)dbr=1;
 if(mode==5)su.own_list=false;if(mode==6)su.oriole=false;
 if(setjmp(panic_return)==0){
  ufs_oriole_stop();
  assert(mode==0 || mode==1 || mode==5 || mode==6);
  if(mode<2){assert(!dbr && !rsr && !su.own_list && !delays);}
  else {assert(!writes && !delays && rsr==1);}
 } else {
  assert(mode==2 || mode==3 || mode==4);
  assert(su.own_list); /* never claim failed cleanup succeeded */
  if(mode==2)assert(dbr==2 && delays==10000 && writes==1);
  if(mode==3)assert(rsr==1 && delays==10000 && writes==1);
  if(mode==4)assert(dbr==1 && !delays && !writes);
 }
 return 0;
}
''')
        cls.stop_opcode = cls.work / 'stop-and-opcode'
        subprocess.run(['cc', '-O1', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', str(fixture), '-o', str(cls.stop_opcode)],
                       check=True)

    @classmethod
    def build_takeover_fixture(cls, source):
        start = source.index('static int\nufs_take_over_host(')
        end = source.index('\n}\n', start) + 3
        constants = '\n'.join(line for line in source.splitlines()
                              if line.startswith(('#define REG_', '#define HCS_',
                                                  '#define CAP_', '#define DMA_SIZE',
                                                  '#define DMA_UTRL', '#define DMA_BOUNCE',
                                                  '#define BOUNCE_SIZE')))
        fixture = cls.work / 'takeover.c'
        fixture.write_text(r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <assert.h>
#include <errno.h>
#define printf(...) ((void)0)
''' + constants + r'''
static struct { bool gs101,oriole,own_list; uint64_t dma_pa; } su;
static uint32_t regs[128];
static unsigned mode,list_writes,delays,all_writes;
static uint32_t ufs_rd(unsigned reg) {return regs[reg/4];}
static void ufs_wr(unsigned reg,uint32_t value) {
 all_writes++;
 if(reg==REG_UTRLBA || reg==REG_UTRLBAU)list_writes++;
 if(reg==REG_UTRLRSR && value==0){
  if(mode==1)regs[REG_UTRLDBR/4]=2; /* late foreign slot1 */
  if(mode==2)return; /* list never stops */
 }
 if(reg==REG_UTRLRSR && value==1 && mode==3)
  regs[REG_HCS/4]&=~HCS_UTRLRDY; /* list never becomes ready */
 regs[reg/4]=value;
}
static void delay(unsigned us) {assert(us==10);delays++;assert(delays<=10000);}
''' + source[start:end] + r'''
int main(int argc,char **argv) {
 assert(argc==2);mode=(unsigned)atoi(argv[1]);
 su.gs101=su.oriole=true;su.dma_pa=0x880100000ULL;
 regs[REG_HCE/4]=1;regs[REG_HCS/4]=HCS_DP|HCS_UTRLRDY;
 regs[REG_CAP/4]=CAP_64AS;regs[REG_UTRLRSR/4]=1;
 if(mode==4)regs[REG_UTRLDBR/4]=2;
 if(mode==5)regs[REG_CAP/4]=0;
 if(mode==6)regs[REG_HCE/4]=0;
 int result=ufs_take_over_host();
 if(mode==0){assert(result==0 && su.own_list && list_writes==2);}
 if(mode==1){assert(result==EBUSY && !su.own_list && !list_writes);
  assert(regs[REG_UTRLDBR/4]==2);}
 if(mode==2){assert(result==ETIMEDOUT && !su.own_list && !list_writes && delays==10000);}
 if(mode==3){assert(result==ETIMEDOUT && su.own_list && list_writes==2 && delays==10000);}
 if(mode>=4){assert(result!=0 && !su.own_list && !list_writes && !all_writes);}
 return 0;
}
''')
        cls.takeover = cls.work / 'takeover'
        subprocess.run(['cc', '-O1', '-Wall', '-Wextra', '-Werror',
                        str(fixture), '-o', str(cls.takeover)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def header_crc(h):
        struct.pack_into('<I', h, 16, 0)
        struct.pack_into('<I', h, 16, zlib.crc32(h[:struct.unpack_from('<I', h, 12)[0]]))

    def entry_crc(self, h, e):
        struct.pack_into('<I', h, 88, zlib.crc32(e[:struct.unpack_from('<I', h, 80)[0]*128]))
        self.header_crc(h)

    def fixture(self):
        capacity = bytearray(struct.pack('>2I', CAPACITY, 4096))
        e = bytearray(16384)
        e[0] = 1
        struct.pack_into('<2Q', e, 32, FIRST, LAST)
        e[56:74] = 'userdata\0'.encode('utf-16le')
        h = bytearray(4096)
        struct.pack_into('<8s4I4Q', h, 0, b'EFI PART', 0x10000, 92, 0, 0,
                         1, CAPACITY, 34, CAPACITY-5)
        struct.pack_into('<Q3I', h, 72, 2, 128, 128, 0)
        self.entry_crc(h, e)
        return capacity, h, e

    def run_fixture(self, fixture, fail_at=0, name='userdata'):
        path = self.work / 'input.bin'
        path.write_bytes(b''.join(fixture))
        return subprocess.run([str(self.exe), str(path), str(fail_at), name],
                              capture_output=True, timeout=5).returncode

    def test_dma_full_extent_and_overflow(self):
        subprocess.run([str(self.exe)], check=True, timeout=5)

    def test_takeover_ownership_race_and_bounded_failures(self):
        for mode in range(7):
            with self.subTest(mode=mode):
                subprocess.run([str(self.takeover), str(mode)], check=True, timeout=5)

    def test_owned_list_cleanup_success_failure_and_foreign_doorbell(self):
        for mode in (0, 1, 2, 3, 4, 5, 6):
            with self.subTest(mode=mode):
                subprocess.run([str(self.stop_opcode), str(mode)], check=True, timeout=5)

    def test_readonly_gate_rejects_all_other_opcodes_and_every_write(self):
        subprocess.run([str(self.stop_opcode), '8'], check=True, timeout=5)

    def test_exact_measured_userdata(self):
        self.assertEqual(self.run_fixture(self.fixture()), 0)

    def test_each_storage_read_failure(self):
        for stage in (1, 2, 3):
            with self.subTest(stage=stage):
                self.assertEqual(self.run_fixture(self.fixture(), stage), 1)

    def test_wrong_partition_request(self):
        self.assertEqual(self.run_fixture(self.fixture(), name='boot'), 1)

    def test_capacity_and_sector_size(self):
        for last, size in [(CAPACITY-1,4096),(CAPACITY+1,4096),
                           (0xffffffff,4096),(CAPACITY,512),(CAPACITY,0)]:
            c,h,e = self.fixture();c[:] = struct.pack('>2I',last,size)
            with self.subTest(last=last,size=size):
                self.assertEqual(self.run_fixture((c,h,e)),1)

    def test_header_corruption(self):
        for offset in (0,16,40,72,88):
            c,h,e = self.fixture();h[offset] ^= 1
            with self.subTest(offset=offset):
                self.assertEqual(self.run_fixture((c,h,e)),1)

    def test_header_bounds_with_valid_crc(self):
        mutations=[(12,'I',91),(12,'I',4097),(20,'I',1),(24,'Q',2),
                   (32,'Q',CAPACITY-1),(40,'Q',CAPACITY),(48,'Q',CAPACITY),
                   (72,'Q',0xffffffffffffffff),(80,'I',0),(80,'I',129),(84,'I',256)]
        for offset,fmt,value in mutations:
            c,h,e=self.fixture();struct.pack_into('<'+fmt,h,offset,value)
            # For invalid header length, retain a mathematically valid 92B CRC:
            # the length guard must reject before reading beyond a sector.
            struct.pack_into('<I',h,16,0)
            size=struct.unpack_from('<I',h,12)[0]
            struct.pack_into('<I',h,16,zlib.crc32(h[:min(size,4096)]))
            with self.subTest(offset=offset,value=value):
                self.assertEqual(self.run_fixture((c,h,e)),1)

    def test_entry_crc(self):
        c,h,e=self.fixture();e[80]^=1
        self.assertEqual(self.run_fixture((c,h,e)),1)

    def test_wrong_bounds_even_with_valid_crc(self):
        for first,last in [(FIRST+1,LAST),(FIRST,LAST-1),(LAST,FIRST),
                           (FIRST,CAPACITY),(0,LAST)]:
            c,h,e=self.fixture();struct.pack_into('<2Q',e,32,first,last)
            self.entry_crc(h,e)
            with self.subTest(first=first,last=last):
                self.assertEqual(self.run_fixture((c,h,e)),1)

    def test_overlap_duplicate_and_missing(self):
        for kind in ('overlap','duplicate','missing','suffix','utf16-high-byte'):
            c,h,e=self.fixture()
            if kind in ('overlap','duplicate'):
                e[128:256]=e[:128]
                if kind=='duplicate':struct.pack_into('<2Q',e,160,100,200)
            if kind=='missing':e[56]=ord('x')
            if kind=='suffix':e[72]=ord('x')
            if kind=='utf16-high-byte':e[57]=1
            self.entry_crc(h,e)
            with self.subTest(kind=kind):
                self.assertEqual(self.run_fixture((c,h,e)),1)


if __name__ == '__main__':
    unittest.main()
