import copy
import unittest
import numpy as np
from test_core import event
from event_adapter import coordinates,possession_patterns
from expected_threat import empty_counts,add_events,solve,rate_actions,surface_for_date,cell,L,W
from match_lab import phase_comparison,network_analysis,progression,xt_summary


def pass_event(sec,a=1,b=2,start=(30,40),end=(70,40),**kw):
    return event('Pass',sec,player={'id':a,'name':f'P{a}'},location=list(start),
                 **{'pass':{'recipient':{'id':b,'name':f'P{b}'},'end_location':list(end)},**kw})


def state(events,cutoff=1200):
    return {'visible':[(float(int(e['timestamp'].split(':')[1])*60+float(e['timestamp'].split(':')[2])),e) for e in events],
            'cutoff':cutoff,'last':event('Half End',int(cutoff))}


class MatchLabTests(unittest.TestCase):
    def test_coordinates_reject_invalid_and_do_not_guess_fidelity(self):
        for raw in (None,[],[float('nan'),0],[121,20],[1,'bad'],[-1,2]): self.assertIsNone(coordinates(raw))
        self.assertEqual(coordinates([120,80]),(120.,80.))
        self.assertEqual(coordinates([1,1],1),(.5,.5))
        self.assertEqual(coordinates([1,1],2),(.95,.95))
        self.assertEqual(cell((120,80)),L*W-1)

    def test_solver_known_markov_solution_and_failed_moves(self):
        c=empty_counts(2,1); c['shots'][1]=10; c['goals'][1]=2
        c['moves'][0]=10; c['transitions'][0,1]=5
        v,stats=solve(c)
        np.testing.assert_allclose(v,[.1,.2])
        self.assertLess(stats['residual'],stats['epsilon'])

    def test_failed_passes_count_in_denominator_and_set_pieces_excluded(self):
        good=pass_event(1); bad=pass_event(2); bad['pass']['outcome']={'name':'Incomplete'}
        corner=pass_event(3,play_pattern={'name':'From Corner'})
        penalty=event('Shot',4,location=[108,40],shot={'type':{'name':'Penalty'},'outcome':{'name':'Goal'}})
        c=empty_counts(); self.assertEqual(add_events(c,[good,bad,corner,penalty]),2)
        self.assertEqual(c['moves'].sum(),2); self.assertEqual(c['transitions'].sum(),1)
        self.assertEqual(c['shots'].sum(),0)

    def test_xt_rates_only_visible_successful_moves_and_keeps_negative(self):
        a=pass_event(10); b=pass_event(20,start=(70,40),end=(30,40)); future=pass_event(1201)
        bad=pass_event(30); bad['pass']['outcome']={'name':'Incomplete'}
        s=state([a,b,bad,future]); before=copy.deepcopy(s)
        grid=[0.]*(L*W); grid[cell((70,40))]=.2
        rows=rate_actions(s,1,{'values':grid})
        self.assertEqual([r['xt'] for r in rows],[.2,-.2]); self.assertEqual(s,before)
        summary=xt_summary(rows); self.assertEqual(summary[0]['xT сумма'],0)
        self.assertEqual(summary[0]['xT положительный'],.2)

    def test_surface_strictly_precedes_match_date(self):
        data={'surfaces':[{'through_date':'2015-08-20'},{'through_date':'2015-09-01'}]}
        self.assertIsNone(surface_for_date(data,'2015-08-20'))
        self.assertEqual(surface_for_date(data,'2015-09-01')['through_date'],'2015-08-20')

    def test_adjacent_windows_have_no_overlap_or_future(self):
        es=[event('Shot',sec,shot={'statsbomb_xg':.1}) for sec in (0,600,601,1200,1201)]
        result=phase_comparison(state(es),1,10)
        self.assertEqual([v['Удары'] for v in result['values']],[1,2])
        self.assertFalse(phase_comparison(state(es,1199),1,10)['ready'])

    def test_phase_does_not_mix_halves(self):
        s=state([event('Shot',400,period=1),event('Shot',400,period=2)],1200)
        s['last']=event('Half End',1200,period=2)
        result=phase_comparison(s,1,10)
        self.assertEqual([v['Удары'] for v in result['values']],[1,0])

    def test_network_weighted_share_and_filtered_edges(self):
        es=[pass_event(1),pass_event(2),pass_event(3,a=2,b=3),pass_event(1300,a=3,b=4)]
        net=network_analysis(state(es),1,0,2)
        self.assertEqual(net['total'],3); self.assertEqual(len(net['edges']),1)
        self.assertEqual(net['nodes'][0]['id'],2)
        self.assertAlmostEqual(sum(n['Доля участий'] for n in net['nodes']),1)

    def test_progression_excludes_failed_backward_and_future(self):
        bad=pass_event(2); bad['pass']['outcome']={'name':'Incomplete'}
        es=[pass_event(1),bad,pass_event(3,start=(80,40),end=(60,40)),pass_event(1300)]
        self.assertEqual(len(progression(state(es),1)),1)

    def test_motif_requires_known_same_possession_and_success(self):
        recover=event('Ball Recovery',1,player={'id':1,'name':'P1'},possession=2)
        p=pass_event(4,possession=2); shot=event('Shot',8,possession=2)
        self.assertEqual(len(possession_patterns(state([recover,p,shot]),1)),1)
        for change in ('unknown','different','failure','opponent','late'):
            events=copy.deepcopy([recover,p,shot])
            if change=='unknown': events[0].pop('possession')
            if change=='different': events[-1]['possession']=3
            if change=='failure': events[1]['pass']['outcome']={'name':'Incomplete'}
            if change=='opponent': events[1]['team']['id']=2
            if change=='late': events[-1]['timestamp']='00:00:30.000'
            self.assertEqual(possession_patterns(state(events),1),[],change)


if __name__=='__main__': unittest.main()
