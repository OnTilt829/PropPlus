import unittest
from scripts.update_injury_reports import parse_report

class InjuryReportTests(unittest.TestCase):
    def test_league_group_parser(self):
        payload={"timestamp":"2026-10-27T12:00Z","injuries":[{"team":{"id":"9","displayName":"Example Team"},"injuries":[{"athlete":{"id":"42","displayName":"Example Player"},"status":"Questionable","type":{"description":"Ankle"}}]}]}
        rows=parse_report("nba",payload,"https://example.org")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["PLAYER_ID"],"42")
        self.assertEqual(rows[0]["TEAM_ID"],"9")
        self.assertEqual(rows[0]["STATUS"],"Questionable")
    def test_espn_top_level_team_group(self):
        payload={"injuries":[{"id":"24","displayName":"Sample Team","injuries":[{"athlete":{"id":"812","displayName":"Sample Player"},"status":"Out"}]}]}
        rows=parse_report("nfl",payload,"source")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["TEAM_ID"],"24")
        self.assertEqual(rows[0]["TEAM"],"Sample Team")
    def test_empty_valid_report(self):
        self.assertEqual(parse_report("nfl",{"injuries":[]},"source"),[])
    def test_malformed_report_is_not_healthy(self):
        with self.assertRaises(ValueError):parse_report("cfb",{},"source")
if __name__=="__main__":unittest.main()
