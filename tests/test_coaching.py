import unittest
from test_core import fixture, event
from core import snapshot, recommend, competition_rules
from coaching import tactical_options, freeze_plan, review_plan, formation_choice
from coach_audit import audit_formations
from tactical_playbook import detailed_instructions
from tactics import FORMATIONS


class CoachingTests(unittest.TestCase):
    def test_twelve_tasks_have_current_player_assignments_and_saved_details(self):
        es, ls = fixture()
        s = snapshot(es, ls, 0)
        options = tactical_options(s, 1, 'win')
        self.assertEqual(len({o['key'] for o in options}), 24)
        names = {p['name'] for p in s['players'][1].values()}
        for option in options:
            detail = detailed_instructions(s, 1, option)
            self.assertEqual(len(detail['phases']), 4)
            self.assertTrue(all(p['Игрок'] in names for p in detail['assignments']))
            self.assertTrue(all(p['Задача'] for p in detail['assignments']))
            self.assertEqual(freeze_plan(s, 1, 'win', option, 5)['details'], detail)

    def test_nine_formations_are_complete_and_unique(self):
        self.assertEqual(len(FORMATIONS), 14)
        for roles in FORMATIONS.values():
            self.assertEqual(len(roles), 11)
            self.assertEqual(len(set(roles)), 11)

    def test_short_handed_team_is_not_offered_counterpress(self):
        es, ls = fixture()
        s = snapshot(es, ls, 0)
        s['players'][1].pop(102)
        options = {o['key']: o for o in tactical_options(s, 1, 'win')}
        self.assertFalse(options['counterpress']['available'])
        self.assertFalse(options['press']['available'])

    def test_future_events_not_scored_before_plan_ends(self):
        es, ls = fixture()
        es += [event('Pass', 600), event('Shot', 750, tid=2, shot={'statsbomb_xg': .3})]
        s = snapshot(es, ls, 600)
        plan = freeze_plan(s, 1, 'win', tactical_options(s, 1, 'win')[0], 5)
        review = review_plan(plan, es, ls, 700, competition_rules(2, 27))
        self.assertFalse(review['ready'])
        self.assertNotIn('theirs', review)

    def test_follow_up_excludes_boundary_and_future(self):
        es, ls = fixture()
        es += [event('Shot', 600, tid=1, shot={'statsbomb_xg': .1}),
               event('Shot', 750, tid=2, shot={'statsbomb_xg': .3}),
               event('Shot', 950, tid=2, shot={'statsbomb_xg': .9})]
        s = snapshot(es, ls, 600)
        plan = freeze_plan(s, 1, 'win', tactical_options(s, 1, 'win')[0], 5)
        r = review_plan(plan, es, ls, 1000, competition_rules(2, 27))
        self.assertTrue(r['ready'])
        self.assertEqual(r['ours']['shots'], 0)
        self.assertEqual(r['theirs']['shots'], 1)
        self.assertAlmostEqual(r['theirs']['xg'], .3)

    def test_shortlist_is_legal_and_bounded(self):
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 1500, period=2)]
        s = snapshot(es, ls, 5000)
        options = recommend(s, 1, roles={112: 'Center Forward', 113: 'Center Forward'})['sub_options']
        self.assertEqual(len(options), 3)
        self.assertEqual(len({(x['out_id'], x['in_id']) for x in options}), 3)
        for x in options:
            self.assertIn(x['out_id'], s['players'][1])
            self.assertIn(x['in_id'], s['bench'][1])
        s['subs'][1] = 5
        self.assertFalse(recommend(s, 1, roles={112: 'Center Forward'})['sub_options'])

    def test_formation_requires_eleven_and_excludes_bench(self):
        es, ls = fixture()
        s = snapshot(es, ls, 0)
        choice = formation_choice(s, 1, {}, {})
        self.assertIsNotNone(choice)
        self.assertEqual({p['id'] for p in choice['lineup']}, set(s['players'][1]))
        s['players'][1].pop(102)
        self.assertIsNone(formation_choice(s, 1, {}, {}))

    def test_future_formation_shift_not_exposed(self):
        es, ls = fixture()
        es += [event('Tactical Shift', 600, tactics=dict(es[0]['tactics'], formation=442))]
        result = audit_formations(es, ls, 1, {}, {}, competition_rules(2, 27), cutoff=0)
        self.assertEqual(result['actual_count'], 0)


if __name__ == '__main__':
    unittest.main()
