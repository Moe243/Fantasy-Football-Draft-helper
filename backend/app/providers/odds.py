"""The Odds API adapter for weekly matchup context."""

from __future__ import annotations

from typing import Any

from ..config import settings
from .http import ProviderError, get_json


class OddsClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.odds_api_key
        self.base_url = (base_url or settings.odds_base_url).rstrip("/")

    def fetch_nfl_odds(self, regions: str = "us", markets: str = "h2h,spreads,totals") -> list[dict[str, Any]]:
        if not self.api_key:
            raise ProviderError("ODDS_API_KEY is not configured.")
        return get_json(
            f"{self.base_url}/sports/americanfootball_nfl/odds",
            {
                "apiKey": self.api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "american",
            },
        )
