import unittest
from scripts.availability_impact import adjustment,load_logs

class AvailabilityImpactTests(unittest.TestCase):
    def setUp(self):
        self.logs={("nba","1","99"):[
            *[{"PLAYED":True,"TEAM_POINTS":110.0} for _ in range(4)],
            *[{"PLAYED":False,"TEAM_POINTS":100.0} for _ in range(4)]
        ]}
        self.out=[{"player":"Example","player_id":"99","status":"Out"}]
    def test_confirmed_absence_adjusts_relative_to_baseline(self):
        value,evidence=adjustment("nba","1",self.out,self.logs)
        self.assertEqual(value,-5)
        self.assertTrue(evidence["applied"])
    def test_questionable_does_not_adjust(self):
        self.assertEqual(adjustment("nba","1",[dict(self.out[0],status="Questionable")],self.logs)[0],0)
    def test_missing_player_id_does_not_adjust(self):
        self.assertEqual(adjustment("nba","1",[dict(self.out[0],player_id="")],self.logs)[0],0)
    def test_insufficient_games_does_not_adjust(self):
        short={("nba","1","99"):self.logs[("nba","1","99")][:5]}
        self.assertEqual(adjustment("nba","1",self.out,short)[0],0)
    def test_no_file_is_safe(self):
        self.assertFalse(load_logs("/not/a/file.csv"))

if __name__=="__main__":unittest.main()
