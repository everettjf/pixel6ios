"""The GUI cue must survive split datagrams and fire only once."""

import unittest

from watch_native_usb import GuiProcessCue, TouchPathObserver


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


class TouchPathTests(unittest.TestCase):
    def test_split_touch_log_and_window_boundary(self):
        observer = TouchPathObserver()
        observer.feed(b'SWEET TOUCH: scanning, 1080x2400\nexec SpringBoard\nexec backboardd\n')
        self.assertEqual(observer.feed(b'SWEET TOUCH: ev 13 01 e2 62 2f 18 64 00 -> ki'), (False, False))
        self.assertEqual(observer.feed(b'nd 2 id 0 raw 738,758\nSWEET HID: touch 0 down at 738,'), (True, False))
        self.assertEqual(observer.feed(b'758\n'), (False, True))
        observer.feed(b'SWEET TOUCH: rail hold: 1200-second scan window ended\n')
        observer.feed(b'SWEET TOUCH: ev 33 01 de 82 2f 18 53 00 -> kind 3 id 0 raw 0,0\n'
                      b'SWEET HID: touch 0 up at 734,760\n')
        self.assertEqual((observer.touch_events, observer.hid_events), (2, 2))
        self.assertEqual((observer.gui_touch_events, observer.gui_hid_events), (1, 1))


if __name__ == '__main__':
    unittest.main()
