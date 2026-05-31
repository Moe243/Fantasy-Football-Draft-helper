import sqlite3
import unittest

from backend.app import db
from backend.app.providers.nfl_data import NFLStatsProvider
from backend.app.services.data_imports import import_nfl_public_stat_rows
from backend.app.services.normalization import normalize_name


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


class NFLStatsImportTests(unittest.TestCase):
    def test_provider_normalizes_nflfastr_fields(self):
        provider = NFLStatsProvider(source_url="http://example.com/stats.json", season=2025)
        row = provider.normalize_row(
            {
                "player_display_name": "J.K. Dobbins",
                "recent_team": "DEN",
                "position_group": "RB",
                "fantasy_points_ppr": 16.6,
                "week": 1,
                "stat_type": "actual",
            }
        )
        self.assertEqual(row["player_name"], "J.K. Dobbins")
        self.assertEqual(row["team"], "DEN")
        self.assertEqual(row["position"], "RB")
        self.assertEqual(row["fantasy_points"], 16.6)
        self.assertEqual(row["stat_type"], "actual")

    def test_import_matches_dobbins(self):
        conn = memory_db()
        player_id = "sleeper_dobbins"
        conn.execute(
            """
            INSERT INTO players (
                internal_player_id, full_name, normalized_name, position, team, active, source
            ) VALUES (?, ?, ?, ?, ?, 1, 'sleeper')
            """,
            (player_id, "J.K. Dobbins", normalize_name("J.K. Dobbins"), "RB", "DEN"),
        )
        conn.commit()

        result = import_nfl_public_stat_rows(
            conn,
            "nflfastR",
            [
                {
                    "player_name": "J.K. Dobbins",
                    "team": "DEN",
                    "position": "RB",
                    "season": 2025,
                    "week": 1,
                    "stat_type": "actual",
                    "fantasy_points": 16.6,
                }
            ],
            default_season=2025,
        )
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        rows = conn.execute(
            "SELECT stat_type, fantasy_points FROM player_stat_lines WHERE internal_player_id = ?",
            (player_id,),
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stat_type"], "actual")

    def test_failed_rows_for_unmatched_player(self):
        conn = memory_db()
        result = import_nfl_public_stat_rows(
            conn,
            "nflfastR",
            [{"player_name": "Unknown Player", "team": "NYG", "position": "RB", "season": 2025, "week": 1}],
            default_season=2025,
        )
        self.assertEqual(result["imported_count"], 0)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["failed_rows"][0]["player_name"], "Unknown Player")
        self.assertIn("No matching player", result["failed_rows"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
