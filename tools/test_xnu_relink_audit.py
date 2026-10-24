"""Exercise offline relink refusal gates against the actual local kernel artifacts."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('relink', ROOT/'tools/relink-reference-xnu.py')
relink = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relink)


@unittest.skipUnless((ROOT/'artifacts/native-kernel/kernel.pie-baseline').exists(), 'local offline artifacts absent')
class RelinkAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = (ROOT/'artifacts/xnu-reference/kernel.development.sweet').read_bytes()
        cls.baseline = (ROOT/'artifacts/native-kernel/kernel.pie-baseline').read_bytes()
        cls.modified = (ROOT/'artifacts/native-kernel/kernel.md0-usb').read_bytes()

    def commands(self, blob):
        off = 32
        for _ in range(struct.unpack_from('<I',blob,16)[0]):
            cmd,size = struct.unpack_from('<II',blob,off)
            yield cmd,off
            off += size

    def offset(self, blob, name):
        segments,symbols,_,_ = relink.macho_info(blob)
        address = symbols[name][0]
        for va,vs,fo,fs,_,_ in segments.values():
            if va <= address < va+fs:
                return fo+address-va
        self.fail('no backing data for '+name)

    def refuse(self, blob, message):
        with self.assertRaisesRegex(SystemExit,message):
            relink.verify_output(self.reference,blob,False)

    def test_both_current_outputs_pass(self):
        self.assertEqual(relink.verify_output(self.reference,self.baseline,False)['global_symbols'],24159)
        self.assertEqual(relink.verify_output(self.reference,self.modified,True)['global_symbols'],24159)

    def test_arm64e_refused(self):
        b=bytearray(self.baseline);struct.pack_into('<I',b,8,2)
        self.refuse(b,'plain-arm64')

    def test_non_pie_refused(self):
        b=bytearray(self.baseline);struct.pack_into('<I',b,24,1);self.refuse(b,'PIE')

    def test_profile_v10_refused(self):
        b=bytearray(self.baseline);struct.pack_into('<Q',b,self.offset(b,'___llvm_profile_raw_version'),10)
        self.refuse(b,'profile ABI')

    def test_changed_stack_probe_refused(self):
        b=bytearray(self.baseline);b[self.offset(b,'___chkstk_darwin')+4]^=1
        self.refuse(b,'Stack-check')

    def test_changed_linkinfo_refused(self):
        b=bytearray(self.baseline);_,_,fo,_,_,_=relink.macho_info(b)[0]['__LINKINFO'];b[fo]^=1
        self.refuse(b,'LINKINFO contents')

    def test_segment_protection_drift_refused(self):
        b=bytearray(self.baseline)
        off=next(o for c,o in self.commands(b) if c==0x19 and b[o+8:o+24].startswith(b'__DATA_CONST\0'))
        struct.pack_into('<I',b,off+60,3);self.refuse(b,'Runtime segment changed')

    def test_entry_drift_refused(self):
        b=bytearray(self.baseline);off=next(o for c,o in self.commands(b) if c==5)+16+32*8
        struct.pack_into('<Q',b,off,struct.unpack_from('<Q',b,off)[0]+4);self.refuse(b,'Entry differs')

    def test_non_linkedit_file_offset_drift_refused(self):
        b=bytearray(self.baseline)
        off=next(o for c,o in self.commands(b) if c==0x19 and b[o+8:o+24].startswith(b'__DATA_CONST\0'))
        field=off+40;struct.pack_into('<Q',b,field,struct.unpack_from('<Q',b,field)[0]+16)
        self.refuse(b,'Runtime segment changed')

    def test_linkedit_file_gap_refused(self):
        b=bytearray(self.baseline)
        off=next(o for c,o in self.commands(b) if c==0x19 and b[o+8:o+24].startswith(b'__LINKEDIT\0'))
        fo,fs=struct.unpack_from('<QQ',b,off+40)
        struct.pack_into('<QQ',b,off+40,fo+16,fs-16)
        self.refuse(b,'LINKEDIT file range')

    def test_entry_and_start_symbol_joint_drift_refused(self):
        b=bytearray(self.baseline)
        off=next(o for c,o in self.commands(b) if c==5)+16+32*8
        old=struct.unpack_from('<Q',b,off)[0];struct.pack_into('<Q',b,off,old+4)
        record=self.symbol_record(b,'__start');struct.pack_into('<Q',b,record+8,old+4)
        self.refuse(b,'Entry differs')

    def symbol_record(self,b,name):
        off=next(o for c,o in self.commands(b) if c==2)
        so,n,st,ss=struct.unpack_from('<4I',b,off+8);wanted=name.encode()+b'\0'
        for i in range(n):
            at=so+i*16;si=struct.unpack_from('<I',b,at)[0]
            if b[st+si:st+si+len(wanted)]==wanted:return at
        self.fail('symbol record absent: '+name)

    def test_symbol_duplicate_multiplicity_refused(self):
        b=bytearray(self.baseline);at=self.symbol_record(b,'__MergedGlobals');other=self.symbol_record(b,'l_.str')
        b[at:at+4]=b[other:other+4]
        self.refuse(b,'symbol-record multiplicity')

    def test_wrong_magic_and_command_area_refused(self):
        b=bytearray(self.baseline);b[0]^=1;self.refuse(b,'plain-arm64')
        b=bytearray(self.baseline);struct.pack_into('<I',b,20,struct.unpack_from('<I',b,20)[0]+4)
        self.refuse(b,'command area size')

    def test_repeated_command_type_refused(self):
        b=bytearray(self.baseline);off=next(o for c,o in self.commands(b) if c==0x2a)
        struct.pack_into('<I',b,off,0x1b);self.refuse(b,'load-command')

    def test_duplicate_zero_segment_name_refused(self):
        b=bytearray(self.baseline);off=next(o for c,o in self.commands(b) if c==0x19 and b[o+8:o+24].split(b'\0')[0]==b'__LAST')
        b[off+8:off+24]=b'__DATA_CONST'.ljust(16,b'\0')
        self.refuse(b,'Duplicate segment')

    def test_public_scope_drift_and_undefined_refused(self):
        for undefined in (False,True):
            b=bytearray(self.baseline);off=next(o for c,o in self.commands(b) if c==2)
            symoff,nsyms,stroff,strsize=struct.unpack_from('<4I',b,off+8)
            for n in range(nsyms):
                at=symoff+n*16;si,typ,_,_,_=struct.unpack_from('<IBBHQ',b,at)
                if si and b[stroff+si:stroff+si+len(b'_ContinuouslySyncProfile\0')]==b'_ContinuouslySyncProfile\0':
                    b[at+4] = 1 if undefined else (typ|1)&~0x10
                    break
            else:self.fail('mutation target absent')
            self.refuse(b,'Undefined symbol' if undefined else 'global-symbol scope')

    def test_unpinned_input_refused(self):
        with patch.object(relink,'digest',return_value='0'*64):
            with self.assertRaisesRegex(SystemExit,'Unreviewed relink input'):
                relink.verify_inputs()


if __name__=='__main__':
    unittest.main()
