import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MetricTests(unittest.TestCase):
    def test_perfect_predictions_have_perfect_classification(self):
        import numpy as np
        from measure_metrics import extended_metrics
        y = np.array([0, 1, 2, 0, 1, 2])
        r = extended_metrics(y, np.eye(3)[y])
        self.assertEqual(r['f1_macro'], 1.)
        self.assertEqual(r['mcc'], 1.)
        self.assertEqual(r['cohen_kappa'], 1.)
        self.assertAlmostEqual(r['ece_top_label_10_bins'], 0., places=4)

    def test_ece_detects_confident_errors(self):
        import numpy as np
        from measure_metrics import extended_metrics
        y = np.array([0, 1, 2])
        p = np.array([[.01, .98, .01], [.01, .01, .98], [.98, .01, .01]])
        self.assertGreater(extended_metrics(y, p)['ece_top_label_10_bins'], .9)


if __name__ == '__main__': unittest.main()
