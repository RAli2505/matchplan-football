import unittest
from goal_pitch import vertical_goal_view,position


def record(x,y,xg=.2,goal=False,own=False):
    return {'location':[x,y],'xg':xg,'goal':goal,'own_goal':own,'player':'Test <name>','minute':25}


class VerticalGoalTests(unittest.TestCase):
    def test_orientation_preserves_our_right_flank(self):
        self.assertLess(position((119,40))[1],position((65,40))[1])
        self.assertGreater(position((119,40),True)[1],position((65,40),True)[1])
        self.assertGreater(position((100,70))[0],position((100,10))[0])
        self.assertGreater(position((100,10),True)[0],position((100,70),True)[0])

    def test_boundaries_do_not_duplicate_and_xg_is_conserved(self):
        rs=[record(x,y) for x in (60,84,102,114,120) for y in (0,18,30,50,62,80)]
        rs+=[record(40,40),dict(record(100,40),location=None),record(100,40,0,own=True)]
        for conceded in (False,True):
            svg,rows=vertical_goal_view(rs,conceded)
            self.assertEqual(sum(r['Удары'] for r in rows),32)
            self.assertAlmostEqual(sum(r['xG'] for r in rows),6.4)
            self.assertEqual(len(rows),22)
            self.assertIn('вертикальная карта',svg)

    def test_shot_mode_has_hollow_misses_and_escaped_names(self):
        svg,_=vertical_goal_view([record(100,40),record(110,40,goal=True)],mode='shots')
        self.assertIn('Test &lt;name&gt;',svg)
        self.assertIn('fill="#fcfcfb"',svg)
        self.assertIn('fill="#2876ca"',svg)

    def test_empty_map_is_valid_and_own_goal_never_adds_xg(self):
        svg,rows=vertical_goal_view([record(4,40,0,own=True)],True,mode='shots')
        self.assertEqual(sum(r['xG'] for r in rows),0)
        self.assertIn('автогол',svg)
        self.assertIn('Наши ворота',svg)


if __name__=='__main__': unittest.main()
