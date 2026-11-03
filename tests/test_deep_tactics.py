import unittest
from core import snapshot
from test_core import fixture,event
from deep_tactics import diagnose,deep_options,diagnostic_map
from coaching import freeze_plan,review_plan
from core import competition_rules


class DeepTacticsTests(unittest.TestCase):
    def test_shot_assist_requires_visible_subsequent_shot(self):
        es,ls=fixture()
        es += [event('Pass',100,id='p',player={'id':109,'name':'P109'},location=[90,40],
                     under_pressure=True,**{'pass':{'assisted_shot_id':'shot'}}),
               event('Shot',110,id='shot',shot={'statsbomb_xg':.2},location=[110,40])]
        before=diagnose(snapshot(es,ls,105),1)
        after=diagnose(snapshot(es,ls,120),1)
        self.assertEqual(before['counts'].get('shot_assists',0),0)
        self.assertEqual(after['counts']['shot_assists'],1)
        self.assertEqual(after['counts']['pressured_passes'],1)
        self.assertTrue(any(x['tag'].startswith('Передача под') for x in after['locations']))
        self.assertEqual(after['creators'][0]['Игрок'],'P109')

    def test_pressure_advice_needs_sufficient_flagged_passes(self):
        es,ls=fixture()
        es += [event('Pass',i*10,under_pressure=True,**{'pass':{'outcome':{'name':'Incomplete'}}}) for i in range(1,9)]
        task=next(x for x in deep_options(snapshot(es,ls,100),1,'win') if x['key']=='pressure_support')
        self.assertTrue(task['available'])
        early=next(x for x in deep_options(snapshot(es,ls,40),1,'win') if x['key']=='pressure_support')
        self.assertFalse(early['available'])

    def test_transition_shots_are_deduplicated_and_stopped_by_control(self):
        es,ls=fixture()
        es += [event('Miscontrol',100),event('Dispossessed',101),
               event('Shot',108,tid=2,id='s1',shot={'statsbomb_xg':.2}),
               event('Miscontrol',200),event('Carry',201),
               event('Shot',205,tid=2,id='s2',shot={'statsbomb_xg':.3})]
        report=diagnose(snapshot(es,ls,300),1)
        self.assertEqual(report['counts']['shots_after_loss'],1)
        self.assertAlmostEqual(report['counts']['xg_after_loss'],.2)
        self.assertEqual(len(report['episodes']),1)

    def test_followup_does_not_use_assist_or_event_from_future(self):
        es,ls=fixture()
        es += [event('Pass',t,under_pressure=True,**{'pass':{}}) for t in (350,400,500,600,750,950)]
        state=snapshot(es,ls,600)
        task=deep_options(state,1,'win')[0]
        plan=freeze_plan(state,1,'win',task,5)
        result=review_plan(plan,es,ls,1000,competition_rules(2,27))
        row=next(x for x in result['task_metrics'] if x['Показатель']=='Наши передачи под отмеченным давлением')
        self.assertEqual(row['До плана / мин'],.8)
        self.assertEqual(row['После плана / мин'],.2)
        self.assertIn('<svg',diagnostic_map(diagnose(state,1)))


if __name__=='__main__':unittest.main()
