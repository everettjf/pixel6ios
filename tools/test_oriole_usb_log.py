#!/usr/bin/env python3
"""Run the actual USB log drain loop against immediate/short-send failures.

Offline source fixture only. UDP success is a local send result, not delivery ACK.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UsbLogCursorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='oriole-usb-log-test-')
        cls.work = Path(cls.tmp.name)
        subprocess.run(['git', 'init', '-q', str(cls.work)], check=True)
        for patch in sorted((ROOT/'research/pixelios-kernel/xnu/patches').glob('*.patch')):
            if int(patch.name[:4]) > 104:
                break
            subprocess.run(['git','apply','--include=bsd/dev/sweet_usb.c',str(patch)],
                           cwd=cls.work,check=True,capture_output=True)
        source=(cls.work/'bsd/dev/sweet_usb.c').read_text()
        start=source.index('\t\tuint32_t n;',source.index('ud_log_thread('))
        end=source.index('\n\t}\n}',start)
        loop=source[start:end]
        fixture=cls.work/'fixture.c'
        fixture.write_text(r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/uio.h>
static const char data[]="ABCDEFGHIJK";
static char received[64];
static unsigned calls,used,fail_call,short_send;
static uint32_t sweet_log_copy(uint64_t *pos,char *out,uint32_t max) {
 uint32_t n=(sizeof(data)-1)-*pos;if(n>max)n=max;
 memcpy(out,data+*pos,n);*pos+=n;return n;
}
static int sock_send(int so,const struct msghdr *msg,int flags,size_t *sent) {
 (void)so;(void)flags;calls++;
 assert(msg->msg_iovlen==1);
 if(calls==fail_call){*sent=short_send?msg->msg_iov[0].iov_len-1:0;
  return short_send?0:5;}
 *sent=msg->msg_iov[0].iov_len;
 memcpy(received+used,msg->msg_iov[0].iov_base,*sent);used+=*sent;
 return 0;
}
static void drain(uint64_t *cursor) {
 uint64_t pos=*cursor;char chunk[4];int so=0;char to=0;
''' + loop + r'''
 *cursor=pos;
}
int main(int argc,char **argv) {
 assert(argc==3);fail_call=(unsigned)atoi(argv[1]);short_send=(unsigned)atoi(argv[2]);
 uint64_t pos=0;drain(&pos);
 if(fail_call){assert(pos==(fail_call-1)*4);assert(used==pos);
  drain(&pos);}
 assert(pos==sizeof(data)-1 && used==sizeof(data)-1);
 assert(memcmp(received,data,sizeof(data)-1)==0);
 return 0;
}
''')
        cls.exe=cls.work/'fixture'
        subprocess.run(['cc','-O1','-Wall','-Wextra','-Werror',str(fixture),
                        '-o',str(cls.exe)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_success_drains_all_chunks(self):
        subprocess.run([str(self.exe),'0','0'],check=True,timeout=5)

    def test_failure_preserves_cursor_and_retries_exact_chunk(self):
        for call in (1,2,3):
            for short in (0,1):
                with self.subTest(call=call,short_send=short):
                    subprocess.run([str(self.exe),str(call),str(short)],check=True,timeout=5)


if __name__=='__main__':
    unittest.main()
