"""User favorites and draft preference storage."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def list_favorites(conn: sqlite3.Connection, league_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT f.*, p.full_name, p.position, p.team
        FROM user_favorite_players f
        LEFT JOIN players p ON p.internal_player_id = f.player_id
        WHERE f.league_id = ?
        ORDER BY f.created_at DESC
        """,
        (league_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def add_favorite(conn: sqlite3.Connection, league_id: str, player_id: str, notes: str | None = None) -> dict[str, Any]:
    conn.execute(
        """
        INSERT INTO user_favorite_players (league_id, player_id, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(league_id, player_id) DO UPDATE SET notes = excluded.notes
        """,
        (league_id, player_id, notes),
    )
    conn.commit()
    return {"status": "saved", "player_id": player_id}


def remove_favorite(conn: sqlite3.Connection, league_id: str, player_id: str) -> dict[str, Any]:
    conn.execute(
        "DELETE FROM user_favorite_players WHERE league_id = ? AND player_id = ?",
        (league_id, player_id),
    )
    conn.commit()
    return {"status": "removed", "player_id": player_id}


def favorite_player_ids(conn: sqlite3.Connection, league_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT player_id FROM user_favorite_players WHERE league_id = ?",
        (league_id,),
    ).fetchall()
    return {row["player_id"] for row in rows}


def get_preferences(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM user_draft_preferences WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    if not row:
        return default_preferences(league_id)
    return preferences_from_row(row)


def save_preferences(conn: sqlite3.Connection, league_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    conn.execute(
        """
        INSERT INTO user_draft_preferences (
            league_id, reach_bias, value_bias, position_weights_json, stack_preferences_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(league_id) DO UPDATE SET
            reach_bias = excluded.reach_bias,
            value_bias = excluded.value_bias,
            position_weights_json = excluded.position_weights_json,
            stack_preferences_json = excluded.stack_preferences_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            league_id,
            float(payload.get("reach_bias") or 0),
            float(payload.get("value_bias") or 0),
            json.dumps(payload.get("position_weights") or {}),
            json.dumps(payload.get("stack_preferences") or {}),
        ),
    )
    conn.commit()
    return get_preferences(conn, league_id)


def default_preferences(league_id: str) -> dict[str, Any]:
    return {
        "league_id": league_id,
        "reach_bias": 0.0,
        "value_bias": 0.0,
        "position_weights": {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0, "DEF": 1.0, "K": 1.0},
        "stack_preferences": {},
    }


def preferences_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "league_id": row["league_id"],
        "reach_bias": float(row["reach_bias"] or 0),
        "value_bias": float(row["value_bias"] or 0),
        "position_weights": json.loads(row["position_weights_json"] or "{}"),
        "stack_preferences": json.loads(row["stack_preferences_json"] or "{}"),
        "updated_at": row["updated_at"],
    }


def user_tendencies_for_round(
    conn: sqlite3.Connection,
    league_id: str,
    round_no: int,
    position: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM user_draft_tendencies
        WHERE league_id = ? AND round = ? AND position = ?
        """,
        (league_id, round_no, position),
    ).fetchone()
