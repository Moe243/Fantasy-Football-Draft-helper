"""Tendency-aware opponent picks for mock drafts."""

from __future__ import annotations

import sqlite3
from typing import Any

from .availability import drafted_player_ids
from .consensus import get_consensus_rows


def practice_drafted_player_ids(conn: sqlite3.Connection, practice_draft_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT player_id FROM practice_draft_picks WHERE practice_draft_id = ? AND player_id IS NOT NULL",
        (practice_draft_id,),
    ).fetchall()
    return {row["player_id"] for row in rows}


def choose_mock_pick(
    conn: sqlite3.Connection,
    league_id: str,
    practice_draft_id: int,
    pick_no: int,
    roster_id: int | None,
    manager_name: str | None,
) -> str:
    unavailable = drafted_player_ids(conn, league_id) | practice_drafted_player_ids(conn, practice_draft_id)
    round_no = max(1, ((pick_no - 1) // max(team_count(conn, league_id), 1)) + 1)
    tendencies = manager_tendencies(conn, league_id, roster_id, round_no)
    candidates = get_consensus_rows(conn, limit=400, current_pick=pick_no)
    best_id: str | None = None
    best_score = -999.0
    for row in candidates:
        player = row["player"]
        player_id = player["internal_player_id"]
        position = player.get("position") or ""
        if player_id in unavailable:
            continue
        if position in {"K", "DEF"} and pick_no < 120:
            continue
        consensus_rank = row["consensus"].get("consensus_rank")
        if consensus_rank is None:
            continue
        score = 220.0 - float(consensus_rank)
        pos_tendency = tendencies.get(position) or {}
        reach_rate = float(pos_tendency.get("reach_rate") or 0)
        value_rate = float(pos_tendency.get("value_pick_rate") or 0)
        delta = pick_no - float(consensus_rank)
        if reach_rate > 0.3 and delta < -6:
            score += 12.0
        if value_rate > 0.3 and delta > 8:
            score -= 10.0
        if score > best_score:
            best_score = score
            best_id = player_id
    if best_id:
        return best_id
    for row in candidates:
        player_id = row["player"]["internal_player_id"]
        if player_id not in unavailable:
            return player_id
    raise ValueError("No available players to simulate")


def manager_tendencies(
    conn: sqlite3.Connection,
    league_id: str,
    roster_id: int | None,
    round_no: int,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if roster_id is None:
        return lookup
    rows = conn.execute(
        """
        SELECT position, reach_rate, value_pick_rate
        FROM manager_draft_tendencies
        WHERE league_id = ? AND roster_id = ? AND (round = ? OR round IS NULL)
        """,
        (league_id, roster_id, round_no),
    ).fetchall()
    for row in rows:
        lookup[row["position"] or "UNK"] = dict(row)
    return lookup


def team_count(conn: sqlite3.Connection, league_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    return int(row["count"] or 10) if row else 10
