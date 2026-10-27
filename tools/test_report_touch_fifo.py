"""A FIFO capture must include the event and cleanup before it is complete."""

import unittest

from report_touch_fifo import report_from_raw


BASE = [
    'INVENTORY Oriole one-shot touch ID and restore',
    'INVENTORY Oriole one-shot touch FIFO and restore',
    *(f'ORIOLE TOUCH RAIL reg{reg:08X} value{value:08X}' for reg, value in
      ((0x5c, 0x2c), (0x5d, 0x3c), (0x5c, 0xac),
       (0x5d, 0xbc), (0x5d, 0x3c), (0x5c, 0x2c))),
    'ORIOLE TOUCH ID first00000000 cleanup00000000',
    'ORIOLE TOUCH ID id000000036 id100000048',
    'ORIOLE TOUCH ID attempts00000001 restored00000002',
    'ORIOLE TOUCH FIFO attempts00000001 event000000003',
    'ORIOLE TOUCH FIFO b100000000 b200000000',
    'ORIOLE TOUCH FIFO b300000000 b400000000',
    'ORIOLE TOUCH FIFO b500000000 b600000000',
    'ORIOLE TOUCH FIFO b700000000 cleanup00000000',
    'ORIOLE TOUCH ID PASS 36 48 AND RESTORED',
    'INVENTORY report complete',
]


class TouchFifoReportTests(unittest.TestCase):
    def report(self, lines):
        return report_from_raw(('\n'.join(lines) + '\n').encode())

    def test_complete_one_event(self):
        report = self.report(BASE)
        self.assertTrue(report['complete'])
        self.assertTrue(report['fifo_read_succeeded'])
        self.assertEqual(report['event_bytes'], [3, 0, 0, 0, 0, 0, 0, 0])
        self.assertFalse(report['ios_touch_or_gestures_verified'])

    def test_missing_fifo_line_is_incomplete(self):
        report = self.report([line for line in BASE if ' b300000000 ' not in line])
        self.assertFalse(report['complete'])
        self.assertIsNone(report['event_bytes'])

    def test_partial_latest_capture_cannot_reuse_prior_success(self):
        report = self.report(BASE + BASE[:4])
        self.assertEqual(report['capture_count'], 2)
        self.assertFalse(report['complete'])

    def test_failed_id_or_status_cannot_claim_fifo_success(self):
        for old, new in [('id000000036', 'id000000099'),
                         ('PASS 36 48 AND RESTORED', 'FAILED')]:
            report = self.report([line.replace(old, new) for line in BASE])
            self.assertTrue(report['complete'])
            self.assertFalse(report['fifo_read_succeeded'])
            self.assertIsNone(report['event_bytes'])

    def test_missing_marker_or_non_byte_event_is_incomplete(self):
        for lines in ([line for line in BASE if 'touch FIFO and restore' not in line],
                      [line.replace('event000000003', 'event000000103') for line in BASE]):
            report = self.report(lines)
            self.assertFalse(report['complete'])
            self.assertFalse(report['fifo_read_succeeded'])


if __name__ == '__main__':
    unittest.main()
