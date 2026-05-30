"""User favorites and personal draft preferences."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db


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
    return [
        {
            "league_id": row["league_id"],
            "player_id": row["player_id"],
            "notes": row["notes"],
            "player": db.player_row_to_api(db.get_player_row(conn, row["player_id"]))
            if db.get_player_row(conn, row["player_id"])
            else {"internal_player_id": row["player_id"], "full_name": row["full_name"]},
        }
        for row in rows
    ]


def add_favorite(
    conn: sqlite3.Connection,
    league_id: str,
    player_id: str,
    notes: str | None = None,
) -> dict[str, Any]:
    if not db.get_player_row(conn, player_id):
        raise ValueError(f"Unknown player_id: {player_id}")
    conn.execute(
        """
        INSERT INTO user_favorite_players (league_id, player_id, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(league_id, player_id) DO UPDATE SET notes = excluded.notes
        """,
        (league_id, player_id, notes),
    )
    conn.commit()
    return {"favorites": list_favorites(conn, league_id)}


def remove_favorite(conn: sqlite3.Connection, league_id: str, player_id: str) -> dict[str, Any]:
    conn.execute(
        "DELETE FROM user_favorite_players WHERE league_id = ? AND player_id = ?",
        (league_id, player_id),
    )
    conn.commit()
    return {"favorites": list_favorites(conn, league_id)}


def get_draft_preferences(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM user_draft_preferences WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    if not row:
        return default_preferences(league_id)
    data = dict(row)
    data["position_weights"] = _json_dict(data.pop("position_weights_json", None))
    data["stack_preferences"] = _json_dict(data.pop("stack_preferences_json", None))
    return data


def save_draft_preferences(conn: sqlite3.Connection, league_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_draft_preferences(conn, league_id)
    reach_bias = float(payload.get("reach_bias", current.get("reach_bias", 0)))
    value_bias = float(payload.get("value_bias", current.get("value_bias", 0)))
    position_weights = payload.get("position_weights", current.get("position_weights", {}))
    stack_preferences = payload.get("stack_preferences", current.get("stack_preferences", {}))
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
            reach_bias,
            value_bias,
            json.dumps(position_weights),
            json.dumps(stack_preferences),
        ),
    )
    conn.commit()
    return get_draft_preferences(conn, league_id)


def default_preferences(league_id: str) -> dict[str, Any]:
    return {
        "league_id": league_id,
        "reach_bias": 0.0,
        "value_bias": 0.0,
        "position_weights": {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0, "DEF": 1.0, "K": 1.0},
        "stack_preferences": {},
    }


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
