"""Opponent pick simulation for mock drafts."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from .availability import drafted_player_ids
from .consensus import get_consensus_rows
from .normalization import normalize_position
from .recommendations import desired_position_counts


def practice_drafted_player_ids(conn, practice_draft_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT player_id FROM practice_draft_picks WHERE practice_draft_id = ? AND player_id IS NOT NULL",
        (practice_draft_id,),
    ).fetchall()
    return {row["player_id"] for row in rows}


def choose_mock_pick(
    conn: sqlite3.Connection,
    league_id: str,
    practice_draft_id: int,
    pick_context: dict[str, Any],
    settings,
) -> str:
    unavailable = drafted_player_ids(conn, league_id) | practice_drafted_player_ids(conn, practice_draft_id)
    roster_id = pick_context.get("current_roster_id") or pick_context.get("original_roster_id")
    round_no = int(pick_context.get("round") or 1)
    roster_counts = opponent_roster_counts(conn, practice_draft_id, roster_id)
    desired = desired_position_counts(settings)
    candidates: list[tuple[float, str]] = []

    for row in get_consensus_rows(conn, limit=500, current_pick=int(pick_context.get("pick_no") or 1)):
        player_id = row["player"]["internal_player_id"]
        position = normalize_position(row["player"].get("position") or "")
        if player_id in unavailable:
            continue
        if position in {"K", "DEF"} and len(unavailable) < 100:
            continue
        if roster_counts.get(position, 0) >= desired.get(position, 0):
            continue
        score = base_candidate_score(conn, league_id, row, round_no, position, roster_id)
        candidates.append((score, player_id))

    if not candidates:
        for row in get_consensus_rows(conn, limit=500, current_pick=1):
            player_id = row["player"]["internal_player_id"]
            if player_id not in unavailable:
                return player_id
        raise ValueError("No available players to simulate")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def opponent_roster_counts(
    conn: sqlite3.Connection,
    practice_draft_id: int,
    roster_id: Any,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    if roster_id is None:
        return counts
    rows = conn.execute(
        """
        SELECT p.position
        FROM practice_draft_picks pp
        JOIN players p ON p.internal_player_id = pp.player_id
        WHERE pp.practice_draft_id = ? AND pp.roster_id = ? AND pp.player_id IS NOT NULL
        """,
        (practice_draft_id, roster_id),
    ).fetchall()
    for row in rows:
        counts[normalize_position(row["position"] or "UNK")] += 1
    return counts


def base_candidate_score(
    conn: sqlite3.Connection,
    league_id: str,
    row: dict[str, Any],
    round_no: int,
    position: str,
    roster_id: Any,
) -> float:
    consensus = row["consensus"]
    rank = float(consensus.get("consensus_rank") or 200)
    score = max(0.0, 220.0 - rank)
    if roster_id is not None:
        tendency = conn.execute(
            """
            SELECT reach_rate, value_pick_rate, avg_player_rank
            FROM manager_draft_tendencies
            WHERE league_id = ? AND roster_id = ? AND round = ? AND position = ?
            """,
            (league_id, roster_id, round_no, position),
        ).fetchone()
        if tendency:
            reach = float(tendency["reach_rate"] or 0)
            value_rate = float(tendency["value_pick_rate"] or 0)
            avg_rank = float(tendency["avg_player_rank"] or rank)
            if reach > 0.3 and rank > avg_rank + 6:
                score += 8.0
            if value_rate > 0.3 and rank < avg_rank - 6:
                score += 6.0
    return score
