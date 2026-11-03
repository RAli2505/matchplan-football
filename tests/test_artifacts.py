import json
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TrainedArtifactsTests(unittest.TestCase):
    def test_splits_and_selection_are_auditable(self):
        report = json.loads((ROOT / 'reports/ml_results.json').read_text(encoding='utf-8'))
        self.assertEqual([x['matches'] for x in report['splits'].values()], [266, 57, 57])
        groups = [set(x['match_ids']) for x in report['splits'].values()]
        self.assertEqual(len(set.union(*groups)), 380)
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual(len(report['models']), 6)
        winner = min(report['models'], key=lambda k: report['models'][k]['validation']['log_loss'])
        self.assertEqual(report['selected_by_validation'], winner)

    def test_saved_models_reproduce_published_test_predictions(self):
        from core import match_data, timeline, seconds
        from ml_runtime import predict_all
        frame = pd.read_csv(ROOT / 'reports/test_predictions.csv')
        row = frame[frame['minute'] == 60].iloc[0]
        mid, tid = int(row['match_id']), int(row['team_id'])
        es, ls = match_data(mid)
        home = next(e['team']['id'] for e in es if e['type']['name'] == 'Starting XI')
        # Home identity from match metadata is authoritative, not event order.
        from core import matches
        game = next(m for m in matches(2, 27) if m['match_id'] == mid)
        home = game['home_team']['home_team_id']
        cutoff = max(t for t, e in timeline(es) if e['period'] == 2 and seconds(e) <= 15*60)
        _, probabilities = predict_all(es, ls, cutoff, tid, home)
        for name, p in probabilities.items():
            published = frame[(frame['model'] == name) & (frame['match_id'] == mid) &
                              (frame['team_id'] == tid) & (frame['minute'] == 60)].iloc[0]
            np.testing.assert_allclose(p, published[['p_loss', 'p_draw', 'p_win']].to_numpy(dtype=float), atol=1e-5)
            self.assertAlmostEqual(sum(p), 1., places=6)


if __name__ == '__main__': unittest.main()
