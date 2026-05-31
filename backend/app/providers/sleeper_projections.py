"""Unofficial Sleeper NFL projections endpoint."""

from __future__ import annotations

from typing import Any

from .http import get_json

SLEEPER_PROJECTIONS_BASE = "https://api.sleeper.app/projections/nfl"


class SleeperProjectionsClient:
  def fetch_week(
      self,
      season: int,
      week: int,
      season_type: str = "regular",
  ) -> list[dict[str, Any]]:
      url = f"{SLEEPER_PROJECTIONS_BASE}/{season}/{week}"
      payload = get_json(url, {"season_type": season_type})
      if isinstance(payload, dict):
          return [
              {"player_id": key, **(value or {})}
              for key, value in payload.items()
              if key and value
          ]
      if isinstance(payload, list):
          return payload
      return []
