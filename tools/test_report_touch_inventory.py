"""A truncated or faulting USB capture must not authorize touch bring-up."""
import unittest

from report_touch_inventory import captures, summarize


def fixture():
    lines = ['cmu base 0x1: OPTION[0]=0', 'cmu_top 0x2: PERIC1_IP mux[0]=0',
             'cmu gates: ipclk_4[0]=0',
             'sysreg USI11 mode (0x3) = 0 (SPI = 1, so not SPI yet)']
    lines += [f'pin {name:<5} bank 0x4[0] func=0 dat=0 pud=0'
              for name in ('clk', 'mosi', 'miso', 'cs', 'irq', 'reset', 'mux')]
    return lines


class TouchInventoryReportTests(unittest.TestCase):
    def test_complete_dump_and_replayed_partial_dump_stay_separate(self):
        full = fixture()
        raw = ('\n'.join('0001 SWEET TOUCH: ' + line for line in full)
               + '\nSWEET TOUCH: cmu base 0x1: OPTION[0]=0\n').encode()
        datasets = captures(raw)
        self.assertEqual(len(datasets), 2)
        self.assertTrue(summarize(datasets[0])['complete'])
        self.assertFalse(summarize(datasets[1])['complete'])

    def test_missing_pin_and_read_fault_refuse_completion(self):
        report = summarize(fixture()[:-1])
        self.assertFalse(report['complete'])
        self.assertIn('pin mux', report['missing'])
        report = summarize(fixture() + ['unreadable pa=0x1234 (value shown as 0)'])
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['read_faults']), 1)

    def test_no_touch_lines_yields_no_capture(self):
        self.assertEqual(captures(b'SWEET USB: event 0x0000c046\n'), [])


if __name__ == '__main__':
    unittest.main()
