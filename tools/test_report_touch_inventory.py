"""A truncated or faulting USB capture must not authorize touch bring-up."""
import unittest

from report_touch_inventory import captures, report_from_raw, summarize


def fixture():
    lines = ['cmu base 0x1: OPTION[0]=0 usi_mux[0]=0 bus_mux[0]=0 '
             'bus_auto[0]=0 usi_auto[0]=0 div[0]=0',
             'cmu_top 0x2: PERIC1_IP mux[0]=0 div[0]=0 gate[0]=0',
             'cmu gates: ipclk_4[0]=0 pclk_4[0]=0 rstnsync[0]=0 QCH[0]=0',
             'sysreg USI11 mode (0x3) = 0 (SPI = 0x1, so not SPI yet)']
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

    def test_cut_off_register_value_is_not_a_complete_dump(self):
        lines = fixture()
        lines[-1] = 'pin mux   bank 0x4[0] func='
        report = summarize(lines)
        self.assertFalse(report['complete'])
        self.assertIn('pin mux', report['missing'])
        lines = fixture()
        lines[3] = 'sysreg USI11 mode (0x3) ='
        report = summarize(lines)
        self.assertFalse(report['complete'])
        self.assertIn('sysreg USI11 mode', report['missing'])
        for index, label in enumerate(('cmu base', 'cmu_top', 'cmu gates')):
            lines = fixture()
            lines[index] = label
            report = summarize(lines)
            self.assertFalse(report['complete'])
            self.assertIn(label, report['missing'])

    def test_wrapped_cmu_line_is_rejoined_before_validation(self):
        lines = fixture()
        first = lines.pop(0)
        split = first.index('bus_auto')
        lines[0:0] = [first[:split].rstrip(), first[split:]]
        self.assertTrue(summarize(lines)['complete'])

    def test_read_fault_before_cmu_line_refuses_whole_log(self):
        lines = ['unreadable pa=0x1234 (value shown as 0)'] + fixture()
        raw = '\n'.join('SWEET TOUCH: ' + line for line in lines).encode()
        report = report_from_raw(raw)
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['read_faults']), 1)

    def test_no_touch_lines_yields_no_capture(self):
        self.assertEqual(captures(b'SWEET USB: event 0x0000c046\n'), [])


if __name__ == '__main__':
    unittest.main()
