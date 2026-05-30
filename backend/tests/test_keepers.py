import sqlite3
import unittest

from backend.app import db
from backend.app.models import LeagueSettings
from backend.app.services.draft_board import get_draft_board, snake_pick_no
from backend.app.services.keepers import add_keeper, keeper_pick_no, remove_keeper
from backend.app.services.recommendations import database_draft_recommendations
from backend.app.services.sleeper_import import import_sleeper_players


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def seed_league(conn, teams: int = 10) -> str:
    league_id = "keeper_league"
    conn.execute(
        """
        INSERT INTO sleeper_leagues (league_id, name, season, status, total_rosters)
        VALUES (?, 'Test', '2025', 'pre_draft', ?)
        """,
        (league_id, teams),
    )
    for slot in range(1, teams + 1):
        conn.execute(
            """
            INSERT INTO league_managers (league_id, roster_id, display_name, team_name, is_me)
            VALUES (?, ?, ?, ?, ?)
            """,
            (league_id, slot, f"Manager {slot}", f"Team {slot}", 1 if slot == 10 else 0),
        )
        conn.execute(
            """
            INSERT INTO draft_slots (league_id, roster_id, manager_name, draft_slot)
            VALUES (?, ?, ?, ?)
            """,
            (league_id, slot, f"Team {slot}", slot),
        )
    conn.commit()
    return league_id


class KeeperPickTests(unittest.TestCase):
    def test_round_15_pick_numbers_for_slots(self):
        teams = 10
        self.assertEqual(keeper_pick_no(15, 1, teams), 141)
        self.assertEqual(keeper_pick_no(15, 6, teams), 146)
        self.assertEqual(keeper_pick_no(15, 10, teams), 150)
        self.assertEqual(snake_pick_no(15, 10, teams), 150)

    def test_keeper_on_board_and_removed_from_best_available(self):
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
                },
            },
        )
        db.upsert_source_ranking(
            conn,
            {
                "internal_player_id": "sleeper_111",
                "source_name": "fantasypros",
                "overall_rank": 2,
                "adp": 2,
                "projected_points": 300,
            },
        )
        league_id = seed_league(conn)
        result = add_keeper(conn, league_id, "sleeper_111", roster_id=10)
        self.assertEqual(result["keeper"]["pick_no"], 150)

        board = get_draft_board(conn, league_id)
        round_15 = next(row for row in board["board"] if row["round"] == 15)
        pick_150 = next(cell for cell in round_15["picks"] if int(cell["pick_no"]) == 150)
        self.assertTrue(pick_150["is_keeper"])
        self.assertEqual(pick_150["player"]["internal_player_id"], "sleeper_111")
        self.assertFalse(pick_150["is_traded"])

        recs = database_draft_recommendations(
            conn,
            LeagueSettings(),
            db.get_keepers(conn, league_id),
            [],
            limit=20,
            league_id=league_id,
        )
        ids = {item["player"]["internal_player_id"] for item in recs}
        self.assertNotIn("sleeper_111", ids)

        remove_keeper(conn, league_id, "sleeper_111", roster_id=10)
        board_after = get_draft_board(conn, league_id)
        round_15_after = next(row for row in board_after["board"] if row["round"] == 15)
        pick_150_after = next(cell for cell in round_15_after["picks"] if int(cell["pick_no"]) == 150)
        self.assertFalse(pick_150_after.get("is_keeper"))
        self.assertIsNone(pick_150_after.get("player"))

    def test_round_15_ignores_traded_pick_ownership(self):
        conn = memory_db()
        import_sleeper_players(
            conn,
            {
                "222": {
                    "first_name": "Bijan",
                    "last_name": "Robinson",
                    "position": "RB",
                    "team": "ATL",
                    "fantasy_positions": ["RB"],
                    "active": True,
                    "search_rank": 4,
                },
            },
        )
        league_id = seed_league(conn, teams=10)
        pick_146 = keeper_pick_no(15, 6, 10)
        conn.execute(
            """
            INSERT INTO user_draft_picks (
                league_id, round, pick_no, draft_slot, original_roster_id, current_roster_id,
                manager_name, is_mine, source
            )
            VALUES (?, 15, ?, 6, 6, 9, 'Traded away', 0, 'traded_pick')
            """,
            (league_id, pick_146),
        )
        conn.commit()
        add_keeper(conn, league_id, "sleeper_222", roster_id=6)
        board = get_draft_board(conn, league_id)
        round_15 = next(row for row in board["board"] if row["round"] == 15)
        cell = next(c for c in round_15["picks"] if int(c["pick_no"]) == pick_146)
        self.assertEqual(cell["roster_id"], 6)
        self.assertFalse(cell["is_traded"])
        self.assertTrue(cell["is_keeper"])


if __name__ == "__main__":
    unittest.main()
