"""Provider protocols used by the app services."""

from __future__ import annotations

from typing import Any, Protocol


class LeagueProvider(Protocol):
    def fetch_league_snapshot(self, league_id: str) -> dict[str, Any]:
        """Return league settings, rosters, users, draft metadata, and picks."""


class OddsProvider(Protocol):
    def fetch_nfl_odds(self, regions: str = "us", markets: str = "h2h,spreads,totals") -> list[dict[str, Any]]:
        """Return NFL betting market data for matchup context."""
