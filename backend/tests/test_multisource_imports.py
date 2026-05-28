import sqlite3
import unittest

from backend.app import db
from backend.app.models import LeagueSettings
from backend.app.providers.rankings_csv import import_ranking_rows
from backend.app.services.consensus import get_consensus_rows
from backend.app.services.normalization import match_player, normalize_name, normalize_position, normalize_team
from backend.app.services.recommendations import database_draft_recommendations
from backend.app.services.sleeper_import import import_sleeper_players


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


class MultisourceImportTests(unittest.TestCase):
    def test_normalization_handles_names_positions_and_defenses(self):
        self.assertEqual(normalize_name("Ja’Marr Chase Jr."), "ja marr chase")
        self.assertEqual(normalize_position("D/ST"), "DEF")
        self.assertEqual(normalize_team("Pittsburgh Steelers"), "PIT")

    def test_sleeper_player_import_filters_and_stores_players(self):
        conn = memory_db()
        result = import_sleeper_players(
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
                    "espn_id": "4362628",
                },
                "222": {
                    "first_name": "Example",
                    "last_name": "Lineman",
                    "position": "OL",
                    "active": True,
                },
            },
        )
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        players, source = db.get_players_for_api(conn)
        self.assertEqual(source, "database")
        self.assertEqual(players[0]["full_name"], "Ja'Marr Chase")

    def test_ranking_import_matches_player_and_creates_consensus(self):
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
        import_ranking_rows(
            conn,
            "fantasypros",
            [
                {
                    "player_name": "Ja'Marr Chase",
                    "team": "CIN",
                    "position": "WR",
                    "overall_rank": 2,
                    "adp": 2.6,
                    "projected_points": 304.8,
                }
            ],
        )
        import_ranking_rows(
            conn,
            "espn",
            [
                {
                    "player_name": "Ja'Marr Chase",
                    "team": "CIN",
                    "position": "WR",
                    "overall_rank": 35,
                    "projected_points": 295,
                }
            ],
        )
        matched = match_player(conn, "Ja'Marr Chase", position="WR", team="CIN")
        self.assertIsNotNone(matched)
        rows = get_consensus_rows(conn, position="WR", current_pick=25)
        self.assertEqual(rows[0]["consensus"]["source_count"], 3)
        self.assertEqual(rows[0]["consensus"]["label"], "High Disagreement")
        self.assertEqual(rows[0]["consensus"]["fantasypros_rank"], 2.0)
        self.assertEqual(rows[0]["consensus"]["espn_rank"], 35.0)

    def test_database_recommendations_explain_value_and_disagreement(self):
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
        import_ranking_rows(
            conn,
            "fantasypros",
            [{"player_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "overall_rank": 2}],
        )
        import_ranking_rows(
            conn,
            "espn",
            [{"player_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "overall_rank": 35}],
        )
        recs = database_draft_recommendations(conn, LeagueSettings(), keepers=[], picks=[], limit=1)
        self.assertEqual(recs[0]["player"]["full_name"], "Ja'Marr Chase")
        self.assertTrue(any("higher on him" in reason for reason in recs[0]["reasons"]))


if __name__ == "__main__":
    unittest.main()
