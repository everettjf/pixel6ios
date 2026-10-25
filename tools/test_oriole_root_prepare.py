#!/usr/bin/env python3
"""Run the actual pre-XNU UFS preparation against fake hardware and I/O faults."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class RootPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='oriole-root-prepare-')
        cls.work=Path(cls.tmp.name)
        fixture=cls.work/'fixture.c'
        fixture.write_text(r'''
#include <assert.h>
#include <stdlib.h>
#include "ufsroot_prepare.h"
static unsigned mode,reads,fail_read,cold_calls,writes,waits;
static uint32_t dbr,rsr,hce=1,hcs=1,cap=1u<<24,ver=0x300;
int ufsroot_hw_read(uintptr_t pa,uint32_t *v) {
 reads++;if(reads==fail_read)return 0;
 switch(pa){case UR_DBR:*v=dbr;break;case UR_RSR:*v=rsr;break;
 case UR_HCE:*v=hce;break;case UR_HCS:*v=hcs;break;
 case UR_CAP:*v=cap;break;case UR_VER:*v=ver;break;default:assert(0);}
 return 1;
}
int ufsroot_hw_write(uintptr_t pa,uint32_t v) {
 assert(pa==UR_RSR && v==0);writes++;
 if(mode==10)return 0;
 if(mode!=5)rsr=0;
 return 1;
}
void ufsroot_wait_ms(unsigned ms) {assert(ms==1);waits++;assert(waits<=200);}
int ufsroot_cold_init(void) {
 cold_calls++;
 if(mode==3)return 7;
 if(mode==4 || mode==5 || mode==10)rsr=1;
 if(mode==6)dbr=2;
 if(mode==7)hce=0;if(mode==8)cap=0;if(mode==9)ver=0x200;
 if(mode==11)hcs=0;
 return 0;
}
int main(int argc,char **argv) {
 assert(argc==3);mode=(unsigned)atoi(argv[1]);fail_read=(unsigned)atoi(argv[2]);
 volatile unsigned active=0;if(mode==1)dbr=2;if(mode==2)rsr=1;
 int result=urs_prepare(&active);
 if(!fail_read){
  assert(result==(mode==0 || mode==4));
  if(mode==1 || mode==2)assert(active==2 && !cold_calls && !writes);
  else assert(active && cold_calls==1);
 }
 if(fail_read && fail_read<=reads)assert(!result);
 if(result)assert(!dbr && !rsr && (cap&(1u<<24)) && ver==0x300);
 unsigned before_stop=reads;
 int stopped=urs_stop(&active);
 if(mode==1 || mode==2 || mode==5 || mode==6 || mode==10 ||
    (fail_read && fail_read<=2)){assert(!stopped && active); /* no fallback USB */}
 else if(fail_read>before_stop && fail_read<=reads)assert(!stopped && active);
 else assert(stopped && !active);
 if(mode==6)assert(!writes && dbr==2);
 return 0;
}
''')
        cls.exe=cls.work/'fixture'
        subprocess.run(['cc','-O1','-Wall','-Wextra','-Werror','-I',
                        str(ROOT/'research/pixelios-kernel/shim'),str(fixture),
                        '-o',str(cls.exe)],check=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_preconditions_cold_init_cleanup_and_failure_modes(self):
        for mode in range(12):
            with self.subTest(mode=mode):
                subprocess.run([str(self.exe),str(mode),'0'],check=True,timeout=5)

    def test_each_read_fault_refuses_and_does_not_claim_cleanup(self):
        for read in range(1,17):
            with self.subTest(read=read):
                subprocess.run([str(self.exe),'0',str(read)],check=True,timeout=5)


if __name__=='__main__':unittest.main()
