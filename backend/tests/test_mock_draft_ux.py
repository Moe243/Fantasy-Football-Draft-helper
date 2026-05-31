from pathlib import Path
import sqlite3
import unittest

from backend.app import db
from backend.app.models import LeagueSettings
from backend.app.services.draft_ranking_engine import QB_ROUND_PENALTY, score_draft_candidate
from backend.app.services.draft_room import league_draft_recommendations
from backend.app.services.league_import import list_managers_for_setup, update_manager_display_names
from backend.app.services.mock_draft_ai import choose_mock_pick
from backend.app.services.recommendations import database_draft_recommendations
from backend.app.services.sleeper_import import import_sleeper_players
from backend.app.services.keepers import keeper_pick_no


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def seed_players(conn):
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
            "222": {
                "first_name": "Josh",
                "last_name": "Allen",
                "position": "QB",
                "team": "BUF",
                "fantasy_positions": ["QB"],
                "active": True,
                "search_rank": 40,
            },
            "333": {
                "first_name": "Bijan",
                "last_name": "Robinson",
                "position": "RB",
                "team": "ATL",
                "fantasy_positions": ["RB"],
                "active": True,
                "search_rank": 5,
            },
        },
    )
    for pid, rank, pos in (
        ("sleeper_111", 2, "WR"),
        ("sleeper_222", 38, "QB"),
        ("sleeper_333", 5, "RB"),
    ):
        db.upsert_source_ranking(
            conn,
            {
                "internal_player_id": pid,
                "source_name": "fantasypros",
                "overall_rank": rank,
                "adp": rank,
                "projected_points": 250 - rank,
            },
        )


def seed_league(conn, teams: int = 10) -> str:
    league_id = "ux_league"
    conn.execute(
        """
        INSERT INTO sleeper_leagues (league_id, name, season, status, total_rosters)
        VALUES (?, 'UX', '2025', 'pre_draft', ?)
        """,
        (league_id, teams),
    )
    for slot in range(1, teams + 1):
        conn.execute(
            """
            INSERT INTO league_managers (league_id, roster_id, display_name, team_name, is_me)
            VALUES (?, ?, ?, ?, ?)
            """,
            (league_id, slot, f"Manager {slot}", f"Team {slot}", 1 if slot == 6 else 0),
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


class MockDraftUxTests(unittest.TestCase):
    def test_pick_sheet_limit_and_position_filter(self):
        conn = memory_db()
        seed_players(conn)
        league_id = seed_league(conn)
        payload = league_draft_recommendations(
            conn, league_id, pick_no=14, limit=30, position="RB"
        )
        self.assertEqual(len(payload["recommendations"]), 1)
        self.assertEqual(payload["recommendations"][0]["player"]["position"], "RB")
        all_payload = league_draft_recommendations(conn, league_id, pick_no=14, limit=30, position="ALL")
        self.assertGreaterEqual(len(all_payload["recommendations"]), 2)

    def test_recommendation_profile_fields(self):
        conn = memory_db()
        seed_players(conn)
        league_id = seed_league(conn)
        conn.execute(
            """
            INSERT INTO player_stat_lines (
                internal_player_id, source_name, season, week, stat_type, fantasy_points, raw_json
            ) VALUES (?, 'espn', 2025, 0, 'season', 245.2, '{"rank": 12}')
            """,
            ("sleeper_111",),
        )
        conn.execute(
            """
            INSERT INTO player_stat_lines (
                internal_player_id, source_name, season, week, stat_type, fantasy_points, raw_json
            ) VALUES (?, 'espn', 2024, 0, 'season', 220.1, '{"rank": 18}')
            """,
            ("sleeper_111",),
        )
        conn.execute(
            """
            INSERT INTO player_props (
                internal_player_id, source_name, sportsbook, market, line, season
            ) VALUES (?, 'odds', 'DraftKings', 'receiving_yards', 82.5, 2026)
            """,
            ("sleeper_111",),
        )
        conn.commit()
        rec = league_draft_recommendations(conn, league_id, pick_no=14, limit=5)["recommendations"][0]
        self.assertEqual(rec["history"]["2025"]["fantasy_points"], 245.2)
        self.assertEqual(rec["history"]["2024"]["rank"], 18)
        self.assertTrue(rec["props_2026"])
        self.assertTrue(rec["outlook"])

    def test_qb_penalty_before_round_three(self):
        conn = memory_db()
        seed_players(conn)
        settings = db.get_league_settings(conn)
        rows = database_draft_recommendations(
            conn,
            settings,
            [],
            [],
            limit=30,
            current_pick_override=10,
            league_id=None,
        )
        qb = next(item for item in rows if item["player"]["position"] == "QB")
        self.assertLessEqual(qb["signals"]["qb_round_penalty"], -QB_ROUND_PENALTY + 1)
        self.assertTrue(any("Round 3" in reason for reason in qb["reasons"]))

    def test_mock_ai_skips_qb_early(self):
        conn = memory_db()
        seed_players(conn)
        league_id = seed_league(conn, teams=2)
        conn.execute(
            """
            INSERT INTO practice_drafts (league_id, name, current_pick, status)
            VALUES (?, 'Mock', 1, 'active')
            """,
            (league_id,),
        )
        practice_id = conn.execute("SELECT id FROM practice_drafts").fetchone()["id"]
        pick_id = choose_mock_pick(conn, league_id, practice_id, 1, 2, "Beta")
        row = db.get_player_row(conn, pick_id)
        self.assertNotEqual(row["position"], "QB")

    def test_manager_name_update_keeps_draft_slot(self):
        conn = memory_db()
        league_id = seed_league(conn)
        before = list_managers_for_setup(conn, league_id)
        slot_before = before[5]["draft_slot"]
        update_manager_display_names(
            conn,
            league_id,
            6,
            local_display_name="Yahia",
            local_team_name="Yahia21 FC",
        )
        after = list_managers_for_setup(conn, league_id)
        row = next(item for item in after if int(item["roster_id"]) == 6)
        self.assertEqual(row["draft_slot"], slot_before)
        self.assertEqual(row["local_team_name"], "Yahia21 FC")

    def test_round_15_keeper_pick_150(self):
        self.assertEqual(keeper_pick_no(15, 10, 10), 150)

    def test_setup_hides_json_from_normal_markup(self):
        html = Path("/workspace/frontend/index.html").read_text(encoding="utf-8")
        self.assertIn('id="advanced-import"', html)
        before_advanced = html.split("Advanced Import", 1)[0]
        self.assertNotIn("<h3>Rankings JSON</h3>", before_advanced)


if __name__ == "__main__":
    unittest.main()
