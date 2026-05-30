"""Import Sleeper projections into player_source_rankings."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db
from ..providers.sleeper import SleeperClient
from ..providers.sleeper_projections import SleeperProjectionsClient


def import_sleeper_projections(conn: sqlite3.Connection, season: int | None = None, week: int | None = None) -> dict[str, Any]:
    state = SleeperClient().nfl_state()
    season = int(season or state.get("season") or 2025)
    week = int(week or state.get("week") or 1)
    run_id = db.start_import_run(conn, "sleeper_projection", "projections")
    try:
        rows = SleeperProjectionsClient().fetch_week_projections(season, week)
        imported = _upsert_rows(conn, rows, season, week)
        db.finish_import_run(conn, run_id, "success", records_imported=imported)
        return {"status": "success", "season": season, "week": week, "records_imported": imported}
    except Exception as exc:
        db.finish_import_run(conn, run_id, "error", error_message=str(exc))
        raise


def _upsert_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]], season: int, week: int) -> int:
    imported = 0
    for row in rows:
        player_id = row.get("player_id")
        if not player_id:
            continue
        internal_id = f"sleeper_{player_id}"
        player_row = conn.execute(
            "SELECT internal_player_id FROM players WHERE sleeper_id = ? OR internal_player_id = ?",
            (str(player_id), internal_id),
        ).fetchone()
        if not player_row:
            continue
        internal_id = player_row["internal_player_id"]
        stats = row.get("stats") or {}
        projected = stats.get("pts_ppr") or stats.get("pts_std") or stats.get("fantasy_points")
        if projected is None:
            continue
        conn.execute(
            """
            INSERT INTO player_source_rankings (
                internal_player_id, source_name, projected_points, raw_json, imported_at
            )
            VALUES (?, 'sleeper_projection', ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(internal_player_id, source_name) DO UPDATE SET
                projected_points = excluded.projected_points,
                raw_json = excluded.raw_json,
                imported_at = CURRENT_TIMESTAMP
            """,
            (internal_id, float(projected), json.dumps({"season": season, "week": week, **row})),
        )
        imported += 1
    conn.commit()
    return imported
