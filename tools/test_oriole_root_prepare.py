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
static unsigned mode,reads,fail_read;
static uint32_t dbr,rsr,hce=1,hcs=1,cap=1u<<24,ver=0x300;
int ufsroot_hw_read(uintptr_t pa,uint32_t *v) {
 reads++;if(reads==fail_read)return 0;
 if(mode==7 && pa==UR_DBR && reads==7)dbr=2;
 if(mode==8 && pa==UR_RSR && reads==8)rsr=1;
 switch(pa){case UR_DBR:*v=dbr;break;case UR_RSR:*v=rsr;break;
 case UR_HCE:*v=hce;break;case UR_HCS:*v=hcs;break;
 case UR_CAP:*v=cap;break;case UR_VER:*v=ver;break;default:assert(0);}
 return 1;
}
int main(int argc,char **argv) {
 assert(argc==3);mode=(unsigned)atoi(argv[1]);fail_read=(unsigned)atoi(argv[2]);
 volatile unsigned active=mode==12?1:0;
 if(mode==1)dbr=2;if(mode==2)rsr=1;if(mode==3)hce=0;
 if(mode==4)hcs=0;if(mode==5)cap=0;if(mode==6)ver=0x200;
 struct urs_diag diag;
 int result=urs_prepare(&active,&diag);
 int expected=!fail_read ? (mode==0 || mode==9 || mode==10 || mode==11) : fail_read>8;
 assert(result==expected);
 if(result)assert(diag.code==9 && diag.value==0);
 if(!result && fail_read && fail_read<=8)assert(diag.code==(unsigned)(0x100+fail_read));
 if(!result && !fail_read){
  static const unsigned codes[]={0,1,2,3,4,5,6,7,8,0,0,0,0};
  static const uint32_t values[]={0,2,1,0,0,0,0x200,2,1,0,0,0,1};
  assert(diag.code==codes[mode] && diag.value==values[mode]);
 }
 if(!result){assert(active==2 && !urs_stop(&active));return 0;}
 assert(active==1);
 if(mode==9)dbr=2;if(mode==10)rsr=1;
 if(mode==11){assert(urs_handoff(&active));assert(active==2);assert(!urs_stop(&active));return 0;}
 int stopped=urs_stop(&active);
 assert(stopped==(mode==0 && fail_read==0));
 if(stopped)assert(active==0);else assert(active==1);
 return 0;
}
''')
        cls.exe=cls.work/'fixture'
        subprocess.run(['cc','-O1','-Wall','-Wextra','-Werror','-I',
                        str(ROOT/'research/pixelios-kernel/shim'),str(fixture),
                        '-o',str(cls.exe)],check=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_readonly_preconditions_cleanup_and_handoff(self):
        for mode in range(13):
            with self.subTest(mode=mode):
                subprocess.run([str(self.exe),str(mode),'0'],check=True,timeout=5)

    def test_each_read_fault_refuses_without_cleanup_or_handoff(self):
        for read in range(1,11):
            with self.subTest(read=read):
                subprocess.run([str(self.exe),'0',str(read)],check=True,timeout=5)


if __name__=='__main__':unittest.main()
