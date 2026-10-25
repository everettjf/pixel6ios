#!/usr/bin/env python3
"""Execute the actual patch-0102 callback gate with fake DT/boot args/network API."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
patch = (ROOT / 'xnu/patches/0102-sweet-md0-usb-after-network.patch').read_text()
added = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
a = added.index('/* BEGIN SWEET_MD0_USB:')
b = added.index('/* END SWEET_MD0_USB */') + len('/* END SWEET_MD0_USB */')
block = added[a:b]
prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void *DTEntry;
#define kSuccess 0
static int test, registered, usb_calls, property_reads, network_ready;
static void (*callback)(void);
static int PE_parse_boot_arg_str(const char *name, char *out, int size) {
    assert(strcmp(name,"rd")==0);
    if(test==1) return 0;
    snprintf(out,size,"%s",test==2 ? "ufsroot0" : "md0"); return 1;
}
static int PE_parse_boot_argn(const char *name, void *out, int size) {
    assert(size==sizeof(int));
    if(!strcmp(name,"sweetusb")) {
        if(test==3) return 0;
        *(int*)out=test==4 ? 0 : test==5 ? 1 : test==6 ? 3 : 2;return 1;
    }
    assert(!strcmp(name,"sweetusbdma"));
    if(test==7) *(int*)out=1;
    if(test==8) *(int*)out=2;
    return test==7 || test==8;
}
static int SecureDTLookupEntry(DTEntry parent, const char *path, DTEntry *out) {
    assert(parent==NULL);
    if(!strcmp(path,"/sweet-ufs")) return test==9 ? kSuccess : -1;
    assert(!strcmp(path,"/sweet-usb"));*out=(void*)1;return test==10 ? -1 : kSuccess;
}
static int SecureDTGetProperty(DTEntry node,const char *name, const void **out,unsigned int *size) {
    static uint32_t one=1,zero=0;
    assert(node==(void*)1);property_reads++;
    if(!strcmp(name,"compatible")) {
        *out=test==11 ? NULL : test==12 ? "qcom,sm7150-dwusb3" : "google,gs101-dwusb3";
        *size=test==13 ? 19 : sizeof("google,gs101-dwusb3"); return test==14 ? -1 : kSuccess;
    }
    if(!strcmp(name,"md0-log-board")) {
        *out=test==15 ? "bluejay" : test==16 ? NULL : "oriole";
        *size=test==17 ? 6 : sizeof("oriole");return test==18 ? -1 : kSuccess;
    }
    assert(!strcmp(name,"init-after-network"));
    *out=test==19 ? NULL : test==20 ? &zero : &one;
    *size=test==21 ? 8 : sizeof(one);return test==22 ? -1 : kSuccess;
}
static int net_init_add(void (*f)(void)) {
    registered++; assert(!network_ready);callback=f;
    return test==23 ? 37 : test==24 ? 12 : 0;
}
void sweet_usb_probe(void) {assert(network_ready);usb_calls++;}
'''
suffix = r'''
int main(int argc,char **argv) {
    assert(argc==2);test=atoi(argv[1]);
    sweet_md0_usb_register();assert(usb_calls==0);
    if(test>0 && test<23) {assert(registered==0);assert(callback==NULL);}
    if(test>=23) {assert(registered==1);assert(usb_calls==0);return 0;}
    if(test==0) {
        assert(registered==1);assert(callback!=NULL);
        network_ready=1;callback();callback();assert(usb_calls==1);
    }
    return 0;
}
'''
class Md0UsbHookTests(unittest.TestCase):
    def test_registration_is_once_before_reset_node_validation(self):
        self.assertIn("+#include <net/init.h>", patch)
        self.assertEqual(added.count("sweet_md0_usb_register();"), 1)
        self.assertIn(" \tstarted = 1;\n+\tsweet_md0_usb_register();\n \tif (SecureDTLookupEntry(NULL, \"/sweet-reset\", &node)", patch)
        self.assertIn('SecureDTLookupEntry(NULL, "/sweet-reset", &node)', patch)

    def test_actual_hook_all_gates_and_network_ready_one_shot(self):
        with tempfile.TemporaryDirectory(prefix='md0-usb-fixture-') as d:
            source, exe = Path(d)/'test.c',Path(d)/'test'
            source.write_text(prefix + block + suffix)
            subprocess.run([os.environ.get('HOST_CC','cc'),'-std=c11','-Wall','-Wextra','-Werror',str(source),'-o',str(exe)],check=True)
            for case in range(25):
                subprocess.run([str(exe),str(case)],check=True,stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
