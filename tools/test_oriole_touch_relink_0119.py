"""Regression tests for the exact private-symbol exception in the 0119 relink."""

from collections import Counter
from pathlib import Path
import runpy
import unittest


AUDIT = runpy.run_path(str(Path(__file__).with_name('relink-oriole-touch-xnu-0119.py')))


class Table(dict):
    def __init__(self):
        super().__init__()
        self.record_counts = Counter()


def valid_pair():
    old, new = Table(), Table()
    for table in (old, new):
        table['__public'] = (0x1100, True)
        table.record_counts[('__public', 0x0f)] = 1
    for (name, typ), count in AUDIT['EXPECTED_REMOVED_LOCALS'].items():
        old[name] = (0x1200, False)
        old.record_counts[(name, typ)] = count + (1 if name.startswith('lJTI') else 0)
        if name.startswith('lJTI'):
            new[name] = (0x1200, False)
            new.record_counts[(name, typ)] = 1
    for (name, typ), count in AUDIT['EXPECTED_ADDED_LOCALS'].items():
        new[name] = (0x1300, False)
        new.record_counts[(name, typ)] = count
    return old, new


class SymbolAuditTests(unittest.TestCase):
    def verify(self, old, new):
        AUDIT['verify_symbol_delta'](old, new, (0x1000, 0x1000, 0x4000, 0x800, 5, 5))

    def test_exact_private_delta(self):
        self.verify(*valid_pair())

    def test_extra_local_rejected(self):
        old, new = valid_pair()
        new.record_counts[('__surprise', 0x0e)] = 1
        with self.assertRaises(SystemExit):
            self.verify(old, new)

    def test_global_change_rejected(self):
        old, new = valid_pair()
        new.record_counts[('__public', 0x0f)] = 2
        with self.assertRaises(SystemExit):
            self.verify(old, new)

    def test_scope_promotion_rejected(self):
        old, new = valid_pair()
        new['__public'] = (0x1100, False)
        with self.assertRaises(SystemExit):
            self.verify(old, new)

    def test_duplicate_record_rejected(self):
        old, new = valid_pair()
        new.record_counts[('_tg_oriole_rail_xfer', 0x0e)] = 2
        with self.assertRaises(SystemExit):
            self.verify(old, new)

    def test_local_outside_executable_segment_rejected(self):
        old, new = valid_pair()
        new['_tg_oriole_rail_xfer'] = (0x1900, False)
        with self.assertRaises(SystemExit):
            self.verify(old, new)


if __name__ == '__main__':
    unittest.main()
