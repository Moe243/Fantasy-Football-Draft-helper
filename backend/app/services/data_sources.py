"""Report configured external data sources."""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from ..config import settings


def data_sources_status(conn: sqlite3.Connection) -> dict[str, Any]:
    sources = ("sleeper", "sleeper_projection", "the_odds_api", "espn", "fantasypros")
    latest = {
        name: dict(row) if (row := _latest_import(conn, name)) else None
        for name in sources
    }
    return {
        "keys": {
            "odds_api": bool(settings.odds_api_key),
            "espn": bool(os.getenv("ESPN_API_KEY", "")),
            "draftkings": bool(os.getenv("DRAFTKINGS_API_KEY", "")),
            "fanduel": bool(os.getenv("FANDUEL_API_KEY", "")),
            "caesars": bool(os.getenv("CAESARS_API_KEY", "")),
            "draft365": bool(os.getenv("DRAFT365_API_KEY", "")),
            "sleeper": True,
        },
        "notes": {
            "odds_api": "The Odds API powers game lines and player props. Props may require a paid tier.",
            "espn": "ESPN fantasy has no public API key. Import rankings JSON with source_name=espn.",
            "draftkings": "Use Odds API bookmakers for DK lines; no direct DK fantasy API.",
            "sleeper": "Public Sleeper API for leagues; projections use an unofficial endpoint.",
        },
        "latest_imports": latest,
        "players_loaded": conn.execute("SELECT COUNT(*) AS c FROM players").fetchone()["c"],
    }


def _latest_import(conn: sqlite3.Connection, source_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT source_name, import_type, status, records_imported, finished_at, error_message
        FROM source_import_runs
        WHERE source_name = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_name,),
    ).fetchone()
