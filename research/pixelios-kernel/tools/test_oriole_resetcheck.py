"""Execute the actual reset protocol with fake host, MMIO and EL3 responses."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
import re

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reset_audit',ROOT/'tools/audit_oriole_resetcheck.py')
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ResetCheckTests(unittest.TestCase):
    def test_source_audit_mutations(self):
        s=(ROOT/'shim/shim.c').read_text()
        h=(ROOT/'shim/resetcheck.h').read_text()
        c=(ROOT/'shim/resetcheck.c').read_bytes()
        audit.source_check(s,h,c)
        for bad in [s.replace('pa==RC_SYSIP && v==0xfc','pa==RC_SYSIP'),
                    s.replace('smc(0x82000504UL,pa,1,v)','smc(0x82000505UL,pa,1,v)'),
                    s.replace('smc(0x82000504UL,pa,1,v)','smc(0x82000504UL,pa,2,v)'),
                    s.replace('return usbg_on && usbgadget_ready();','return 1;'),
                    s.replace('pa==RC_SYSIP && try_read32(pa,v)','try_read32(pa,v)'),
                    s.replace('void resetcheck_wait_ms(unsigned ms) { delay_ms(ms); }',
                              'void resetcheck_wait_ms(unsigned ms) { (void)ms; }'),
                    s.replace('oriole_resetcheck(usbg_end);','oriole_resetcheck(now()+1);'),
                    s.replace('usb_gadget_start(dtb);\n#ifdef ORIOLE_RESETCHECK',
                              '#ifdef ORIOLE_RESETCHECK').replace('oriole_resetcheck(usbg_end);',
                              'oriole_resetcheck(usbg_end); usb_gadget_start(dtb);')]:
            self.assertNotEqual(bad,s)
            with self.assertRaises(ValueError): audit.source_check(bad,h,c)
        with self.assertRaises(ValueError):
            audit.source_check(s,h.replace('0x17460810UL','0x17460814UL'),c)
        with self.assertRaises(ValueError):
            audit.source_check(s,h,c.replace(b'RC_SWRESET,2',b'RC_SWRESET,3'))

    def test_compiled_audit_mutations(self):
        s=(ROOT/'tools/fixtures/oriole-resetcheck-writer.disasm').read_text()
        audit.writer_check(s)
        # Every compiled instruction is material; mutate one opcode at a time.
        matches=list(re.finditer(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',s,re.M))
        self.assertEqual(len(matches),19)
        for m in matches:
            bad=s[:m.start(1)]+f'{int(m[1],16)^1:08x}'+s[m.end(1):]
            with self.assertRaises(ValueError): audit.writer_check(bad)
        p=(ROOT/'tools/fixtures/oriole-resetcheck.disasm').read_text()
        audit.protocol_check(p)
        for bad in [p.replace('a9bd7bfd','a9bd7bfc',1),
                    p.replace('R_AARCH64_CALL26\tresetcheck_write','R_AARCH64_CALL26\tresetcheck_read',1),
                    p.replace('[sp, #-48]','[x0, #-48]',1)]:
            self.assertNotEqual(bad,p)
            with self.assertRaises(ValueError): audit.protocol_check(bad)

    def test_protocol_faults_and_exact_write_sequence(self):
        with tempfile.TemporaryDirectory() as d:
            c,exe=Path(d)/'test.c',Path(d)/'test'
            c.write_text(r'''
#include <assert.h>
#include "resetcheck.h"
static unsigned mode, reads, writes, t;
void con_str(const char *a,const char *b){(void)a;(void)b;}
void con_hex(const char *a,uint64_t v){(void)a;(void)v;}
int resetcheck_ready(void){return mode!=1 && !(mode==7 && t>=8000);}
uint64_t resetcheck_ticks(void){return t;}
void resetcheck_wait_ms(unsigned ms){assert(ms==1||ms==8000);t+=ms;}
int resetcheck_read(uintptr_t pa,uint32_t *v){
 assert(pa==RC_SYSIP);reads++;
 if((mode==2&&reads==1)||(mode==3&&reads==2))return 0;
 *v=reads==1 ? 0x1234 : mode==4 ? 0x1234 : 0xfc;return 1;
}
uint64_t resetcheck_write(uintptr_t pa,uint32_t v){
 writes++;assert(writes<=2);
 assert(writes==1 ? pa==RC_SYSIP&&v==0xfc : pa==RC_SWRESET&&v==2);
 return mode==5 ? 0xffffffffffffffffULL : 0;
}
int main(void){
 for(mode=0;mode<8;mode++){
  reads=writes=t=0;oriole_resetcheck(10);
  assert(t<=16000);
  if(mode==1){assert(t==10&&reads==0&&writes==0);}
  else if(mode==2){assert(reads==1&&writes==0);}
  else if(mode==3||mode==4||mode==5||mode==7){assert(reads==2&&writes==1&&t==8000);}
  else {assert(reads==2&&writes==2&&t==16000);}
 }
 return 0;
}
''')
            subprocess.run(['cc','-O1','-Wall','-Wextra','-Werror','-I',str(ROOT/'shim'),
                            str(c),str(ROOT/'shim/resetcheck.c'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)


if __name__=='__main__':
    unittest.main()
