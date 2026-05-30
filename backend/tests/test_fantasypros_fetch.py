import unittest

from backend.app.providers.fantasypros import (
    entry_to_row,
    parse_ranking_entries,
)


SAMPLE_HTML = """
<html><body>
<script>
var data = [{"player_id":22968,"player_name":"Jahmyr Gibbs","player_team_id":"DET",
"player_position_id":"RB","pos_rank":"RB1","player_bye_week":"6","rank_ecr":1,"tier":1},
{"player_id":23133,"player_name":"Bijan Robinson","player_team_id":"ATL",
"player_position_id":"RB","pos_rank":"RB2","player_bye_week":"11","rank_ecr":2,"tier":1}];
</script>
</body></html>
"""


class FantasyProsFetchTests(unittest.TestCase):
    def test_parse_ranking_entries_from_embedded_json(self):
        entries = parse_ranking_entries(SAMPLE_HTML)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["player_name"], "Jahmyr Gibbs")

    def test_entry_to_row_overall_uses_rank_ecr_as_overall_rank(self):
        row = entry_to_row(
            {
                "player_id": 22968,
                "player_name": "Jahmyr Gibbs",
                "player_team_id": "DET",
                "player_position_id": "RB",
                "pos_rank": "RB1",
                "rank_ecr": 3,
                "tier": 1,
                "player_bye_week": "6",
            },
            "overall",
        )
        self.assertEqual(row["overall_rank"], 3)
        self.assertEqual(row["position_rank"], "RB1")

    def test_entry_to_row_position_page_keeps_pos_rank(self):
        row = entry_to_row(
            {
                "player_id": 22968,
                "player_name": "Jahmyr Gibbs",
                "player_team_id": "DET",
                "player_position_id": "RB",
                "pos_rank": "RB1",
                "rank_ecr": 1,
            },
            "rb",
        )
        self.assertNotIn("overall_rank", row)
        self.assertEqual(row["position_rank"], "RB1")


if __name__ == "__main__":
    unittest.main()
