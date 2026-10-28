"""The GUI cue must survive split datagrams and fire only once."""

import unittest

from watch_native_usb import GuiProcessCue


class GuiCueTests(unittest.TestCase):
    def test_split_markers_and_order(self):
        cue = GuiProcessCue()
        self.assertFalse(cue.feed(b'noise exec back'))
        self.assertFalse(cue.feed(b'boardd\nmore exec Spring'))
        self.assertTrue(cue.feed(b'Board\n'))
        self.assertFalse(cue.feed(b'exec SpringBoard\nexec backboardd\n'))

    def test_one_process_is_not_a_lock_screen_cue(self):
        cue = GuiProcessCue()
        self.assertFalse(cue.feed(b'exec SpringBoard\n'))
        self.assertFalse(cue.announced)


if __name__ == '__main__':
    unittest.main()
