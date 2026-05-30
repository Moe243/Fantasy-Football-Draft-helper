"""nflverse release helpers (stats_player) without third-party deps."""

from __future__ import annotations

import csv
import io
from typing import Any
from urllib.request import urlopen

from .http import ProviderError

NFLVERSE_RELEASE_BASE = "https://github.com/nflverse/nflverse-data/releases/download"


def stats_player_csv_url(season: int) -> str:
    return f"{NFLVERSE_RELEASE_BASE}/stats_player/stats_player_week_{season}.csv"


def fetch_csv_text(url: str, timeout: int = 30) -> str:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        raise ProviderError(f"Could not download nflverse CSV from {url}: {exc}") from exc


def parse_csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def fetch_stats_player_rows(season: int, limit: int | None = None) -> list[dict[str, Any]]:
    text = fetch_csv_text(stats_player_csv_url(season))
    rows = [normalize_stat_row(row) for row in parse_csv_rows(text)]
    rows = [row for row in rows if row.get("player_name")]
    if limit is not None:
        return rows[:limit]
    return rows


def normalize_stat_row(row: dict[str, Any]) -> dict[str, Any]:
    player_name = (
        row.get("player_name")
        or row.get("player_display_name")
        or row.get("display_name")
        or ""
    )
    position = row.get("position") or row.get("pos") or ""
    team = row.get("recent_team") or row.get("team") or row.get("team_abbr") or ""
    fantasy_points = (
        row.get("fantasy_points")
        or row.get("fantasy_points_ppr")
        or row.get("fantasy_points_half_ppr")
    )
    return {
        "player_name": str(player_name).strip(),
        "position": str(position).strip(),
        "team": str(team).strip(),
        "season": optional_int(row.get("season")),
        "week": optional_int(row.get("week")),
        "stat_type": "actual",
        "sleeper_id": optional_str(row.get("sleeper_id")),
        "espn_id": optional_str(row.get("espn_id")),
        "passing_yards": optional_float(row.get("passing_yards")),
        "passing_tds": optional_float(row.get("passing_tds")),
        "interceptions": optional_float(row.get("interceptions")),
        "rushing_attempts": optional_float(row.get("rushing_attempts") or row.get("carries")),
        "rushing_yards": optional_float(row.get("rushing_yards")),
        "rushing_tds": optional_float(row.get("rushing_tds")),
        "targets": optional_float(row.get("targets")),
        "receptions": optional_float(row.get("receptions")),
        "receiving_yards": optional_float(row.get("receiving_yards")),
        "receiving_tds": optional_float(row.get("receiving_tds")),
        "fantasy_points": optional_float(fantasy_points),
    }


def optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)
