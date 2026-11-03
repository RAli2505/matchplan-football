import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MLDataTests(unittest.TestCase):
    def test_temporal_split_has_no_match_overlap(self):
        from ml_data import temporal_split
        ids = [i for i in range(34) for _ in range(4)]
        train, validation, test = temporal_split(ids)
        sets = [{ids[i] for i in part} for part in (train, validation, test)]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        self.assertLess(max(sets[0]), min(sets[1]))
        self.assertLess(max(sets[1]), min(sets[2]))

    def test_sequence_does_not_include_future(self):
        import numpy as np
        from ml_data import make_sequence
        from core import snapshot
        from test_core import fixture, event
        es, ls = fixture()
        prefix = es + [event('Pass', 600)]
        future = prefix + [event('Shot', 1200, shot={'outcome': {'name': 'Goal'}, 'statsbomb_xg': .8})]
        a, na = make_sequence(prefix, ls, 600, 1, 1)
        b, nb = make_sequence(future, ls, 600, 1, 1)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(na, nb)

    def test_last_sequence_row_matches_current_features(self):
        import numpy as np
        from ml_data import make_sequence, features
        from core import snapshot
        from test_core import fixture, event
        es, ls = fixture()
        es += [event('Pass', 600)]
        sequence, length = make_sequence(es, ls, 600, 1, 1)
        np.testing.assert_allclose(sequence[length-1], features(snapshot(es, ls, 600), 1, 1))


if __name__ == '__main__': unittest.main()
