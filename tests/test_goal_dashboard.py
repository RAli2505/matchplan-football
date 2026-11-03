import unittest
from goal_dashboard import records_from_events, select_records, zone_map, goalmouth, match_goal_map
import xml.etree.ElementTree as ET


class GoalDashboardTests(unittest.TestCase):
    def test_xg_zones_include_unsuccessful_shots_and_have_white_field(self):
        events=[{'type':{'name':'Shot'},'team':{'id':1},'location':[110,40],
                 'shot':{'outcome':{'name':outcome},'statsbomb_xg':xg}}
                for outcome,xg in [('Goal',.1),('Saved',.25)]]
        records=records_from_events(events)
        svg,zones=zone_map(records)
        row=next(r for r in zones if r['Зона']=='Штрафная · Центр')
        self.assertEqual(row['xG'],.35)
        self.assertEqual(row['Голы'],1)
        self.assertEqual(row['Удары'],2)
        self.assertIn('>0.35</text>',svg)
        self.assertIn('fill="#ffffff"',svg)
        mirrored,other=zone_map(records,True,mirror=True)
        self.assertEqual(zones,other)
        self.assertIn('Наши ворота слева',mirrored)
        ET.fromstring(mirrored)

    def test_current_match_uses_opposite_goals_in_same_coordinate_frame(self):
        es=[{'type':{'name':'Shot'},'team':{'id':tid},'player':{'name':'Player '+str(tid)},
             'location':[110,40],'minute':10,'second':5,'period':2,
             'shot':{'outcome':{'name':'Goal'},'statsbomb_xg':.3}} for tid in (1,2)]
        records=records_from_events(es)
        own,rows,missing=match_goal_map(select_records(records,1),1)
        against,_,_=match_goal_map(select_records(records,1,True),1,True)
        ns={'svg':'http://www.w3.org/2000/svg'}
        # The radius-13 marker is a goal; the field's centre circle is a separate element.
        own_marker=next(c for c in ET.fromstring(own).findall('svg:circle',ns) if c.get('r')=='13')
        other_marker=next(c for c in ET.fromstring(against).findall('svg:circle',ns) if c.get('r')=='13')
        self.assertGreater(float(own_marker.get('cx')),300)
        self.assertLess(float(other_marker.get('cx')),300)
        self.assertEqual(rows[0]['Время'],'10:05')
        self.assertEqual(rows[0]['Игрок'],'Player 1')
        self.assertEqual(missing,0)

    def test_autogoal_without_location_is_counted_without_fake_marker(self):
        records=records_from_events([{'type':{'name':'Own Goal Against'},'team':{'id':2},'minute':20}])
        svg,rows,missing=match_goal_map(select_records(records,1),1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['Событие'],'Автогол')
        self.assertEqual(missing,1)
        self.assertNotIn('Голов пока нет',svg)

    def test_team_direction_and_own_goals(self):
        events=[{'type':{'name':'Shot'},'team':{'id':tid},'location':[110,40],
                 'shot':{'outcome':{'name':'Goal'},'statsbomb_xg':.3,'end_location':[120,40,1]}}
                for tid in (1,2)]
        events += [{'type':{'name':'Own Goal Against'},'team':{'id':1}}]
        records=records_from_events(events)
        scored=select_records(records,1)
        conceded=select_records(records,1,True)
        self.assertEqual(len(scored),1)
        self.assertEqual(len(conceded),2)
        self.assertEqual(sum(r['own_goal'] for r in conceded),1)
        svg,zones=zone_map(conceded,True)
        self.assertEqual(sum(z['Голы'] for z in zones),1)
        self.assertEqual(goalmouth(conceded)[1],1)
        self.assertIn('<svg',svg)

    def test_zones_do_not_double_count_boundaries_and_filters(self):
        es=[{'type':{'name':'Shot'},'team':{'id':1},'location':[x,40],
             'shot':{'outcome':{'name':'Goal'},'statsbomb_xg':.1,'type':{'name':'Open Play'}}}
            for x in (30,60,102,114,120)]
        records=records_from_events(es)
        _,zones=zone_map(records)
        self.assertEqual(sum(z['Голы'] for z in zones),5)
        self.assertEqual(len(select_records(records,1,play='Открытая игра')),5)
        self.assertEqual(select_records(records,1,play='Стандарты и пенальти'),[])
        self.assertEqual(goalmouth(records)[1],0)


if __name__=='__main__': unittest.main()
