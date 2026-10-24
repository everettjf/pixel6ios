"""Fail-closed first-boot gates must run before any compilation or device action."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InventoryGateTests(unittest.TestCase):
    def reject(self, args, message, **extra_env):
        env = dict(os.environ, CROSS_CC='/nonexistent-inventory-compiler')
        env.pop('USB_DMA_HI_BASE', None)
        env.pop('USB_WINDOW', None)
        env.update(extra_env)
        p = subprocess.run(['bash', 'shim/build.sh', '--board', 'oriole'] + args,
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn(message, p.stderr)
        self.assertNotIn('nonexistent-inventory-compiler', p.stderr)

    def test_oriole_normal_boot_closed(self):
        self.reject([], 'oriole is inventory-only')

    def test_peripheral_and_payload_paths_closed(self):
        for args in [['--boot-xnu'], ['--udump', '1'], ['--touch-probe=rails'],
                     ['--gpu-job'], ['--wlan-link=27'], ['--dvfs', '100,100,100'],
                     ['--pstore-fast'], ['--qrlog'], ['payload.bin']]:
            with self.subTest(args=args):
                self.reject(['--inventory'] + args, '--inventory cannot run')

    def test_fixed_dma_override_closed(self):
        self.reject(['--inventory'], 'no USB_DMA_HI_BASE', USB_DMA_HI_BASE='0x880200000ULL')

    def test_window_bounded(self):
        for value in ['0', '61', '-1', 'garbage']:
            with self.subTest(value=value):
                self.reject(['--inventory'], 'USB_WINDOW must be 1..60', USB_WINDOW=value)


if __name__ == '__main__':
    unittest.main()
