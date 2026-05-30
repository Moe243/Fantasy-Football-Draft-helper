import sqlite3
import unittest
from unittest.mock import patch

from backend.app import db
from backend.app.providers.odds import OddsClient
from backend.app.providers.sleeper_projections import SleeperProjectionsClient
from backend.app.services.draft_ranking_engine import score_draft_candidate
from backend.app.services.practice_draft import simulate_next, simulate_to_my_next_pick, start_practice
from backend.app.services.recommendations import database_draft_recommendations
from backend.app.services.sleeper_import import import_sleeper_players
from backend.app.services.user_preferences import add_favorite


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def seed_players(conn):
    return import_sleeper_players(
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


def seed_league(conn, league_id: str = "league_test") -> None:
    conn.execute(
        """
        INSERT INTO sleeper_leagues (league_id, name, season, status, total_rosters)
        VALUES (?, 'Test', '2025', 'pre_draft', 2)
        """,
        (league_id,),
    )
    for roster_id, name, is_me in ((1, "Alpha", 1), (2, "Beta", 0)):
        conn.execute(
            """
            INSERT INTO league_managers (league_id, roster_id, display_name, team_name, is_me)
            VALUES (?, ?, ?, ?, ?)
            """,
            (league_id, roster_id, name, name, is_me),
        )
    for pick_no, roster_id in ((1, 1), (2, 2), (3, 2), (4, 1)):
        conn.execute(
            """
            INSERT INTO user_draft_picks (
                league_id, round, pick_no, draft_slot, current_roster_id, manager_name, is_mine
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                league_id,
                ((pick_no - 1) // 2) + 1,
                pick_no,
                roster_id,
                roster_id,
                "Alpha" if roster_id == 1 else "Beta",
                1 if roster_id == 1 else 0,
            ),
        )
    conn.commit()


class MockDraftRankingTests(unittest.TestCase):
    def test_favorite_player_boosts_ranking(self):
        conn = memory_db()
        seed_players(conn)
        settings = db.get_league_settings(conn)
        add_favorite(conn, "local", "sleeper_111")
        recs = database_draft_recommendations(
            conn,
            settings,
            [],
            [],
            limit=5,
            league_id="local",
        )
        top = recs[0]["player"]["internal_player_id"]
        self.assertEqual(top, "sleeper_111")

    def test_mock_draft_simulate_guard_on_my_pick(self):
        conn = memory_db()
        seed_players(conn)
        seed_league(conn)
        start_practice(conn, "league_test", name="Mock")
        simulate_to_my_next_pick(conn, "league_test")
        with self.assertRaises(ValueError) as ctx:
            simulate_next(conn, "league_test")
        self.assertIn("on the clock", str(ctx.exception).lower())

    def test_sleeper_projections_client_parses_dict_payload(self):
        client = SleeperProjectionsClient()
        with patch("backend.app.providers.sleeper_projections.get_json") as mock_get:
            mock_get.return_value = {
                "111": {"stats": {"pts_ppr": 18.5}},
                "222": {"stats": {"pts_ppr": 14.2}},
            }
            rows = client.fetch_week(2025, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["player_id"], "111")

    def test_odds_client_requires_api_key(self):
        client = OddsClient(api_key="")
        with self.assertRaises(Exception):
            client.fetch_nfl_events()


if __name__ == "__main__":
    unittest.main()
