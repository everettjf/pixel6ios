"""The rail capture must not turn a partial IPC result into a success claim."""
import unittest

from run_acpm_rails_inventory import capture_ok


class CaptureTests(unittest.TestCase):
    def test_exact_two_replies(self):
        lines = (b'ACPM RAIL DESC rc00000000 why00000000\r\n'
                 b'ACPM RAIL READ reg0000005C rc00000000\r\n'
                 b'ACPM RAIL IPC published00000002 reply00000001\r\n'
                 b'ACPM RAIL READ reg0000005D rc00000000\r\n'
                 b'ACPM RAIL IPC published00000002 reply00000001\r\n'
                 b'INVENTORY report complete\r\n')
        self.assertTrue(capture_ok(lines))
        for broken in (lines.replace(b'0000005D', b'0000005E'),
                       lines.replace(b'rc00000000\r\nACPM RAIL IPC', b'rc00000006\r\nACPM RAIL IPC'),
                       lines.replace(b'reply00000001', b'reply00000000', 1),
                       lines.replace(b'ACPM RAIL READ reg0000005D rc00000000\r\n', b'')):
            self.assertFalse(capture_ok(broken))


if __name__ == '__main__':
    unittest.main()
