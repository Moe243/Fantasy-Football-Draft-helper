"""Tendency-aware opponent picks for mock drafts."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import db
from ..models import LeagueSettings
from .availability import drafted_player_ids
from .consensus import get_consensus_rows
from .draft_ranking_engine import score_draft_candidate
from .recommendations import desired_position_counts


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
    settings = db.get_league_settings(conn)
    desired = desired_position_counts(settings)
    teams = team_count(conn, league_id)
    counts: dict[str, int] = {}
    candidates = get_consensus_rows(conn, limit=500, current_pick=pick_no)
    best_id: str | None = None
    best_score = -999999.0
    for row in candidates:
        player = row["player"]
        player_id = player["internal_player_id"]
        position = player.get("position") or ""
        if player_id in unavailable:
            continue
        if position in {"K", "DEF"} and pick_no < 120:
            continue
        scored = score_draft_candidate(
            conn,
            row,
            league_id=league_id,
            desired=desired,
            counts=counts,
            current_pick=pick_no,
            teams=teams,
        )
        score = float(scored["score"])
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


def team_count(conn: sqlite3.Connection, league_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    if row and row["count"]:
        return int(row["count"])
    settings: LeagueSettings = db.get_league_settings(conn)
    return int(settings.teams or 10)
