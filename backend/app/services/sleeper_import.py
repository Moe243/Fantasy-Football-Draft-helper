"""Sleeper player import pipeline."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db
from .normalization import FANTASY_POSITIONS, normalize_name, normalize_position, normalize_team


def import_sleeper_players(conn: sqlite3.Connection, sleeper_players: dict[str, dict[str, Any]]) -> dict[str, Any]:
    run_id = db.start_import_run(conn, "sleeper", "players")
    imported = 0
    skipped = 0
    total_seen = len(sleeper_players)
    try:
        for sleeper_id, raw in sleeper_players.items():
            payload = build_player_payload(str(sleeper_id), raw or {})
            if not payload:
                skipped += 1
                continue
            db.upsert_player(conn, payload)
            db.upsert_source_ranking(
                conn,
                {
                    "internal_player_id": payload["internal_player_id"],
                    "source_name": "sleeper",
                    "source_player_id": str(sleeper_id),
                    "overall_rank": payload.get("search_rank"),
                    "position_rank": None,
                    "adp": None,
                    "projected_points": None,
                    "tier": None,
                    "bye_week": None,
                    "raw_json": json.dumps(raw),
                },
            )
            imported += 1
        db.finish_import_run(conn, run_id, "success", imported)
        return {
            "imported_count": imported,
            "skipped_count": skipped,
            "total_seen": total_seen,
            "status": "success",
        }
    except Exception as exc:
        db.finish_import_run(conn, run_id, "error", imported, str(exc))
        raise


def build_player_payload(sleeper_id: str, raw: dict[str, Any]) -> dict[str, Any] | None:
    position = normalize_position(str(raw.get("position") or ""))
    fantasy_positions = [
        normalize_position(str(item))
        for item in (raw.get("fantasy_positions") or [])
        if normalize_position(str(item)) in FANTASY_POSITIONS
    ]
    if position not in FANTASY_POSITIONS and not fantasy_positions:
        return None

    active = bool(raw.get("active")) or str(raw.get("status") or "").lower() == "active"
    if not active and not fantasy_positions:
        return None

    first = clean(raw.get("first_name"))
    last = clean(raw.get("last_name"))
    full_name = clean(raw.get("full_name")) or " ".join(part for part in [first, last] if part).strip()
    team = normalize_team(str(raw.get("team") or ""))
    if not full_name and position == "DEF" and team:
        full_name = f"{team} Defense"
    if not full_name:
        return None

    return {
        "internal_player_id": f"sleeper_{sleeper_id}",
        "sleeper_id": sleeper_id,
        "espn_id": clean(raw.get("espn_id")),
        "fantasypros_id": None,
        "full_name": full_name,
        "first_name": first,
        "last_name": last,
        "normalized_name": normalize_name(full_name),
        "position": position or (fantasy_positions[0] if fantasy_positions else None),
        "team": team,
        "fantasy_positions": fantasy_positions,
        "active": active,
        "age": raw.get("age"),
        "years_exp": raw.get("years_exp"),
        "status": clean(raw.get("status")),
        "injury_status": clean(raw.get("injury_status")),
        "search_rank": raw.get("search_rank"),
        "source": "sleeper",
    }


def clean(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value).strip()
