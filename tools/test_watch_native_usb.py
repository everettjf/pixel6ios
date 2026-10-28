"""The GUI cue must survive split datagrams and fire only once."""

import unittest

from watch_native_usb import GuiProcessCue


class GuiCueTests(unittest.TestCase):
    def test_split_markers_and_order(self):
        cue = GuiProcessCue()
        self.assertFalse(cue.feed(b'SWEET TOUCH: scan'))
        self.assertFalse(cue.feed(b'ning, 1080x2400\nnoise exec back'))
        self.assertFalse(cue.feed(b'boardd\nmore exec Spring'))
        self.assertTrue(cue.feed(b'Board\n'))
        self.assertFalse(cue.feed(b'exec SpringBoard\nexec backboardd\n'))

    def test_one_process_is_not_a_lock_screen_cue(self):
        cue = GuiProcessCue()
        self.assertFalse(cue.feed(b'exec SpringBoard\n'))
        self.assertFalse(cue.announced)

    def test_expired_scan_cannot_cue(self):
        cue = GuiProcessCue()
        self.assertFalse(cue.feed(b'SWEET TOUCH: scanning, 1080x2400\n'))
        self.assertFalse(cue.feed(b'SWEET TOUCH: rail hold: 1200-second scan window ended\n'))
        self.assertFalse(cue.feed(b'exec SpringBoard\nexec backboardd\n'))
        self.assertFalse(cue.announced)


if __name__ == '__main__':
    unittest.main()
