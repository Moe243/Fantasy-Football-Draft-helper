"""Rough future-pick availability estimates."""

from __future__ import annotations

import sqlite3
from typing import Any

from .consensus import get_consensus_rows


def estimate_availability(
    conn: sqlite3.Connection,
    league_id: str,
    pick_no: int,
    limit: int = 8,
) -> dict[str, Any]:
    drafted = drafted_player_ids(conn, league_id)
    candidates = [
        row for row in get_consensus_rows(conn, limit=700, current_pick=pick_no)
        if row["player"]["internal_player_id"] not in drafted
    ]
    candidates.sort(key=lambda row: row["consensus"]["consensus_rank"] or row["player"].get("search_rank") or 999999)
    picks_remaining = max(0, pick_no - current_pick_no(conn, league_id))
    likely: list[dict[str, Any]] = []
    for index, row in enumerate(candidates):
        rank = row["consensus"]["consensus_rank"] or row["player"].get("search_rank") or 999
        survival_margin = float(rank) - picks_remaining
        probability = max(0.05, min(0.95, 0.5 + survival_margin / 60))
        if index < picks_remaining:
            probability *= 0.55
        likely.append(
            {
                "player": row["player"],
                "consensus": row["consensus"],
                "sources": row["sources"],
                "availability_probability": round(probability, 2),
                "reason": f"Projected to last because consensus rank is {round(float(rank), 1)} and {picks_remaining} picks remain before your pick.",
            }
        )
    likely.sort(key=lambda item: item["availability_probability"], reverse=True)
    return {"target_pick": pick_no, "likely_available": likely[:limit]}


def drafted_player_ids(conn: sqlite3.Connection, league_id: str) -> set[str]:
    draft_id = latest_draft_id(conn, league_id)
    if draft_id:
        rows = conn.execute(
            "SELECT player_id FROM league_draft_picks WHERE league_id = ? AND draft_id = ? AND player_id IS NOT NULL",
            (league_id, draft_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT player_id FROM league_draft_picks WHERE league_id = ? AND player_id IS NOT NULL",
            (league_id,),
        ).fetchall()
    practice = conn.execute(
        """
        SELECT p.player_id
        FROM practice_draft_picks p
        JOIN practice_drafts d ON d.id = p.practice_draft_id
        WHERE d.league_id = ? AND p.player_id IS NOT NULL AND d.status = 'active'
        """,
        (league_id,),
    ).fetchall()
    keepers = conn.execute("SELECT player_id FROM keepers").fetchall()
    return {row["player_id"] for row in rows + practice + keepers if row["player_id"]}


def current_pick_no(conn: sqlite3.Connection, league_id: str) -> int:
    draft_id = latest_draft_id(conn, league_id)
    if draft_id:
        row = conn.execute(
            "SELECT MAX(pick_no) AS max_pick FROM league_draft_picks WHERE league_id = ? AND draft_id = ?",
            (league_id, draft_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT MAX(pick_no) AS max_pick FROM league_draft_picks WHERE league_id = ?",
            (league_id,),
        ).fetchone()
    practice = conn.execute(
        "SELECT current_pick FROM practice_drafts WHERE league_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    base = int(row["max_pick"] or 0) + 1
    if practice:
        return max(base, int(practice["current_pick"] or 1))
    return base


def latest_draft_id(conn: sqlite3.Connection, league_id: str) -> str | None:
    row = conn.execute(
        "SELECT draft_id FROM league_drafts WHERE league_id = ? ORDER BY season DESC, id DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    return row["draft_id"] if row else None
