import unittest

from backend.app.services.draft_room import make_draft_pick, player_id_on_cell
from backend.tests.test_sleeper_draft_tool import FakeSleeperClient, import_sleeper_league, memory_db, seed_players, seed_rankings, start_practice


class BoardPickReplaceTests(unittest.TestCase):
    def test_player_id_on_cell(self):
        cell = {"player": {"internal_player_id": "sleeper_111", "name": "Ja'Marr Chase"}}
        self.assertEqual(player_id_on_cell(cell), "sleeper_111")
        self.assertIsNone(player_id_on_cell({}))

    def test_replace_pick_on_same_cell(self):
        conn = memory_db()
        seed_players(conn)
        seed_rankings(conn)
        import_sleeper_league(conn, "L1", client=FakeSleeperClient(picks=[]))
        start_practice(conn, "L1")
        first = make_draft_pick(conn, "L1", "sleeper_111", pick_no=1)
        self.assertEqual(first["board"][0]["picks"][0]["player"]["internal_player_id"], "sleeper_111")
        second = make_draft_pick(conn, "L1", "sleeper_222", pick_no=1)
        self.assertEqual(second["board"][0]["picks"][0]["player"]["internal_player_id"], "sleeper_222")
        available_ids = {item["player"]["internal_player_id"] for item in second["best_available"]}
        self.assertNotIn("sleeper_222", available_ids)
        self.assertIn("sleeper_111", available_ids)


if __name__ == "__main__":
    unittest.main()
