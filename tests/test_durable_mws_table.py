"""Table consumers preserve the retained three-arm Linux measurement boundary."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_durable_mws as renderer


class DurableTableTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((renderer.DATA / 'verified-summary.json').read_text())

    def test_actual_retained_medians_all_arms(self):
        text = renderer.table(self.result)
        self.assertIn('Sparse cut & 1704.67 & 1686.94 & 1792.73', text)
        self.assertIn('Dense cut & 3375.37 & 3392.32 & 3426.95', text)
        self.assertIn('Low conflict & 696.07 & 622.08 & 657.99', text)
        self.assertIn('Linux durable workflows', text)
        self.assertEqual(len(self.result['costs_128_handles']), 9)

    def test_missing_control_arm_refuses(self):
        self.result['costs_128_handles'] = [r for r in self.result['costs_128_handles']
                                          if r['implementation'] != 'scanning']
        with self.assertRaisesRegex(ValueError, 'all three arms'):
            renderer.table(self.result)

    def test_wrong_sample_denominator_refuses(self):
        self.result['costs_128_handles'][0]['seeds'] = 3
        with self.assertRaisesRegex(ValueError, 'two complete'):
            renderer.table(self.result)


if __name__ == '__main__':
    unittest.main()
