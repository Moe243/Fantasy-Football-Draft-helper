import sqlite3
import unittest

from backend.app import db
from backend.app.providers.rankings_csv import import_ranking_rows
from backend.app.services.consensus import get_consensus_rows
from backend.app.services.data_imports import import_nflverse_stat_rows
from backend.app.services.player_detail import player_detail
from backend.app.services.recommendations import database_draft_recommendations
from backend.app.services.sleeper_import import import_sleeper_players
from backend.app.models import LeagueSettings


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


CHASE = {
    "111": {
        "first_name": "Ja'Marr",
        "last_name": "Chase",
        "position": "WR",
        "team": "CIN",
        "fantasy_positions": ["WR"],
        "active": True,
        "search_rank": 2,
    }
}


class SourceComparisonTests(unittest.TestCase):
    def seed_rankings(self, conn):
        import_sleeper_players(conn, CHASE)
        import_ranking_rows(
            conn,
            "fantasypros",
            [{"player_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "overall_rank": 2, "adp": 2.6}],
        )
        import_ranking_rows(
            conn,
            "espn",
            [{"player_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "overall_rank": 35}],
        )

    def test_consensus_labels(self):
        conn = memory_db()
        self.seed_rankings(conn)
        rows = get_consensus_rows(conn, position="WR", current_pick=25)
        self.assertEqual(rows[0]["consensus"]["label"], "Risky / Split Opinions")
        self.assertEqual(rows[0]["consensus"]["source_count"], 3)

    def test_player_detail_source_comparison(self):
        conn = memory_db()
        self.seed_rankings(conn)
        import_nflverse_stat_rows(
            conn,
            [
                {
                    "player_name": "Ja'Marr Chase",
                    "team": "CIN",
                    "position": "WR",
                    "season": 2024,
                    "week": 1,
                    "fantasy_points": 25.0,
                }
            ],
        )
        detail = player_detail(conn, "sleeper_111")
        comparison = detail["source_comparison"]
        self.assertEqual(comparison["espn_rank"], 35.0)
        self.assertEqual(comparison["fantasypros_rank"], 2.0)
        self.assertEqual(comparison["nflverse_fantasy_points"], 25.0)
        self.assertGreaterEqual(comparison["source_count"], 2)

    def test_draft_recommendations_include_source_comparison(self):
        conn = memory_db()
        self.seed_rankings(conn)
        recs = database_draft_recommendations(conn, LeagueSettings(), keepers=[], picks=[], limit=1)
        self.assertIn("source_comparison", recs[0])
        self.assertEqual(recs[0]["source_comparison"]["value_label"], "Risky / Split Opinions")

    def test_ranking_import_failed_rows(self):
        conn = memory_db()
        result = import_ranking_rows(conn, "espn", [{"position": "WR"}])
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(len(result["failed_rows"]), 1)


if __name__ == "__main__":
    unittest.main()
