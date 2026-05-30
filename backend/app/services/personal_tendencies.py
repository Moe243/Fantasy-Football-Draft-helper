"""Calculate personal draft tendencies from imported history."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from .consensus import get_consensus_for_player
from .draft_history import rate


def calculate_user_tendencies(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    my_roster = conn.execute(
        "SELECT roster_id FROM league_managers WHERE league_id = ? AND is_me = 1 LIMIT 1",
        (league_id,),
    ).fetchone()
    roster_id = my_roster["roster_id"] if my_roster else None
    rows: list[sqlite3.Row] = []
    if roster_id is not None:
        rows = conn.execute(
            """
            SELECT pick_no, round, position, player_id
            FROM league_draft_picks
            WHERE league_id = ? AND roster_id = ? AND player_id IS NOT NULL
            """,
            (league_id, roster_id),
        ).fetchall()
    conn.execute("DELETE FROM user_draft_tendencies WHERE league_id = ?", (league_id,))
    grouped: dict[tuple[int, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["round"] or 0), row["position"] or "UNK")].append(row)

    imported = 0
    for (round_no, position), picks in grouped.items():
        rank_deltas: list[float] = []
        for row in picks:
            consensus = get_consensus_for_player(conn, row["player_id"], current_pick=int(row["pick_no"] or 1))
            if not consensus or consensus["consensus"]["consensus_rank"] is None:
                continue
            rank = float(consensus["consensus"]["consensus_rank"])
            rank_deltas.append(float(row["pick_no"] or 0) - rank)
        conn.execute(
            """
            INSERT INTO user_draft_tendencies (
                league_id, round, position, pick_count, reach_rate, value_pick_rate, avg_round_taken, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                league_id,
                round_no,
                position,
                len(picks),
                rate([delta < -8 for delta in rank_deltas]),
                rate([delta > 8 for delta in rank_deltas]),
                float(round_no),
            ),
        )
        imported += 1
    conn.commit()
    return {"tendencies_imported": imported, "picks_analyzed": len(rows)}
