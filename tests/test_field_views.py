import unittest
from unittest.mock import patch
from field_views import pass_network, goal_map
from fifa_reference import compare_substitutions
from build_player_photos import choose


class FieldTests(unittest.TestCase):
    def test_network_excludes_failed_other_team_and_future_passes(self):
        def passing(tid=1, outcome=None):
            p = {'recipient': {'id': 2, 'name': 'B'}, 'end_location': [60, 40]}
            if outcome: p['outcome'] = {'name': outcome}
            return {'type': {'name': 'Pass'}, 'team': {'id': tid}, 'player': {'id': 1, 'name': 'A'},
                    'location': [30, 40], 'pass': p}
        state = {'cutoff': 100, 'visible': [(50, passing()), (60, passing(outcome='Incomplete')),
                                           (70, passing(2)), (110, passing())]}
        _, rows = pass_network(state, 1)
        self.assertEqual(rows, [{'От': 'A', 'Кому': 'B', 'Успешных передач': 1}])

    def test_goal_maps_separate_teams_and_exclude_future(self):
        def shot(tid):
            return {'type': {'name': 'Shot'}, 'team': {'id': tid}, 'location': [110, 40],
                    'minute': 1, 'shot': {'outcome': {'name': 'Goal'}, 'statsbomb_xg': .2}}
        state = {'cutoff': 100, 'visible': [(20, shot(1)), (40, shot(2)), (120, shot(1))]}
        self.assertEqual(len(goal_map(state, 1)[1]), 1)
        self.assertEqual(len(goal_map(state, 1, True)[1]), 1)

    def test_identity_rejects_ambiguous_full_name(self):
        rows = [{'long_name': 'Diego Costa Silva', 'short_name': 'D. Costa'},
                {'long_name': 'Diego Costa Junior', 'short_name': 'D. Costa'}]
        self.assertIsNone(choose('Diego Costa', rows)[0])
        self.assertIsNone(choose('Costa', rows)[0])

    def test_missing_fifa_attributes_do_not_invent_scores(self):
        with patch('fifa_reference.photo_manifest', return_value={}):
            result = compare_substitutions([{'out_id': 1, 'in_id': 2, 'out': 'A', 'in': 'B'}], 'balanced')
        self.assertIsNone(result[0]['Разница индекса'])


if __name__ == '__main__':
    unittest.main()
