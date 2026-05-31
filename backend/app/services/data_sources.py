"""Setup status for configured external data sources."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..config import settings


def data_sources_status(conn: sqlite3.Connection) -> dict[str, Any]:
    def last_import(source: str, import_type: str | None = None) -> dict[str, Any] | None:
        query = """
            SELECT source_name, import_type, status, records_imported, finished_at
            FROM source_import_runs
            WHERE source_name = ?
        """
        params: list[Any] = [source]
        if import_type:
            query += " AND import_type = ?"
            params.append(import_type)
        query += " ORDER BY id DESC LIMIT 1"
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None

    player_count = conn.execute("SELECT COUNT(*) AS c FROM players").fetchone()["c"]
    ranking_count = conn.execute("SELECT COUNT(*) AS c FROM player_source_rankings").fetchone()["c"]
    prop_count = conn.execute("SELECT COUNT(*) AS c FROM player_props").fetchone()["c"]

    return {
        "odds_api": {
            "configured": bool(settings.odds_api_key),
            "env_var": "ODDS_API_KEY",
            "last_import": last_import("odds_api", "game_odds"),
            "note": "Player props often require a paid Odds API tier.",
        },
        "sleeper_players": {
            "configured": True,
            "env_var": None,
            "last_import": last_import("sleeper", "players"),
            "player_count": player_count,
        },
        "sleeper_projections": {
            "configured": True,
            "env_var": None,
            "last_import": last_import("sleeper_projection", "projections"),
            "note": "Unofficial Sleeper projections endpoint.",
        },
        "rankings_import": {
            "configured": True,
            "env_var": None,
            "ranking_rows": ranking_count,
            "note": "Use POST /api/rankings/import/csv with source_name espn or fantasypros.",
        },
        "espn": {
            "configured": False,
            "env_var": "ESPN_API_KEY",
            "note": "No public ESPN fantasy API key. Import ESPN ranks via JSON/CSV instead.",
        },
        "sportsbook_keys": {
            "configured": False,
            "env_vars": ["DRAFTKINGS_API_KEY", "FANDUEL_API_KEY", "CAESARS_API_KEY"],
            "note": "Aggregate props through Odds API bookmakers, not separate fantasy APIs.",
        },
        "player_props": {
            "row_count": prop_count,
            "last_import": last_import("odds_api"),
        },
    }
