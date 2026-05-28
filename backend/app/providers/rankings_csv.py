"""JSON-first ranking import adapter.

The name keeps room for file-based CSV upload later. For this local MVP the
frontend posts parsed rows as JSON, which is easier to test and avoids adding a
multipart parser to the standard-library backend.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .. import db
from ..services.normalization import match_player, normalize_name, normalize_position, normalize_team


def import_ranking_rows(conn: sqlite3.Connection, source_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    clean_source = normalize_source_name(source_name)
    run_id = db.start_import_run(conn, clean_source, "rankings_json")
    imported = 0
    skipped = 0
    created_players = 0
    matched_players = 0
    try:
        for row in rows:
            player_name = str(row.get("player_name") or row.get("full_name") or row.get("name") or "").strip()
            if not player_name:
                skipped += 1
                continue

            position = normalize_position(str(row.get("position") or ""))
            team = normalize_team(str(row.get("team") or ""))
            source_player_id = optional_str(row.get("source_player_id") or row.get("player_id"))
            player = match_player(
                conn,
                player_name,
                position=position,
                team=team,
                source_player_id=source_player_id,
                source_name=clean_source,
            )
            internal_player_id = player["internal_player_id"] if player else make_internal_player_id(
                clean_source,
                player_name,
                position,
                team,
                source_player_id,
            )
            if player:
                matched_players += 1
            else:
                created_players += 1
                db.upsert_player(
                    conn,
                    {
                        "internal_player_id": internal_player_id,
                        "full_name": player_name,
                        "first_name": first_name(player_name),
                        "last_name": last_name(player_name),
                        "normalized_name": normalize_name(player_name),
                        f"{clean_source}_id": source_player_id,
                        "position": position,
                        "team": team,
                        "fantasy_positions": [position] if position else [],
                        "active": 1,
                        "source": clean_source,
                    },
                )

            db.upsert_source_ranking(
                conn,
                {
                    "internal_player_id": internal_player_id,
                    "source_name": clean_source,
                    "source_player_id": source_player_id,
                    "overall_rank": row.get("overall_rank"),
                    "position_rank": optional_str(row.get("position_rank")),
                    "adp": row.get("adp"),
                    "projected_points": row.get("projected_points"),
                    "tier": row.get("tier"),
                    "bye_week": row.get("bye_week"),
                    "raw_json": json.dumps(row),
                },
            )
            imported += 1
        db.finish_import_run(conn, run_id, "success", imported)
        return {
            "source_name": clean_source,
            "status": "success",
            "imported_count": imported,
            "skipped_count": skipped,
            "created_players": created_players,
            "matched_players": matched_players,
        }
    except Exception as exc:
        db.finish_import_run(conn, run_id, "error", imported, str(exc))
        raise


def normalize_source_name(source_name: str) -> str:
    source = re.sub(r"[^a-z0-9_]+", "_", str(source_name or "").lower()).strip("_")
    if not source:
        raise ValueError("source_name is required")
    return source


def make_internal_player_id(
    source_name: str,
    player_name: str,
    position: str | None,
    team: str | None,
    source_player_id: str | None,
) -> str:
    if source_player_id:
        return f"{source_name}_{source_player_id}"
    slug = normalize_name(player_name).replace(" ", "_")
    suffix = "_".join(item.lower() for item in [team, position] if item)
    return f"{source_name}_{slug}_{suffix}".strip("_")


def first_name(full_name: str) -> str | None:
    parts = full_name.split()
    return parts[0] if parts else None


def last_name(full_name: str) -> str | None:
    parts = full_name.split()
    return parts[-1] if len(parts) > 1 else None


def optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)
