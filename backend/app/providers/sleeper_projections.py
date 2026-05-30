"""Sleeper NFL projections (unofficial endpoint)."""

from __future__ import annotations

from typing import Any

from .http import get_json


PROJECTIONS_BASE = "https://api.sleeper.app/projections/nfl"


class SleeperProjectionsClient:
    def fetch_week_projections(
        self,
        season: int,
        week: int,
        season_type: str = "regular",
    ) -> list[dict[str, Any]]:
        positions = "position[]=QB&position[]=RB&position[]=WR&position[]=TE&position[]=K&position[]=DEF"
        url = f"{PROJECTIONS_BASE}/{season}/{week}?season_type={season_type}&{positions}"
        data = get_json(url, timeout=45)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.values())
        return []
