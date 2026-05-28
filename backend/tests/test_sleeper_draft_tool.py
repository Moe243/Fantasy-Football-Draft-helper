import sqlite3
import unittest

from backend.app import db
from backend.app.providers.draftkings import DraftKingsClient
from backend.app.providers.http import ProviderError
from backend.app.providers.rankings_csv import import_ranking_rows
from backend.app.services import startup
from backend.app.services.availability import estimate_availability
from backend.app.services.data_imports import import_prop_rows, import_stat_rows
from backend.app.services.draft_board import get_draft_board
from backend.app.services.league_import import import_sleeper_league, set_my_team
from backend.app.services.player_detail import player_detail, search_players
from backend.app.services.practice_draft import simulate_next, start_practice
from backend.app.services.props_analysis import analyze_props
from backend.app.services.sleeper_import import import_sleeper_players


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
                "number": "1",
                "age": 26,
                "years_exp": 5,
                "height": "72",
                "weight": "201",
                "college": "LSU",
            },
            "222": {
                "first_name": "Bijan",
                "last_name": "Robinson",
                "position": "RB",
                "team": "ATL",
                "fantasy_positions": ["RB"],
                "active": True,
                "search_rank": 4,
                "number": "7",
                "age": 24,
            },
            "333": {
                "first_name": "Amon-Ra",
                "last_name": "St. Brown",
                "position": "WR",
                "team": "DET",
                "fantasy_positions": ["WR"],
                "active": True,
                "search_rank": 8,
                "age": 26,
            },
            "444": {
                "first_name": "Jahmyr",
                "last_name": "Gibbs",
                "position": "RB",
                "team": "DET",
                "fantasy_positions": ["RB"],
                "active": True,
                "search_rank": 9,
                "age": 24,
            },
            "555": {
                "first_name": "Trey",
                "last_name": "McBride",
                "position": "TE",
                "team": "ARI",
                "fantasy_positions": ["TE"],
                "active": True,
                "search_rank": 28,
                "age": 26,
            },
        },
    )


def seed_rankings(conn):
    rows = [
        {"player_name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "overall_rank": 2, "projected_points": 304},
        {"player_name": "Bijan Robinson", "team": "ATL", "position": "RB", "overall_rank": 4, "projected_points": 280},
        {"player_name": "Amon-Ra St. Brown", "team": "DET", "position": "WR", "overall_rank": 8, "projected_points": 270},
        {"player_name": "Jahmyr Gibbs", "team": "DET", "position": "RB", "overall_rank": 9, "projected_points": 260},
        {"player_name": "Trey McBride", "team": "ARI", "position": "TE", "overall_rank": 28, "projected_points": 210},
    ]
    import_ranking_rows(conn, "fantasypros", rows)


class FakeSleeperClient:
    def __init__(self, picks=None):
        self.picks = picks if picks is not None else [
            {
                "pick_no": 1,
                "round": 1,
                "draft_slot": 1,
                "roster_id": 1,
                "picked_by": "u1",
                "player_id": "111",
                "metadata": {"first_name": "Ja'Marr", "last_name": "Chase", "position": "WR", "team": "CIN"},
            },
            {
                "pick_no": 2,
                "round": 1,
                "draft_slot": 2,
                "roster_id": 2,
                "picked_by": "u2",
                "player_id": "222",
                "metadata": {"first_name": "Bijan", "last_name": "Robinson", "position": "RB", "team": "ATL"},
            },
        ]

    def fetch_league_snapshot(self, league_id):
        return {
            "league": {
                "league_id": league_id,
                "name": "Test League",
                "season": "2025",
                "status": "pre_draft",
                "total_rosters": 3,
                "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF", "K", "BN"],
                "scoring_settings": {"rec": 1},
                "settings": {},
                "previous_league_id": None,
            },
            "users": [
                {"user_id": "u1", "display_name": "Alex", "metadata": {"team_name": "Alpha"}},
                {"user_id": "u2", "display_name": "Mo", "metadata": {"team_name": "Mo Squad"}},
                {"user_id": "u3", "display_name": "Sam", "metadata": {"team_name": "Gamma"}},
            ],
            "rosters": [
                {"roster_id": 1, "owner_id": "u1"},
                {"roster_id": 2, "owner_id": "u2"},
                {"roster_id": 3, "owner_id": "u3"},
            ],
            "drafts": [{"draft_id": "D1"}],
            "traded_picks": [],
        }

    def draft(self, draft_id):
        return {
            "draft_id": draft_id,
            "season": "2025",
            "status": "pre_draft",
            "type": "snake",
            "settings": {"teams": 3, "rounds": 3},
            "metadata": {},
            "slot_to_roster_id": {"1": 1, "2": 2, "3": 3},
            "draft_order": {"u1": 1, "u2": 2, "u3": 3},
        }

    def draft_picks(self, draft_id):
        return self.picks


class SleeperDraftToolTests(unittest.TestCase):
    def test_startup_auto_import_uses_sleeper_when_empty(self):
        conn = memory_db()
        original = startup.SleeperClient

        class FakeStartupSleeper:
            def players(self, sport):
                if sport != "nfl":
                    raise AssertionError(sport)
                return {
                    "111": {
                        "first_name": "Ja'Marr",
                        "last_name": "Chase",
                        "position": "WR",
                        "team": "CIN",
                        "fantasy_positions": ["WR"],
                        "active": True,
                    }
                }

        try:
            startup.SleeperClient = FakeStartupSleeper
            result = startup.ensure_sleeper_players(conn)
        finally:
            startup.SleeperClient = original

        self.assertEqual(result["status"], "success")
        self.assertEqual(db.count_players_by_source(conn, "sleeper"), 1)
        self.assertFalse(startup.should_refresh_sleeper_players(conn))

    def test_sleeper_league_import_managers_drafts_board_and_my_picks(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        result = import_sleeper_league(conn, "L1", client=FakeSleeperClient())
        self.assertEqual(result["managers_imported"], 3)
        self.assertEqual(result["drafts_imported"], 1)
        self.assertEqual(result["draft_picks_imported"], 2)
        self.assertGreater(result["manager_tendencies"]["tendencies_imported"], 0)

        set_my_team(conn, "L1", 2)
        board = get_draft_board(conn, "L1")
        self.assertEqual(board["my_team"]["team_name"], "Mo Squad")
        self.assertEqual([pick["pick_no"] for pick in board["my_picks"]], [2, 5, 8])
        self.assertTrue(board["board"][0]["picks"][1]["is_mine"])
        self.assertEqual(board["board"][1]["picks"][1]["pick_no"], 5)

    def test_availability_and_practice_draft_simulation(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        import_sleeper_league(conn, "L1", client=FakeSleeperClient(picks=[]))
        set_my_team(conn, "L1", 2)

        available = estimate_availability(conn, "L1", 5, limit=3)
        self.assertEqual(available["target_pick"], 5)
        self.assertTrue(available["likely_available"])

        started = start_practice(conn, "L1")
        self.assertEqual(started["practice"]["current_pick"], 1)
        simulated = simulate_next(conn, "L1")
        self.assertEqual(simulated["practice"]["current_pick"], 2)
        self.assertEqual(len(simulated["picks"]), 1)

    def test_player_search_filters_and_detail_imports(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        search = search_players(conn, search="chase", position="WR", team="CIN", age_min=25, age_max=27, number="1", active=1)
        self.assertEqual(search["total"], 1)

        stats = import_stat_rows(
            conn,
            "espn",
            [
                {
                    "player_name": "Ja'Marr Chase",
                    "team": "CIN",
                    "position": "WR",
                    "season": 2025,
                    "week": 1,
                    "stat_type": "actual",
                    "targets": 12,
                    "receptions": 8,
                    "receiving_yards": 110,
                    "fantasy_points": 25,
                }
            ],
        )
        props = import_prop_rows(
            conn,
            "draftkings",
            "DraftKings",
            [
                {
                    "player_name": "Ja'Marr Chase",
                    "team": "CIN",
                    "position": "WR",
                    "market": "receiving_yards",
                    "line": 82.5,
                    "over_odds": "-110",
                    "under_odds": "-110",
                    "week": 1,
                    "season": 2025,
                }
            ],
        )
        self.assertEqual(stats["imported_count"], 1)
        self.assertEqual(props["imported_count"], 1)

        detail = player_detail(conn, "sleeper_111")
        self.assertIn("fantasypros", detail["rankings"])
        self.assertEqual(detail["stats"]["actual"][0]["receiving_yards"], 110)
        self.assertEqual(detail["props"][0]["sportsbook"], "DraftKings")

    def test_props_analysis_and_provider_fallback(self):
        analysis = analyze_props(
            [
                {"sportsbook": "DraftKings", "market": "receiving_yards", "line": 82.5},
                {"sportsbook": "FanDuel", "market": "receiving_yards", "line": 80.5},
            ]
        )
        self.assertEqual(analysis[0]["line_spread"], 2.0)
        self.assertTrue(any("highest" in note for note in analysis[0]["notes"]))

        with self.assertRaises(ProviderError):
            DraftKingsClient(api_key="").fetch()


if __name__ == "__main__":
    unittest.main()
