"""Loader range failures and fail-closed build profile (no Apple inputs needed)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RamProbeTests(unittest.TestCase):
    def test_non_avb_cannot_relabel_stale_image(self):
        # Execute the actual build-script finalization in isolation: an old
        # image exists, but this invocation did not generate its AVB footer.
        script=(ROOT/'shim/build.sh').read_text()
        finish=script.split('# provenance sidecar for the image fastboot will boot',1)[1]
        finish=finish.split('\n',1)[1]
        finish=finish[:finish.index('\nls -l')]
        invalidate=next(s for s in script.splitlines()
                        if s.startswith('rm -f out/shim-boot-avb.img.meta.json'))
        with tempfile.TemporaryDirectory() as d:
            work=Path(d);(work/'out').mkdir()
            (work/'out/shim-boot-avb.img').write_bytes(b'old image')
            sidecar=work/'out/shim-boot-avb.img.meta.json'
            for avb in ('0','1'):
                sidecar.write_text('stale provenance')
                env=dict(os.environ,avb=avb,boot_xnu='1',udump_mib='0',PYTHON='/bin/echo')
                r=subprocess.run(['bash','-ec',invalidate+'\n'+finish],cwd=work,
                                 env=env,capture_output=True,text=True,check=True)
                self.assertFalse(sidecar.exists())
                self.assertEqual('imgmeta.py write' in r.stdout,avb=='1')

    def test_loader_bounds_and_rounding(self):
        with tempfile.TemporaryDirectory() as d:
            c, exe = Path(d)/'test.c', Path(d)/'test'
            c.write_text(r'''
#include <assert.h>
#include <string.h>
#include "ramprobe_guard.h"
#include "ufsinventory_guard.h"
struct fixture {uint64_t words[(sizeof(struct payload)+11*sizeof(struct payload_seg))/8];};
int main(void) {
 struct fixture x={0}; struct payload *p=(struct payload *)x.words;
 p->version=1;p->nsegs=11;p->virt_base=0xfffffe0006000000ULL;
 p->phys_base=0x880000000ULL;p->mem_size=0x80000000;
 p->entry_va=0xfffffe0007493488ULL;p->kernel_end=0xfffffe0008730000ULL;
 p->adt_off=0x2000;p->adt_size=0x1000;
 for(unsigned i=0;i<11;i++) p->segs[i]=(struct payload_seg){p->entry_va+i*0x4000,0x1000,0x1000+i*8,8};
 assert(ramprobe_payload_ok(p,16726576));
 assert(!ramprobe_payload_ok(p,16726575));
 struct fixture good=x;
 p->nsegs=12;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->mem_size=0xffffffffffffffffULL;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->phys_base=0x80000000;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->adt_off=16726576-8;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->segs[0].file_size=9;p->segs[0].vmsize=8;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->segs[0].file_off=16726576-8;p->segs[0].file_size=9;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->segs[0].vmaddr=0xfffffffffffffff8ULL;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->segs[0].vmsize=0xfffffffffffffff8ULL;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->segs[1].vmaddr=p->segs[0].vmaddr;assert(!ramprobe_payload_ok(p,16726576));x=good;
 p->segs[0].file_size=0;assert(!ramprobe_payload_ok(p,16726576));x=good;
 struct fdt_memmap m={0};m.n_banks=1;m.banks[0].base=p->phys_base;m.banks[0].size=p->mem_size;
 assert(ufsi_range_free(&m,p->phys_base,p->mem_size,0,0));
 m.n_reserved=1;m.reserved[0].base=p->phys_base+0x40000000;m.reserved[0].size=0x1000;
 assert(!ufsi_range_free(&m,p->phys_base,p->mem_size,0,0));
 m.n_reserved=0;struct ufsi_avoid a={p->phys_base+p->mem_size-8,8};
 assert(!ufsi_range_free(&m,p->phys_base,p->mem_size,&a,1));
 m.n_reserved_dropped=1;assert(!ufsi_range_free(&m,p->phys_base,p->mem_size,0,0));
 return 0;
}
''')
            subprocess.run(['cc','-O1','-Wall','-Wextra','-Werror','-I',str(ROOT/'shim'),
                            str(c),'-o',str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_profile_selections_are_exclusive(self):
        for flags in (['--xnu-loadcheck','--xnu-ramprobe'],
                      ['--xnu-ramprobe','--xnu-loadcheck']):
            r=subprocess.run(['bash','shim/build.sh','--board','oriole']+flags,
                cwd=ROOT,env=dict(os.environ,CROSS_CC='/nonexistent-ramprobe-compiler'),
                capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,2,r.stderr)
            self.assertIn('select only one RAM probe profile',r.stderr)

    def test_build_rejects_before_compiler(self):
        env = dict(os.environ, CROSS_CC='/nonexistent-ramprobe-compiler')
        for key in ('USB_WINDOW','USB_DMA_HI_BASE','UFS_DMA_HI_BASE','UFS_ATTEMPTS','REBOOT_BL','XNU_UFS'):
            env.pop(key, None)
        for options, extra in [(['--inventory'],{}),(['--udump','1'],{}),
                (['--touch-probe=rails'],{}),(['--gpu-job'],{}),(['--wlan-link'],{}),
                (['--pstore-fast'],{}),(['--qrlog'],{}),([] ,{'XNU_UFS':'1'}),
                ([],{'USB_DMA_HI_BASE':'0x880100000'}),([],{'REBOOT_BL':'1'}),
                ([],{'USB_WINDOW':'61'}),([],{'UFS_ATTEMPTS':'1'})]:
            with self.subTest(options=options,extra=extra):
                for profile in ('--xnu-ramprobe','--xnu-loadcheck'):
                    r=subprocess.run(['bash','shim/build.sh','--board','oriole',profile]+options,
                        cwd=ROOT,env=dict(env,**extra),capture_output=True,text=True,timeout=10)
                    self.assertEqual(r.returncode,2,r.stderr)
                    self.assertNotIn('nonexistent-ramprobe-compiler',r.stderr)


if __name__=='__main__':
    unittest.main()
