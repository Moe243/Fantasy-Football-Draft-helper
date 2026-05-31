import tempfile
import unittest
from pathlib import Path

from backend.app import db
from backend.app.models import Keeper, LeagueSettings
from backend.app.services.recommendations import recommendation_api_rows


class DraftModeKeeperTests(unittest.TestCase):
    def test_keeper_upsert_persists_across_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "keepers.db"
            conn = db.connect(db_path)
            db.init_db(conn)
            db.upsert_keeper(
                conn,
                Keeper(player_id="p_test", team_name="Team Mahomes", round=3, pick_no=7),
            )
            conn.close()

            conn2 = db.connect(db_path)
            keepers = db.get_keepers(conn2)
            conn2.close()
            self.assertEqual(len(keepers), 1)
            self.assertEqual(keepers[0].player_id, "p_test")
            self.assertEqual(keepers[0].team_name, "Team Mahomes")
            self.assertEqual(keepers[0].round, 3)
            self.assertEqual(keepers[0].pick_no, 7)

    def test_recommendation_api_rows_returns_expected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "recs.db"
            conn = db.connect(db_path)
            db.init_db(conn)
            rows = recommendation_api_rows(
                conn=conn,
                settings=LeagueSettings(),
                keepers=[],
                picks=[],
                position="ALL",
                limit=5,
                current_pick=1,
            )
            conn.close()
        self.assertIsInstance(rows, list)
        if rows:
            sample = rows[0]
            for key in (
                "player_id",
                "player_name",
                "team",
                "position",
                "consensus_rank",
                "adp",
                "label",
                "source_count",
                "projected_points",
            ):
                self.assertIn(key, sample)


if __name__ == "__main__":
    unittest.main()
