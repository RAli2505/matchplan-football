import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import (card, decision_log, historical_roles, match_data, matches, metrics,
                  historical_profiles, propose_lineup, recommend, snapshot, timeline)


def event(kind, sec=0, period=1, tid=1, **kwargs):
    return {'type': {'name': kind}, 'team': {'id': tid}, 'period': period,
            'timestamp': f'00:{sec//60:02}:{sec%60:02}.000',
            'minute': sec//60 + (45 if period == 2 else 0), **kwargs}


def fixture():
    lineups = [{'team_id': tid, 'lineup': [{'player_id': tid*100+i, 'player_name': f'P{tid*100+i}',
        'jersey_number': i} for i in range(1, 14)]} for tid in (1, 2)]
    events = [event('Starting XI', tid=tid, tactics={'formation': 433, 'lineup': [
        {'player': {'id': tid*100+i, 'name': f'P{tid*100+i}'},
         'position': {'name': 'Goalkeeper' if i == 1 else 'Center Forward' if i >= 9 else 'Center Midfield'},
         'jersey_number': i} for i in range(1, 12)]}) for tid in (1, 2)]
    return events, lineups


class ReplayTests(unittest.TestCase):
    def test_retained_plan_has_consistent_actions_and_alternative(self):
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 25*60, period=2)]
        s = snapshot(es, ls, 5000)
        r = recommend(s, 1, 'win', roles={112: 'Center Forward'}, plan_override='balanced')
        self.assertEqual(r['plan'], 'balanced')
        self.assertIn('Сохранить текущую структуру', r['attack'])
        self.assertIn(r['attack'], r['actions'])
        self.assertNotEqual(r['alternative'], r['plan'])
        self.assertIn(r['alternative'], r['scores'])

    def test_coach_comparison_cannot_reveal_future_substitutions(self):
        from coach_audit import audit_substitutions
        from core import competition_rules
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 25*60, period=2),
               event('Substitution', 26*60, period=2, player={'id': 109},
                     substitution={'replacement': {'id': 112, 'name': 'P112'}})]
        result = audit_substitutions(es, ls, 1, {112: 'Center Forward'}, competition_rules(2, 27), cutoff=0)
        self.assertEqual(result['actual_count'], 0)

    def test_historical_premier_league_three_substitutions(self):
        from core import competition_rules
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 25*60, period=2)]
        s = snapshot(es, ls, 5000, rules=competition_rules(2, 27))
        s['subs'][1] = 3
        self.assertFalse(recommend(s, 1, roles={112: 'Center Forward'})['subs_allowed'])
        s['subs'][1] = 2
        self.assertTrue(recommend(s, 1, roles={112: 'Center Forward'})['subs_allowed'])

    def test_dismissed_reserve_is_not_available(self):
        es, ls = fixture()
        es += [event('Bad Behaviour', 80, player={'id': 112}, bad_behaviour={'card': {'name': 'Red Card'}})]
        s = snapshot(es, ls, 90)
        self.assertNotIn(112, s['bench'][1])
        self.assertIn(112, s['removed'])
        self.assertEqual(s['red'][1], 0)

    def test_substitutions_same_stoppage_one_window(self):
        es, ls = fixture()
        es += [event('Substitution', 60, player={'id': 109}, substitution={'replacement': {'id': 112, 'name': 'P112'}}),
               event('Substitution', 65, player={'id': 110}, substitution={'replacement': {'id': 113, 'name': 'P113'}}),
               event('Pass', 80)]
        s = snapshot(es, ls, 90)
        self.assertEqual(s['subs'][1], 2)
        self.assertEqual(len(s['windows'][1]), 1)

    def test_prematch_exclusions_and_unknown_roles(self):
        es, ls = fixture()
        s = snapshot(es, ls, 0)
        proposed = propose_lineup(s, 1, {112: 'Center Forward'}, {}, [109])
        self.assertEqual(len(proposed), 11)
        self.assertNotIn(109, [p['id'] for p in proposed])
        self.assertIn(112, [p['id'] for p in proposed])
        self.assertEqual(len(set(p['id'] for p in proposed)), 11)
        no_keepers = propose_lineup(s, 1, {}, {}, [101])
        self.assertTrue(any(p['id'] < 0 for p in no_keepers))

    def test_goals_own_goal_and_no_double_count(self):
        es, ls = fixture()
        es += [event('Shot', 60, shot={'outcome': {'name': 'Goal'}, 'statsbomb_xg': .3}),
               event('Own Goal Against', 70, tid=1), event('Own Goal For', 70, tid=2)]
        before = snapshot(es, ls, 0)
        after = snapshot(es, ls, 80)
        self.assertEqual(dict(before['goals']), {})
        self.assertEqual(after['goals'][1], 1)
        self.assertEqual(after['goals'][2], 1)

    def test_future_lineup_metadata_not_used(self):
        es, ls = fixture()
        a = snapshot(es, ls, 0)
        dirty = copy.deepcopy(ls)
        dirty[0]['lineup'][0]['cards'] = [{'card_type': 'Red Card'}]
        dirty[0]['lineup'][0]['positions'] = [{'position': 'Center Forward', 'from': '75:00'}]
        b = snapshot(es, dirty, 0)
        self.assertEqual(a, b)

    def test_sub_red_and_tactical_resurrection(self):
        es, ls = fixture()
        es += [event('Substitution', 60, player={'id': 109}, substitution={'replacement': {'id': 112, 'name': 'P112'}}),
               event('Foul Committed', 65, player={'id': 110}, foul_committed={'card': {'name': 'Second Yellow'}}),
               event('Tactical Shift', 70, tactics=copy.deepcopy(es[0]['tactics']))]
        s = snapshot(es, ls, 80)
        self.assertNotIn(109, s['players'][1])
        self.assertNotIn(110, s['players'][1])
        self.assertIn(112, s['players'][1])
        self.assertNotIn(112, s['bench'][1])
        self.assertEqual(len(s['players'][1]), 10)
        self.assertEqual(s['red'][1], 1)

    def test_period_overlap(self):
        es, ls = fixture()
        es += [event('Shot', 47*60, shot={'outcome': {'name': 'Goal'}}),
               event('Half End', 48*60), event('Half Start', 0, period=2)]
        ts = timeline(es)
        second_start = ts[-1][0]
        self.assertGreater(second_start, ts[-2][0])
        self.assertEqual(snapshot(es, ls, second_start)['goals'][1], 1)
        self.assertEqual(snapshot(es, ls, 46*60)['goals'][1], 0)

    def test_target_changes_plan_at_70(self):
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 25*60, period=2)]
        s = snapshot(es, ls, 5000)
        self.assertEqual(recommend(s, 1, 'win')['plan'], 'attacking')
        self.assertEqual(recommend(s, 1, 'draw')['plan'], 'cautious')

    def test_only_known_compatible_bench(self):
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 25*60, period=2)]
        s = snapshot(es, ls, 5000)
        self.assertIsNone(recommend(s, 1)['sub'])
        sub = recommend(s, 1, roles={112: 'Center Forward'})['sub']
        self.assertEqual(sub['in'], 'P112')
        self.assertIn(sub['out'], ['P109', 'P110', 'P111'])
        s['subs'][1] = 5
        self.assertIsNone(recommend(s, 1, roles={112: 'Center Forward'})['sub'])

    def test_window_limit_and_halftime(self):
        es, ls = fixture()
        es += [event('Half End', 2700), event('Pass', 25*60, period=2)]
        s = snapshot(es, ls, 5000)
        s['windows'][1] = {(1, 100), (1, 200), (2, 300)}
        self.assertFalse(recommend(s, 1)['subs_allowed'])
        s['last'] = event('Half Start', 0, period=2)
        self.assertTrue(recommend(s, 1)['subs_allowed'])

    def test_fifteen_minute_window(self):
        es, ls = fixture()
        es += [event('Shot', 60, shot={'statsbomb_xg': .5}), event('Pass', 1200)]
        s = snapshot(es, ls, 1200)
        self.assertEqual(metrics(s, 1)['xg'], 0)
        self.assertEqual(metrics(s, 1, window=0)['xg'], .5)

    def test_finished(self):
        es, ls = fixture()
        es += [event('Half End', 2700), event('Half End', 2700, period=2)]
        self.assertTrue(recommend(snapshot(es, ls, 6000), 1)['finished'])


class DatasetTests(unittest.TestCase):
    def test_all_matches_final_score_and_squads(self):
        for m in matches():
            with self.subTest(match=m['match_id']):
                es, ls = match_data(m['match_id'])
                end = max(t for t, _ in timeline(es)) + 1
                s = snapshot(es, ls, end)
                self.assertEqual(s['goals'][m['home_team']['home_team_id']], m['home_score'])
                self.assertEqual(s['goals'][m['away_team']['away_team_id']], m['away_score'])
                for tid, players in s['players'].items():
                    self.assertLessEqual(len(players), 11)
                    self.assertFalse(set(players) & set(s['bench'][tid]))
                    self.assertFalse(set(players) & s['removed'])

    def test_truncating_future_does_not_change_current_decision(self):
        es, ls = match_data(matches()[5]['match_id'])
        timed = timeline(es)
        cutoff = 1800
        prefix = [e for t, e in timed if t <= cutoff]
        for tid in [x['team_id'] for x in ls]:
            a = recommend(snapshot(es, ls, cutoff), tid)
            b = recommend(snapshot(prefix, ls, cutoff), tid)
            self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
