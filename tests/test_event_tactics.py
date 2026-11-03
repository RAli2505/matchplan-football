import unittest
from core import snapshot
from test_core import fixture, event
from event_tactics import indicators, event_options, recent_changes, action_diagram
from coaching import freeze_plan, review_plan
from core import competition_rules


class EventTacticsTests(unittest.TestCase):
    def test_safe_exit_uses_current_team_and_visible_evidence_only(self):
        es, ls = fixture()
        es += [event('Miscontrol', t, tid=1, location=[20,30]) for t in (100,200,300)]
        es += [event('Miscontrol', 350, tid=2, location=[20,30]),
               event('Miscontrol', 500, tid=1, location=[20,30])]
        s = snapshot(es, ls, 400)
        a, evidence = indicators(s,1)
        self.assertEqual(a['deep_losses'], 3)
        task = next(o for o in event_options(s,1,'win') if o['key']=='safe_exit')
        self.assertTrue(task['available'])
        self.assertEqual(len(task['event_evidence']),3)

    def test_low_quality_shots_need_three_observations(self):
        es,ls=fixture()
        es += [event('Shot',t,tid=1,location=[90,40],shot={'statsbomb_xg':.02}) for t in (100,200,300)]
        early = next(o for o in event_options(snapshot(es,ls,250),1,'win') if o['key']=='shot_selection')
        later = next(o for o in event_options(snapshot(es,ls,350),1,'win') if o['key']=='shot_selection')
        self.assertFalse(early['available']); self.assertTrue(later['available'])

    def test_task_review_measures_only_followup_interval(self):
        es,ls=fixture()
        es += [event('Miscontrol',t,tid=1,location=[20,30]) for t in (350,400,500,600,750,950)]
        s=snapshot(es,ls,600)
        option=next(o for o in event_options(s,1,'win') if o['key']=='safe_exit')
        plan=freeze_plan(s,1,'win',option,5)
        r=review_plan(plan,es,ls,1000,competition_rules(2,27))
        row=next(x for x in r['task_metrics'] if x['Показатель']=='Потери в своей трети')
        self.assertEqual(row['До плана / мин'],.8)
        self.assertEqual(row['После плана / мин'],.2)

    def test_trend_boundary_belongs_to_only_one_window(self):
        es,ls=fixture()
        es += [event('Miscontrol',t,tid=1,location=[20,30]) for t in (300,600,700)]
        s=snapshot(es,ls,600)
        rows=recent_changes(s,1)
        row=next(r for r in rows if r['Показатель']=='Потери в своей трети')
        self.assertEqual(row['Предыдущие 5 минут'],1)
        self.assertEqual(row['Последние 5 минут'],1)
        self.assertEqual(recent_changes(snapshot(es,ls,500),1),[])
        self.assertIn('<svg',action_diagram('safe_exit'))


if __name__=='__main__': unittest.main()
