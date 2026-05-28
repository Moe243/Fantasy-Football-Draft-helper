import unittest

from backend.app.models import DraftPick, Keeper, LeagueSettings
from backend.app.services.recommendations import (
    chat_response,
    current_pick_number,
    draft_recommendations,
    evaluate_keeper,
)


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.settings = LeagueSettings()

    def test_keepers_are_removed_from_draft_recommendations(self):
        keepers = [Keeper(player_id="p_wr_chase", team_name="Team A", round=1, pick_no=1)]
        recs = draft_recommendations(self.settings, keepers, picks=[], limit=20)
        names = {rec.player.name for rec in recs}
        self.assertNotIn("Ja'Marr Chase", names)

    def test_current_pick_accounts_for_manual_keeper_pick(self):
        keepers = [Keeper(player_id="p_rb_bijan", team_name="Team A", pick_no=8)]
        picks = [DraftPick(pick_no=3, player_id="p_wr_chase", manager="opponent")]
        self.assertEqual(current_pick_number(picks, keepers), 9)

    def test_chat_understands_rbs_gaining_value(self):
        response = chat_response("Which RBs are gaining value?", self.settings, keepers=[], picks=[])
        self.assertEqual(response["intent"], "waiver_risers")
        self.assertEqual(set(response["groups"].keys()), {"RB"})

    def test_keeper_evaluation_uses_round_cost(self):
        result = evaluate_keeper("Ja'Marr Chase", keep_round=3, settings=self.settings)
        self.assertEqual(result["decision"], "Keep")
        self.assertGreater(result["surplus_picks"], 20)


if __name__ == "__main__":
    unittest.main()
