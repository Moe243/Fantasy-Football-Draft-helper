"""Import Sleeper projections into player_source_rankings."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from ..providers.sleeper_projections import SleeperProjectionsClient


def _internal_player_id(conn: sqlite3.Connection, sleeper_id: str) -> str | None:
    row = conn.execute(
        "SELECT internal_player_id FROM players WHERE sleeper_id = ?",
        (sleeper_id,),
    ).fetchone()
    if row:
        return row["internal_player_id"]
    candidate = f"sleeper_{sleeper_id}"
    row = conn.execute(
        "SELECT internal_player_id FROM players WHERE internal_player_id = ?",
        (candidate,),
    ).fetchone()
    return row["internal_player_id"] if row else None


def import_sleeper_projections(
    conn: sqlite3.Connection,
    season: int = 2025,
    week: int = 1,
) -> dict[str, Any]:
    client = SleeperProjectionsClient()
    rows = client.fetch_week(season, week)
    imported = 0
    for row in rows:
        sleeper_id = str(row.get("player_id") or "")
        internal_id = _internal_player_id(conn, sleeper_id)
        if not internal_id:
            continue
        stats = row.get("stats") or row
        projected = _projected_points(stats)
        if projected is None:
            continue
        conn.execute(
            """
            INSERT INTO player_source_rankings (
                internal_player_id, source_name, source_player_id,
                projected_points, raw_json, imported_at
            )
            VALUES (?, 'sleeper_projection', ?, ?, ?, ?)
            ON CONFLICT(internal_player_id, source_name) DO UPDATE SET
                projected_points = excluded.projected_points,
                raw_json = excluded.raw_json,
                imported_at = excluded.imported_at
            """,
            (
                internal_id,
                sleeper_id,
                projected,
                json.dumps(row),
                datetime.utcnow().isoformat(),
            ),
        )
        imported += 1
    conn.execute(
        """
        INSERT INTO source_import_runs (source_name, import_type, status, records_imported, finished_at)
        VALUES ('sleeper_projection', 'projections', 'ok', ?, CURRENT_TIMESTAMP)
        """,
        (imported,),
    )
    conn.commit()
    return {"imported": imported, "season": season, "week": week, "source": "sleeper_projection"}


def _projected_points(stats: dict[str, Any]) -> float | None:
    for key in ("pts_ppr", "pts_half_ppr", "pts_std", "fantasy_points", "fpts"):
        if stats.get(key) is not None:
            return float(stats[key])
    return None
