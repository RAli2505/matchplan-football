import unittest
from test_core import fixture,event
from core import snapshot
from player_insights import player_card,player_map


class PlayerInsightsTests(unittest.TestCase):
    def test_card_uses_only_this_player_and_visible_linked_shots(self):
        es,ls=fixture()
        es += [event('Pass',100,player={'id':109,'name':'A'},under_pressure=True,location=[20,40],
                     **{'pass':{'end_location':[50,40],'assisted_shot_id':'shot'}}),
               event('Shot',110,id='shot',player={'id':110,'name':'B'},shot={'statsbomb_xg':.3}),
               event('Shot',200,player={'id':109,'name':'A'},shot={'statsbomb_xg':.9})]
        early=player_card(snapshot(es,ls,105),1,109)
        later=player_card(snapshot(es,ls,150),1,109)
        self.assertEqual(early['counts'].get('shot_assists',0),0)
        self.assertEqual(later['counts']['shot_assists'],1)
        self.assertEqual(later['counts']['pressured_complete'],1)
        self.assertEqual(later['counts']['forward_passes'],1)
        self.assertEqual(later['counts'].get('xg',0),0)
        self.assertIn('<svg',player_map(later))

    def test_empty_bench_player_is_not_assigned_invented_performance(self):
        es,ls=fixture(); card=player_card(snapshot(es,ls,0),1,112)
        self.assertEqual(card['counts'],{})
        self.assertFalse(card['on_pitch'])
        self.assertIsNone(card['minutes'])


if __name__=='__main__':unittest.main()
