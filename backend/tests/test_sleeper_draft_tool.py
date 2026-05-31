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
from backend.app.services.draft_history import draft_history_summary
from backend.app.services.draft_room import get_draft_state, make_draft_pick, remove_draft_pick
from backend.app.services.league_import import build_draft_slot_mapping, import_sleeper_league, set_my_team, update_draft_slots
from backend.app.services.player_detail import player_detail, search_players
from backend.app.services.pick_ownership import calculate_pick_ownership, snake_draft_slot
from backend.app.services.practice_draft import simulate_next, simulate_to_my_next_pick, start_practice
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

    def league_traded_picks(self, league_id):
        return []

    def draft_traded_picks(self, draft_id):
        return []


class OutOfOrderSleeperClient:
    def fetch_league_snapshot(self, league_id):
        users = [{"user_id": "u10", "display_name": "yahia21", "metadata": {"team_name": "Yahia"}}]
        users += [
            {"user_id": f"u{i}", "display_name": f"Manager {i}", "metadata": {"team_name": f"Team {i}"}}
            for i in range(1, 10)
        ]
        return {
            "league": {
                "league_id": league_id,
                "draft_id": "D10",
                "name": "Ten Team",
                "season": "2025",
                "status": "pre_draft",
                "total_rosters": 10,
                "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF", "K", "BN"],
                "scoring_settings": {"rec": 1},
                "settings": {},
                "previous_league_id": None,
            },
            "users": users,
            "rosters": [{"roster_id": 10, "owner_id": "u10"}] + [{"roster_id": i, "owner_id": f"u{i}"} for i in range(9, 0, -1)],
            "drafts": [{"draft_id": "D10"}],
            "traded_picks": [],
        }

    def draft(self, draft_id):
        return {
            "draft_id": draft_id,
            "season": "2025",
            "status": "pre_draft",
            "type": "snake",
            "settings": {"teams": 10, "rounds": 2},
            "metadata": {},
            "draft_order": {**{f"u{i}": i for i in range(1, 10)}, "u10": 10},
            "slot_to_roster_id": {**{str(i): i for i in range(1, 10)}, "10": 10},
        }

    def draft_picks(self, draft_id):
        return []

    def league_traded_picks(self, league_id):
        return []

    def draft_traded_picks(self, draft_id):
        return []


class MultiDraftSleeperClient(FakeSleeperClient):
    def fetch_league_snapshot(self, league_id):
        snapshot = super().fetch_league_snapshot(league_id)
        snapshot["league"]["draft_id"] = "D2025"
        snapshot["drafts"] = [{"draft_id": "D2025"}, {"draft_id": "D2024"}]
        return snapshot

    def draft(self, draft_id):
        season = "2025" if draft_id == "D2025" else "2024"
        return {
            "draft_id": draft_id,
            "season": season,
            "status": "complete" if draft_id == "D2024" else "pre_draft",
            "type": "snake",
            "settings": {"teams": 3, "rounds": 3},
            "metadata": {},
            "slot_to_roster_id": {"1": 1, "2": 2, "3": 3},
            "draft_order": {"u1": 1, "u2": 2, "u3": 3},
        }

    def draft_picks(self, draft_id):
        if draft_id == "D2025":
            return []
        return [
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

    def league_traded_picks(self, league_id):
        return [{"season": "2025", "round": 1, "roster_id": 1, "previous_owner_id": 1, "owner_id": 2}]

    def draft_traded_picks(self, draft_id):
        if draft_id == "D2025":
            return [{"season": "2025", "round": 2, "roster_id": 2, "previous_owner_id": 2, "owner_id": 3}]
        return []


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

    def test_draft_state_pick_and_remove_updates_board_and_available(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        import_sleeper_league(conn, "L1", client=FakeSleeperClient(picks=[]))
        set_my_team(conn, "L1", 2)
        start_practice(conn, "L1")

        before = get_draft_state(conn, "L1")
        self.assertEqual(before["current_pick"], 1)
        self.assertTrue(before["board"][0]["picks"][0]["is_current_pick"])

        after = make_draft_pick(conn, "L1", "sleeper_111")
        self.assertEqual(after["current_pick"], 2)
        self.assertEqual(after["board"][0]["picks"][0]["player"]["full_name"], "Ja'Marr Chase")
        available_ids = {item["player"]["internal_player_id"] for item in after["best_available"]}
        self.assertNotIn("sleeper_111", available_ids)

        removed = remove_draft_pick(conn, "L1", 1)
        self.assertEqual(removed["current_pick"], 1)
        self.assertIsNone(removed["board"][0]["picks"][0]["player"])

    def test_mock_draft_state_metadata_and_simulate_guard(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        import_sleeper_league(conn, "L1", client=FakeSleeperClient(picks=[]))
        set_my_team(conn, "L1", 2)
        start_practice(conn, "L1")
        state_payload = get_draft_state(conn, "L1")
        self.assertEqual(state_payload["draft_mode"], "mock")
        simulate_to_my_next_pick(conn, "L1")
        with self.assertRaises(ValueError):
            simulate_next(conn, "L1")

    def test_favorite_player_boosts_ranking(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        from backend.app.services.user_preferences import add_favorite
        from backend.app.services.recommendations import database_draft_recommendations
        from backend.app.models import LeagueSettings
        add_favorite(conn, "L1", "sleeper_111")
        recs = database_draft_recommendations(conn, LeagueSettings(), keepers=[], picks=[], limit=20, league_id="L1")
        favorite_rec = next(item for item in recs if item["player"]["internal_player_id"] == "sleeper_111")
        self.assertTrue(favorite_rec["signals"]["favorite"])

    def test_sleeper_draft_order_metadata_overrides_user_and_roster_order(self):
        conn = memory_db()
        result = import_sleeper_league(conn, "L10", client=OutOfOrderSleeperClient())

        yahia_mapping = next(item for item in result["draft_mapping"] if item["display_name"] == "yahia21")
        self.assertEqual(yahia_mapping["draft_slot"], 10)
        self.assertEqual(yahia_mapping["roster_id"], 10)
        self.assertEqual([item["draft_slot"] for item in result["draft_mapping"]], list(range(1, 11)))

        managers = conn.execute(
            """
            SELECT lm.display_name, ds.draft_slot
            FROM league_managers lm
            JOIN draft_slots ds ON ds.league_id = lm.league_id AND ds.roster_id = lm.roster_id
            WHERE lm.league_id = ?
            ORDER BY ds.draft_slot
            """,
            ("L10",),
        ).fetchall()
        self.assertEqual(managers[-1]["display_name"], "yahia21")
        self.assertEqual(managers[-1]["draft_slot"], 10)

        set_my_team(conn, "L10", 10)
        board = get_draft_board(conn, "L10")
        self.assertEqual(board["draft_order"][9]["manager_name"], "Yahia")
        self.assertEqual(board["board"][0]["picks"][9]["pick_no"], 10)
        self.assertEqual(board["board"][0]["picks"][9]["roster_id"], 10)
        self.assertTrue(board["board"][0]["picks"][9]["is_mine"])
        self.assertEqual(board["board"][1]["picks"][9]["pick_no"], 11)
        self.assertEqual([pick["pick_no"] for pick in board["my_picks"]], [10, 11])

    def test_build_draft_slot_mapping_does_not_sort_alphabetically_or_by_roster_id(self):
        users = [
            {"user_id": "u10", "display_name": "yahia21"},
            {"user_id": "u1", "display_name": "Alpha"},
            {"user_id": "u2", "display_name": "Beta"},
        ]
        rosters = [
            {"roster_id": 10, "owner_id": "u10"},
            {"roster_id": 2, "owner_id": "u2"},
            {"roster_id": 1, "owner_id": "u1"},
        ]
        league = {"league_id": "L3", "draft_id": "D3", "total_rosters": 3}
        drafts = [
            {
                "draft_id": "D3",
                "settings": {"teams": 3},
                "draft_order": {"u10": 3, "u1": 1, "u2": 2},
                "slot_to_roster_id": {"1": 1, "2": 2, "3": 10},
            }
        ]

        mapping = build_draft_slot_mapping(league, users, rosters, drafts)

        self.assertEqual([item["display_name"] for item in mapping], ["Alpha", "Beta", "yahia21"])
        self.assertEqual(mapping[-1]["draft_slot"], 3)
        self.assertEqual(mapping[-1]["roster_id"], 10)

    def test_manual_draft_slot_update_recalculates_my_picks(self):
        conn = memory_db()
        import_sleeper_league(conn, "L1", client=FakeSleeperClient(picks=[]))
        set_my_team(conn, "L1", 2)

        update_draft_slots(
            conn,
            "L1",
            [
                {"sleeper_user_id": "u1", "roster_id": 1, "draft_slot": 1},
                {"sleeper_user_id": "u3", "roster_id": 3, "draft_slot": 2},
                {"sleeper_user_id": "u2", "roster_id": 2, "draft_slot": 3},
            ],
        )
        board = get_draft_board(conn, "L1")
        self.assertEqual(board["draft_order"][2]["roster_id"], 2)
        self.assertEqual([pick["pick_no"] for pick in board["my_picks"]], [3, 4, 9])

    def test_multi_draft_import_traded_picks_board_and_history(self):
        conn = memory_db()
        seed_players(conn)
        result = import_sleeper_league(conn, "L2", client=MultiDraftSleeperClient())

        self.assertEqual(result["drafts_imported"], 2)
        self.assertEqual(result["draft_picks_imported"], 2)
        self.assertEqual(result["traded_picks_imported"], 2)
        self.assertEqual(result["active_draft_id"], "D2025")

        traded_rows = conn.execute("SELECT * FROM league_traded_picks WHERE league_id = ?", ("L2",)).fetchall()
        self.assertEqual(len(traded_rows), 2)

        set_my_team(conn, "L2", 2)
        board = get_draft_board(conn, "L2")
        self.assertEqual(board["active_draft_id"], "D2025")
        self.assertEqual(board["board"][0]["picks"][0]["original_roster_id"], 1)
        self.assertEqual(board["board"][0]["picks"][0]["current_roster_id"], 2)
        self.assertTrue(board["board"][0]["picks"][0]["is_traded"])
        self.assertTrue(board["board"][0]["picks"][0]["is_mine"])
        self.assertEqual(board["board"][1]["picks"][1]["original_roster_id"], 2)
        self.assertEqual(board["board"][1]["picks"][1]["current_roster_id"], 3)
        self.assertTrue(board["board"][1]["picks"][1]["is_traded"])
        self.assertFalse(board["board"][1]["picks"][1]["is_mine"])

        my_picks = [pick["pick_no"] for pick in board["my_picks"]]
        self.assertIn(1, my_picks)
        self.assertNotIn(5, my_picks)

        history = draft_history_summary(conn, "L2")
        self.assertEqual(len(history["drafts"]), 2)
        self.assertTrue(any(item["pick_count"] == 2 for item in history["drafts"]))
        self.assertTrue(history["history_by_manager"])

    def test_pick_ownership_uses_ten_team_snake_and_trades(self):
        self.assertEqual([snake_draft_slot(pick, 10) for pick in (1, 10, 11, 20, 21, 30, 31)], [1, 10, 10, 1, 1, 10, 10])
        managers = [
            {"roster_id": slot, "team_name": f"Team {slot}"}
            for slot in range(1, 11)
        ]
        slots = [
            {"draft_slot": slot, "roster_id": slot}
            for slot in range(1, 11)
        ]
        picks = calculate_pick_ownership(
            "L10",
            "D10",
            "2025",
            managers,
            slots,
            [{"season": "2025", "round": 3, "roster_id": 10, "owner_id": 4}],
            10,
            4,
            my_roster_id=10,
        )

        yahia_picks = [pick["pick_no"] for pick in picks if pick["original_roster_id"] == 10]
        self.assertEqual(yahia_picks, [10, 11, 30, 31])
        traded = next(pick for pick in picks if pick["pick_no"] == 30)
        self.assertEqual(traded["current_roster_id"], 4)
        self.assertEqual(traded["source"], "traded_pick")
        self.assertFalse(traded["is_mine"])

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
