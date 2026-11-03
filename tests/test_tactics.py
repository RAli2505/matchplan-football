import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class AssignmentTests(unittest.TestCase):
    def test_assignment_does_not_waste_flexible_player(self):
        from tactics import assign_roles
        scores = {1: [9, 8], 2: [7, None]}
        assignment, score = assign_roles(scores, 2)
        self.assertEqual(assignment, [2, 1])
        self.assertEqual(score, 15)

    def test_unknown_roles_are_gaps(self):
        from tactics import assign_roles
        assignment, score = assign_roles({1: [None, None]}, 2)
        self.assertEqual(assignment, [None, None])

    def test_unavailable_players_never_selected(self):
        from tactics import formation_options
        from test_core import fixture
        from core import snapshot
        es, ls = fixture()
        s = snapshot(es, ls, 0)
        options = formation_options(s, 1, {}, {}, unavailable=[101, 109])
        for option in options:
            self.assertEqual(len(option['lineup']), 11)
            ids = [p['id'] for p in option['lineup'] if p['id'] > 0]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertNotIn(101, ids)
            self.assertNotIn(109, ids)
            self.assertGreater(option['gaps'], 0)

    def test_opponent_profile_uses_only_supplied_history(self):
        from tactics import opponent_profile
        from test_core import fixture, event
        es, ls = fixture()
        es += [event('Shot', 60, tid=2, shot={'statsbomb_xg': .2}),
               event('Pass', 70, tid=2, location=[40, 10], **{'pass': {'end_location': [90, 10]}}),
               event('Half End', 2700), event('Half End', 2700, period=2)]
        p = opponent_profile([es], 2)
        self.assertEqual(p['matches'], 1)
        self.assertEqual(p['shots_per_match'], 1)
        self.assertEqual(p['attack_channel'], 'left')
        self.assertEqual(opponent_profile([], 2)['matches'], 0)

    def test_manual_scenario_leaves_recording_untouched(self):
        from tactics import scenario_state
        from test_core import fixture
        from core import snapshot
        es, ls = fixture()
        s = snapshot(es, ls, 0)
        custom = scenario_state(s, 1, 1, 0, [109], [112])
        self.assertEqual(custom['goals'][1], 1)
        self.assertNotIn(109, custom['players'][1])
        self.assertNotIn(112, custom['bench'][1])
        self.assertIn(109, s['players'][1])
        self.assertIn(112, s['bench'][1])
        self.assertEqual(s['goals'][1], 0)


if __name__ == '__main__': unittest.main()
