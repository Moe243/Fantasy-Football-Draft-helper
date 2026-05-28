"""JSON importers for player stats, projections, props, and news-ready data."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db
from .normalization import match_player, normalize_name, normalize_position, normalize_team


def import_stat_rows(conn: sqlite3.Connection, source_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return import_rows(conn, source_name, rows, kind="stats")


def import_prop_rows(conn: sqlite3.Connection, source_name: str, sportsbook: str | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return import_rows(conn, source_name, rows, kind="props", sportsbook=sportsbook)


def import_rows(
    conn: sqlite3.Connection,
    source_name: str,
    rows: list[dict[str, Any]],
    kind: str,
    sportsbook: str | None = None,
) -> dict[str, Any]:
    run_id = db.start_import_run(conn, source_name, kind)
    imported = skipped = matched = created = 0
    try:
        for row in rows:
            player_name = str(row.get("player_name") or row.get("name") or row.get("full_name") or "").strip()
            if not player_name:
                skipped += 1
                continue
            position = normalize_position(str(row.get("position") or ""))
            team = normalize_team(str(row.get("team") or ""))
            player = match_player(conn, player_name, position=position, team=team)
            if player:
                internal_id = player["internal_player_id"]
                matched += 1
            else:
                internal_id = f"{source_name}_{normalize_name(player_name).replace(' ', '_')}_{team.lower()}_{position.lower()}".strip("_")
                db.upsert_player(
                    conn,
                    {
                        "internal_player_id": internal_id,
                        "full_name": player_name,
                        "normalized_name": normalize_name(player_name),
                        "position": position,
                        "team": team,
                        "fantasy_positions": [position] if position else [],
                        "active": 1,
                        "source": source_name,
                    },
                )
                created += 1
            if kind == "stats":
                insert_stat(conn, internal_id, source_name, row)
            else:
                insert_prop(conn, internal_id, source_name, sportsbook, row)
            imported += 1
        db.finish_import_run(conn, run_id, "success", imported)
        return {
            "status": "success",
            "source_name": source_name,
            "imported_count": imported,
            "skipped_count": skipped,
            "matched_players": matched,
            "created_players": created,
        }
    except Exception as exc:
        db.finish_import_run(conn, run_id, "error", imported, str(exc))
        raise


def insert_stat(conn: sqlite3.Connection, player_id: str, source_name: str, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO player_stat_lines (
            internal_player_id, source_name, season, week, stat_type, games_played,
            passing_yards, passing_tds, interceptions, rushing_attempts, rushing_yards,
            rushing_tds, targets, receptions, receiving_yards, receiving_tds,
            fantasy_points, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            player_id,
            source_name,
            optional_int(row.get("season")),
            optional_int(row.get("week")),
            row.get("stat_type") or "actual",
            optional_float(row.get("games_played")),
            optional_float(row.get("passing_yards")),
            optional_float(row.get("passing_tds")),
            optional_float(row.get("interceptions")),
            optional_float(row.get("rushing_attempts")),
            optional_float(row.get("rushing_yards")),
            optional_float(row.get("rushing_tds")),
            optional_float(row.get("targets")),
            optional_float(row.get("receptions")),
            optional_float(row.get("receiving_yards")),
            optional_float(row.get("receiving_tds")),
            optional_float(row.get("fantasy_points")),
            json.dumps(row),
        ),
    )
    conn.commit()


def insert_prop(conn: sqlite3.Connection, player_id: str, source_name: str, sportsbook: str | None, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO player_props (
            internal_player_id, source_name, sportsbook, market, line, over_odds,
            under_odds, implied_probability, game_id, opponent, week, season,
            starts_at, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            player_id,
            source_name,
            sportsbook or row.get("sportsbook"),
            row.get("market"),
            optional_float(row.get("line")),
            optional_str(row.get("over_odds")),
            optional_str(row.get("under_odds")),
            optional_float(row.get("implied_probability")),
            optional_str(row.get("game_id")),
            optional_str(row.get("opponent")),
            optional_int(row.get("week")),
            optional_int(row.get("season")),
            optional_str(row.get("starts_at")),
            json.dumps(row),
        ),
    )
    conn.commit()


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
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)
