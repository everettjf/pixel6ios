"""The PMIC cycle capture is accepted only after both rails are restored."""
import unittest

from run_acpm_rail_cycle_inventory import capture_ok


class CaptureTests(unittest.TestCase):
    def test_complete_and_faults(self):
        lines = [
            b'ACPM CYCLE READ reg0000005C value0000002C',
            b'ACPM CYCLE READ rc00000000 want0000002C',
            b'ACPM CYCLE READ reg0000005D value0000003C',
            b'ACPM CYCLE READ rc00000000 want0000003C',
            b'ACPM CYCLE SET reg0000005C on00000001',
            b'ACPM CYCLE SET rc00000000 published00000001',
            b'ACPM CYCLE READ reg0000005C value000000AC',
            b'ACPM CYCLE READ rc00000000 want000000AC',
            b'ACPM CYCLE SET reg0000005D on00000001',
            b'ACPM CYCLE SET rc00000000 published00000001',
            b'ACPM CYCLE READ reg0000005D value000000BC',
            b'ACPM CYCLE READ rc00000000 want000000BC',
            b'ACPM CYCLE both rails enabled and read back',
            b'ACPM CYCLE SET reg0000005D on00000000',
            b'ACPM CYCLE SET rc00000000 published00000001',
            b'ACPM CYCLE READ reg0000005D value0000003C',
            b'ACPM CYCLE READ rc00000000 want0000003C',
            b'ACPM CYCLE SET reg0000005C on00000000',
            b'ACPM CYCLE SET rc00000000 published00000001',
            b'ACPM CYCLE READ reg0000005C value0000002C',
            b'ACPM CYCLE READ rc00000000 want0000002C',
            b'ACPM CYCLE END enabled00000001 restored00000002',
            b'INVENTORY report complete',
        ]
        self.assertTrue(capture_ok(b'\n'.join(lines)))
        for i in range(len(lines)):
            self.assertFalse(capture_ok(b'\n'.join(lines[:i] + lines[i + 1:])))
        self.assertFalse(capture_ok(b'\n'.join(lines + [b'RESTORE FAILED LDO25M'])))
        self.assertFalse(capture_ok(b'\n'.join(lines + [lines[9]])))
        self.assertFalse(capture_ok(b'\n'.join(lines[:5] + [b'ACPM CYCLE SET rc00000005 published00000001'] + lines[6:])))
        self.assertFalse(capture_ok(b'\n'.join(lines[:5] + [b'ACPM CYCLE SET rc00000000 published00000000'] + lines[6:])))
        self.assertFalse(capture_ok(b'\n'.join(lines[:1] + [b'ACPM CYCLE READ rc00000005 want0000002C'] + lines[2:])))
        self.assertFalse(capture_ok(b'\n'.join(lines[:13] + [b'ACPM CYCLE SET reg0000005C on00000000'] + lines[13:])))


if __name__ == '__main__':
    unittest.main()
