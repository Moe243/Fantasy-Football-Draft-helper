"""Sleeper API adapter.

Sleeper is the primary league integration for this MVP because it exposes public
league, roster, draft, player, and trending-player endpoints without requiring a
paid data agreement.
"""

from __future__ import annotations

from typing import Any

from ..config import settings
from .http import ProviderError, get_json


class SleeperClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.sleeper_base_url).rstrip("/")

    def user(self, username_or_id: str) -> dict[str, Any]:
        return get_json(f"{self.base_url}/user/{username_or_id}")

    def leagues_for_user(self, user_id: str, season: str, sport: str = "nfl") -> list[dict[str, Any]]:
        return get_json(f"{self.base_url}/user/{user_id}/leagues/{sport}/{season}")

    def league(self, league_id: str) -> dict[str, Any]:
        return get_json(f"{self.base_url}/league/{league_id}")

    def rosters(self, league_id: str) -> list[dict[str, Any]]:
        return self._safe_list(f"{self.base_url}/league/{league_id}/rosters")

    def users(self, league_id: str) -> list[dict[str, Any]]:
        return self._safe_list(f"{self.base_url}/league/{league_id}/users")

    def drafts(self, league_id: str) -> list[dict[str, Any]]:
        return self._safe_list(f"{self.base_url}/league/{league_id}/drafts")

    def draft_picks(self, draft_id: str) -> list[dict[str, Any]]:
        return self._safe_list(f"{self.base_url}/draft/{draft_id}/picks")

    def draft(self, draft_id: str) -> dict[str, Any]:
        return get_json(f"{self.base_url}/draft/{draft_id}")

    def traded_picks(self, league_id: str) -> list[dict[str, Any]]:
        return self.league_traded_picks(league_id)

    def league_traded_picks(self, league_id: str) -> list[dict[str, Any]]:
        return self._safe_list(f"{self.base_url}/league/{league_id}/traded_picks")

    def draft_traded_picks(self, draft_id: str) -> list[dict[str, Any]]:
        return self._safe_list(f"{self.base_url}/draft/{draft_id}/traded_picks")

    def nfl_state(self) -> dict[str, Any]:
        return get_json(f"{self.base_url}/state/nfl")

    def players(self, sport: str = "nfl") -> dict[str, Any]:
        return get_json(f"{self.base_url}/players/{sport}", timeout=30)

    def trending(self, trend_type: str = "add", sport: str = "nfl", lookback_hours: int = 24, limit: int = 50) -> list[dict[str, Any]]:
        return get_json(
            f"{self.base_url}/players/{sport}/trending/{trend_type}",
            {"lookback_hours": lookback_hours, "limit": limit},
        )

    def fetch_league_snapshot(self, league_id: str) -> dict[str, Any]:
        league = self.league(league_id)
        drafts = self.drafts(league_id)
        active_draft = drafts[0] if drafts else None
        picks: list[dict[str, Any]] = []
        if active_draft and active_draft.get("draft_id"):
            picks = self.draft_picks(active_draft["draft_id"])
            active_draft = self.draft(active_draft["draft_id"])
        return {
            "league": league,
            "rosters": self.rosters(league_id),
            "users": self.users(league_id),
            "drafts": drafts,
            "active_draft": active_draft,
            "picks": picks,
            "traded_picks": self.traded_picks(league_id),
        }

    def _safe_list(self, url: str) -> list[dict[str, Any]]:
        try:
            payload = get_json(url)
        except ProviderError:
            return []
        return payload if isinstance(payload, list) else []
