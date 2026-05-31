import unittest

from backend.app.providers.nflverse import normalize_stat_row


class NflverseTests(unittest.TestCase):
    def test_normalize_stat_row(self):
        row = normalize_stat_row(
            {
                "player_display_name": "Ja'Marr Chase",
                "position": "WR",
                "recent_team": "CIN",
                "season": "2024",
                "week": "1",
                "fantasy_points_ppr": "25.5",
                "sleeper_id": "111",
            }
        )
        self.assertEqual(row["player_name"], "Ja'Marr Chase")
        self.assertEqual(row["team"], "CIN")
        self.assertEqual(row["fantasy_points"], 25.5)
        self.assertEqual(row["sleeper_id"], "111")


if __name__ == "__main__":
    unittest.main()
