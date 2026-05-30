"""Fetch and normalize NFL stats from a public JSON/CSV URL."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

from ..config import settings
from .http import ProviderError, get_json
from ..services.normalization import normalize_position, normalize_team


class NFLStatsProvider:
    """Load nflfastR-style weekly stats from a remote or local file."""

    def __init__(self, source_url: str | None = None, season: int | str | None = None) -> None:
        self.source_url = (source_url or settings.nfl_stats_source_url or "").strip()
        self.season = str(season or settings.nfl_stats_season or "").strip()

    def fetch_rows(self) -> list[dict[str, Any]]:
        if not self.source_url:
            raise ProviderError("NFL stats source is not configured.")
        raw_rows = self._load_raw_rows(self.source_url)
        normalized = [self.normalize_row(row) for row in raw_rows]
        return [row for row in normalized if row.get("player_name")]

    def normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        player_name = (
            row.get("player_name")
            or row.get("player_display_name")
            or row.get("name")
            or ""
        )
        team = row.get("team") or row.get("recent_team") or ""
        position = (
            row.get("position")
            or row.get("position_group")
            or row.get("fantasy_position")
            or ""
        )
        fantasy_points = row.get("fantasy_points")
        if fantasy_points in {None, ""}:
            fantasy_points = row.get("fantasy_points_ppr") or row.get("fantasy_points_half_ppr")

        stat_type = str(row.get("stat_type") or "actual").lower().strip()
        if stat_type not in {"actual", "projected"}:
            stat_type = "actual"

        season = row.get("season") or self.season
        week = row.get("week")

        normalized: dict[str, Any] = {
            "player_name": str(player_name).strip(),
            "team": normalize_team(str(team)),
            "position": normalize_position(str(position)),
            "season": int(season) if season not in {None, ""} else None,
            "week": int(week) if week not in {None, ""} else None,
            "stat_type": stat_type,
            "fantasy_points": fantasy_points,
            "games_played": row.get("games_played") or row.get("games"),
            "passing_yards": row.get("passing_yards"),
            "passing_tds": row.get("passing_tds") or row.get("passing_touchdowns"),
            "interceptions": row.get("interceptions") or row.get("passing_interceptions"),
            "rushing_attempts": row.get("rushing_attempts") or row.get("carries"),
            "rushing_yards": row.get("rushing_yards"),
            "rushing_tds": row.get("rushing_tds") or row.get("rushing_touchdowns"),
            "targets": row.get("targets") or row.get("receiving_targets"),
            "receptions": row.get("receptions") or row.get("catches"),
            "receiving_yards": row.get("receiving_yards"),
            "receiving_tds": row.get("receiving_tds") or row.get("receiving_touchdowns"),
        }
        return normalized

    def _load_raw_rows(self, url: str) -> list[dict[str, Any]]:
        if url.startswith("file://"):
            path = Path(unquote(urlparse(url).path))
            content = path.read_text(encoding="utf-8")
        else:
            content = None
            candidates = [
                Path(url),
                settings.nfl_stats_cache_path.parent.parent / url,
                settings.nfl_stats_cache_path.parent.parent / "sample_data" / Path(url).name,
            ]
            for path in candidates:
                if path.is_file():
                    content = path.read_text(encoding="utf-8")
                    url = str(path)
                    break
            if content is None:
                return self._fetch_remote(url)

        rows = self._parse_content(content, url)
        self._write_cache(rows)
        return rows

    def _fetch_remote(self, url: str) -> list[dict[str, Any]]:
        lowered = url.lower().split("?", 1)[0]
        if lowered.endswith(".csv"):
            request = __import__("urllib.request").Request(
                url,
                headers={"User-Agent": "fantasy-football-assistant/0.1"},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    content = response.read().decode("utf-8")
            except Exception as exc:
                raise ProviderError(f"Could not reach {url}: {exc}") from exc
            rows = self._parse_content(content, url)
        else:
            payload = get_json(url, timeout=30)
            rows = self._json_to_rows(payload)
        self._write_cache(rows)
        return rows

    def _parse_content(self, content: str, url: str) -> list[dict[str, Any]]:
        if url.lower().endswith(".csv"):
            return self._parse_csv(content)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Could not parse NFL stats from {url}: {exc}") from exc
        return self._json_to_rows(payload)

    def _json_to_rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("data", "rows", "players", "stats"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
        raise ProviderError("NFL stats JSON must be a list or an object with a data/rows array.")

    def _parse_csv(self, content: str) -> list[dict[str, Any]]:
        reader = csv.DictReader(StringIO(content))
        return [dict(row) for row in reader]

    def _write_cache(self, rows: list[dict[str, Any]]) -> None:
        cache_path = settings.nfl_stats_cache_path
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        except OSError:
            pass
