"""Personal draft tendency model for the user's team."""

from __future__ import annotations

from collections import defaultdict
import sqlite3
from typing import Any

from .consensus import get_consensus_for_player
from .draft_history import rate, avg


def calculate_user_tendencies(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    my_roster = conn.execute(
        "SELECT roster_id FROM league_managers WHERE league_id = ? AND is_me = 1 LIMIT 1",
        (league_id,),
    ).fetchone()
    roster_id = int(my_roster["roster_id"]) if my_roster and my_roster["roster_id"] is not None else None
    query = """
        SELECT p.* FROM league_draft_picks p
        WHERE p.league_id = ? AND p.position IS NOT NULL
    """
    params: list[Any] = [league_id]
    if roster_id is not None:
        query += " AND p.roster_id = ?"
        params.append(roster_id)
    rows = conn.execute(query, params).fetchall()
    if not rows:
        practice_rows = conn.execute(
            """
            SELECT pp.pick_no, pp.round, pp.player_id, pl.position
            FROM practice_draft_picks pp
            JOIN practice_drafts pd ON pd.id = pp.practice_draft_id
            JOIN players pl ON pl.internal_player_id = pp.player_id
            WHERE pd.league_id = ? AND pd.status = 'active' AND pp.source = 'user'
            """,
            (league_id,),
        ).fetchall()
        rows = practice_rows

    grouped: dict[tuple[int | None, str], list] = defaultdict(list)
    for row in rows:
        round_no = int(row["round"] or 0) or None
        position = row["position"] or "UNK"
        grouped[(round_no, position)].append(row)

    conn.execute("DELETE FROM user_draft_tendencies WHERE league_id = ?", (league_id,))
    imported = 0
    position_deltas: dict[str, list[float]] = defaultdict(list)
    for (_round_no, position), picks in grouped.items():
        rank_deltas: list[float] = []
        for row in picks:
            if not row["player_id"]:
                continue
            consensus = get_consensus_for_player(conn, row["player_id"], current_pick=int(row["pick_no"] or 1))
            if not consensus or consensus["consensus"]["consensus_rank"] is None:
                continue
            rank = float(consensus["consensus"]["consensus_rank"])
            delta = float(row["pick_no"] or 0) - rank
            rank_deltas.append(delta)
            position_deltas[position].append(delta)
        reach_rate = rate([delta < -8 for delta in rank_deltas])
        value_pick_rate = rate([delta > 8 for delta in rank_deltas])
        conn.execute(
            """
            INSERT INTO user_draft_tendencies (
                league_id, round, position, pick_count, reach_rate, value_pick_rate, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (league_id, _round_no, position, len(picks), reach_rate, value_pick_rate),
        )
        imported += 1

    for position, deltas in position_deltas.items():
        reach_rate = rate([delta < -8 for delta in deltas])
        value_pick_rate = rate([delta > 8 for delta in deltas])
        conn.execute(
            """
            INSERT INTO user_draft_tendencies (
                league_id, round, position, pick_count, reach_rate, value_pick_rate, updated_at
            )
            VALUES (?, NULL, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(league_id, round, position) DO UPDATE SET
                pick_count = excluded.pick_count,
                reach_rate = excluded.reach_rate,
                value_pick_rate = excluded.value_pick_rate,
                updated_at = CURRENT_TIMESTAMP
            """,
            (league_id, position, len(deltas), reach_rate, value_pick_rate),
        )
        imported += 1
    conn.commit()
    return {"rows_analyzed": len(rows), "tendencies_imported": imported}
