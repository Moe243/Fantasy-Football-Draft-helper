import sqlite3
import unittest

from backend.app import db
from backend.app.services.player_rankings import (
    build_consensus_payload,
    consensus_label,
    get_player_rankings,
)
from backend.app.services.sleeper_import import import_sleeper_players


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


class PlayerRankingsApiTests(unittest.TestCase):
    def test_empty_rankings_message(self):
        conn = memory_db()
        import_sleeper_players(
            conn,
            {
                "111": {
                    "first_name": "Ja'Marr",
                    "last_name": "Chase",
                    "position": "WR",
                    "team": "CIN",
                    "fantasy_positions": ["WR"],
                    "active": True,
                    "search_rank": 2,
                }
            },
        )
        conn.execute("DELETE FROM player_source_rankings WHERE internal_player_id = 'sleeper_111'")
        conn.commit()
        payload = get_player_rankings(conn, "sleeper_111")
        self.assertEqual(payload["message"], "No rankings imported yet")
        self.assertEqual(payload["sources"], [])

    def test_sleeper_rankings_shape(self):
        conn = memory_db()
        import_sleeper_players(
            conn,
            {
                "111": {
                    "first_name": "Ja'Marr",
                    "last_name": "Chase",
                    "position": "WR",
                    "team": "CIN",
                    "fantasy_positions": ["WR"],
                    "active": True,
                    "search_rank": 12,
                }
            },
        )
        payload = get_player_rankings(conn, "sleeper_111", current_pick=20)
        self.assertEqual(payload["sources"][0]["source_name"], "sleeper")
        self.assertEqual(payload["sources"][0]["overall_rank"], 12)
        self.assertEqual(payload["consensus"]["label"], "Not Enough Sources")

    def test_consensus_label_logic(self):
        self.assertEqual(consensus_label(1, 0, 10.0, 20), "Not Enough Sources")
        self.assertEqual(consensus_label(2, 5, 10.0, 20), "Split Opinions")
        self.assertEqual(consensus_label(2, 2, 10.0, 20), "Strong Value")
        self.assertEqual(consensus_label(2, 2, 25.0, 20), "Fair Value")

    def test_build_consensus_averages(self):
        consensus = build_consensus_payload(
            [
                {"source_name": "sleeper", "overall_rank": 10, "adp": 12.0},
                {"source_name": "espn", "overall_rank": 14, "adp": None},
            ],
            current_pick=20,
        )
        self.assertEqual(consensus["source_count"], 2)
        self.assertEqual(consensus["avg_rank"], 12.0)
        self.assertEqual(consensus["avg_adp"], 12.0)
        self.assertEqual(consensus["rank_spread"], 4.0)


if __name__ == "__main__":
    unittest.main()
