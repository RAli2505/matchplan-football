import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from test_core import fixture,event
from core import snapshot
from decision_support import (compare_plans,build_package,package_changes,evidence_support,
    checklist_items,save_execution,load_execution)
from decision_history import find_similar
from attack_chains import attack_chains,chain_diagram
from match_insights import territory,set_piece_summary,coach_report_html


class DecisionSupportTests(unittest.TestCase):
    def state(self):
        es,ls=fixture()
        es += [event('Half End',2700),event('Pass',1200,period=2)]
        return snapshot(es,ls,4000),es,ls

    def test_comparison_has_three_plans_and_does_not_mutate(self):
        state,_,_=self.state(); before=deepcopy(state)
        plans=compare_plans(state,1,'win',{112:'Center Forward'})
        self.assertEqual({p['key'] for p in plans},{'attacking','balanced','cautious'})
        self.assertEqual(state,before)

    def test_package_has_exactly_legal_replacement_and_complete_roles(self):
        state,_,_=self.state(); before=deepcopy(state)
        package=build_package(state,1,'win',{112:'Center Forward'}, {},'attacking',0)
        sub=package['substitution']
        self.assertIn(sub['out_id'],state['players'][1]); self.assertIn(sub['in_id'],state['bench'][1])
        expected=set(state['players'][1])-{sub['out_id']}|{sub['in_id']}
        self.assertEqual(set(package['roster']),expected)
        self.assertEqual({p['id'] for p in package['formation']['lineup']},expected)
        self.assertTrue(all(p['Игрок']!=state['players'][1][sub['out_id']]['name'] for p in package['plan']['details']['assignments']))
        self.assertEqual(state,before)
        with self.assertRaises(ValueError):build_package(state,1,'win',{}, {},'attacking',99)

    def test_cautious_package_does_not_add_pressing_and_no_fake_eleventh_player(self):
        state,_,_=self.state(); state['players'][1].pop(102)
        package=build_package(state,1,'draw',{}, {},'cautious')
        self.assertIsNone(package['formation'])
        self.assertEqual(len(package['roster']),10)
        self.assertNotIn(package['task']['key'],('press','counterpress','width'))

    def test_persistence_restores_without_false_stale_score_or_lost_notes(self):
        state,_,_=self.state(); package=build_package(state,1,'win',{}, {})
        statuses={item['id']:'Выполнено' for item in checklist_items(package)}
        with tempfile.TemporaryDirectory() as directory:
            save_execution(package,42,1,statuses,'My <script>note</script>',directory)
            restored=load_execution(42,1,directory)['decisions'][package['id']]
            self.assertEqual(restored['note'],'My <script>note</script>')
            self.assertFalse(package_changes(restored['package'],state,1,'win'))
            with self.assertRaises(ValueError): save_execution(package,42,1,{},'',directory)
        state['goals'][2]=1
        self.assertTrue(package_changes(package,state,1))

    def test_horizon_changes_decision_identity_and_cold_evidence_is_limited(self):
        state,_,_=self.state()
        a=build_package(state,1,'win',{}, {},horizon=5)
        b=build_package(state,1,'win',{}, {},horizon=10)
        self.assertNotEqual(a['id'],b['id'])
        es,ls=fixture(); cold=snapshot(es,ls,0)
        support=evidence_support(cold,1,a['task'])
        self.assertIn('Недостаточно',support['level'])

    def test_similarities_use_only_earlier_distinct_matches(self):
        query={'minute':60,'score_diff':0,'man_diff':0,'xg_delta':0,'entries_delta':0}
        rows=[{'date':date,'match_id':mid,'team_id':tid,'features':dict(query),'result':result}
              for date,mid,tid,result in [('2015-01-01',1,1,'Поражение'),('2015-01-01',1,2,'Победа'),
                  ('2015-01-02',2,1,'Победа'),('2015-01-03',3,1,'Победа'),('2015-01-04',4,1,'Победа')]]
        rows.append({'date':'2015-01-01','match_id':5,'team_id':1,'features':dict(query,man_diff=-1),'result':'Ничья'})
        found=find_similar(rows,query,'2015-01-03',2)
        self.assertEqual([r['match_id'] for r in found],[1])
        self.assertEqual(found[0]['result'],'Поражение') # Do not cherry-pick winners.
        self.assertEqual(find_similar(rows,dict(query,minute=0),'2015-01-03',2),[])

    def test_chains_exclude_future_and_other_possessions(self):
        es,ls=fixture()
        es += [event('Pass',100,possession=3,location=[30,40],**{'pass':{'end_location':[60,40]}}),
               event('Carry',110,possession=3,location=[60,40],carry={'end_location':[90,40]}),
               event('Pass',115,possession=4,location=[20,40],**{'pass':{'end_location':[70,40]}}),
               event('Shot',120,id='shot',possession=3,location=[105,40],shot={'statsbomb_xg':.3}),
               event('Shot',160,id='future',possession=3,shot={'statsbomb_xg':.9})]
        chains=attack_chains(snapshot(es,ls,140),1)
        self.assertEqual(len(chains),1)
        self.assertEqual([e['kind'] for e in chains[0]['events']],['Pass','Carry','Shot'])
        self.assertIn('<svg',chain_diagram(chains[0]))

    def test_unknown_possession_is_not_joined_and_html_is_escaped(self):
        es,ls=fixture(); es += [event('Pass',100),event('Shot',120,shot={'statsbomb_xg':.2})]
        state=snapshot(es,ls,140)
        chain=attack_chains(state,1)[0]
        self.assertEqual(len(chain['events']),1); self.assertFalse(chain['possession_known'])
        document=coach_report_html(state,1,{1:'<script>A</script>',2:'B'},1,
                                  execution={'note':'<script>alert(1)</script>'})
        self.assertNotIn('<script>',document)
        self.assertIn('&lt;script&gt;',document)

    def test_territory_and_set_pieces_are_cutoff_limited(self):
        es,ls=fixture()
        es += [event('Pass',t,tid=team,location=[90,40],**{'pass':{}}) for t,team in ((10,1),(20,1),(30,2),(500,2))]
        es += [event('Shot',50,play_pattern={'name':'From Corner'},shot={'statsbomb_xg':.2}),
               event('Shot',60,tid=2,shot={'type':{'name':'Penalty'},'statsbomb_xg':.78})]
        state=snapshot(es,ls,100)
        self.assertAlmostEqual(territory(state,1)['share'],2/3)
        rows=set_piece_summary(state,1)
        self.assertEqual({r['Ситуация'] for r in rows},{'После углового','Пенальти'})
        self.assertAlmostEqual(sum(r['xG'] for r in rows),.98)


if __name__=='__main__':unittest.main()
