"""Import Center status for Setup."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import db


def import_run_summary(conn: sqlite3.Connection, source_name: str, import_type: str) -> dict[str, Any] | None:
    row = db.latest_import_run(conn, source_name, import_type)
    if not row:
        return None
    return {
        "source_name": row["source_name"],
        "import_type": row["import_type"],
        "status": row["status"],
        "imported_count": row["records_imported"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_message": row["error_message"],
    }


def ranking_source_summary(conn: sqlite3.Connection, source_name: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count, MAX(imported_at) AS last_import
        FROM player_source_rankings
        WHERE source_name = ?
        """,
        (source_name,),
    ).fetchone()
    latest = import_run_summary(conn, source_name, "rankings_json")
    return {
        "source_name": source_name,
        "ranking_rows": int(row["count"] or 0),
        "last_import": row["last_import"] or (latest or {}).get("finished_at"),
        "latest_run": latest,
    }


def stat_source_summary(conn: sqlite3.Connection, source_name: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count, MAX(imported_at) AS last_import
        FROM player_stat_lines
        WHERE source_name = ?
        """,
        (source_name,),
    ).fetchone()
    latest = import_run_summary(conn, source_name, "stats")
    return {
        "source_name": source_name,
        "stat_rows": int(row["count"] or 0),
        "last_import": row["last_import"] or (latest or {}).get("finished_at"),
        "latest_run": latest,
    }


def get_import_center_status(conn: sqlite3.Connection, league_id: str | None = None) -> dict[str, Any]:
    latest_players = import_run_summary(conn, "sleeper", "players")
    latest_league = import_run_summary(conn, "sleeper", "league")
    panels = [
        {
            "key": "sleeper_players",
            "title": "Sleeper Players",
            "source_name": "sleeper",
            "import_type": "players",
            "players_loaded": db.count_players_by_source(conn, "sleeper"),
            "latest_run": latest_players,
        },
        {
            "key": "sleeper_league",
            "title": "Sleeper League",
            "source_name": "sleeper",
            "import_type": "league",
            "league_id": league_id,
            "latest_run": latest_league,
        },
        {
            "key": "nflverse_stats",
            "title": "nflverse Stats",
            "source_name": "nflverse",
            "import_type": "stats",
            **stat_source_summary(conn, "nflverse"),
        },
        {
            "key": "espn_rankings",
            "title": "ESPN Rankings",
            "source_name": "espn",
            "import_type": "rankings_json",
            **ranking_source_summary(conn, "espn"),
        },
        {
            "key": "fantasypros_rankings",
            "title": "FantasyPros Rankings",
            "source_name": "fantasypros",
            "import_type": "rankings_json",
            **ranking_source_summary(conn, "fantasypros"),
        },
    ]
    return {"panels": panels, "players_loaded": db.count_players_by_source(conn, "sleeper")}
