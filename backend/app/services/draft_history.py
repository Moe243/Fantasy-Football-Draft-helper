"""Simple manager tendency calculations from imported drafts."""

from __future__ import annotations

from collections import defaultdict
import sqlite3
from typing import Any

from .consensus import get_consensus_for_player


def calculate_manager_tendencies(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT p.*, m.team_name, m.display_name
        FROM league_draft_picks p
        LEFT JOIN league_managers m
            ON m.league_id = p.league_id AND m.roster_id = p.roster_id
        WHERE p.league_id = ? AND p.position IS NOT NULL
        """,
        (league_id,),
    ).fetchall()
    grouped: dict[tuple[int, int, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        roster_id = int(row["roster_id"] or 0)
        round_no = int(row["round"] or 0)
        position = row["position"] or "UNK"
        grouped[(roster_id, round_no, position)].append(row)

    conn.execute("DELETE FROM manager_draft_tendencies WHERE league_id = ?", (league_id,))
    imported = 0
    for (roster_id, round_no, position), picks in grouped.items():
        pick_numbers = [float(row["pick_no"]) for row in picks if row["pick_no"] is not None]
        rank_deltas: list[float] = []
        ranks: list[float] = []
        for row in picks:
            if not row["player_id"]:
                continue
            consensus = get_consensus_for_player(conn, row["player_id"], current_pick=int(row["pick_no"] or 1))
            if not consensus or consensus["consensus"]["consensus_rank"] is None:
                continue
            rank = float(consensus["consensus"]["consensus_rank"])
            ranks.append(rank)
            rank_deltas.append(float(row["pick_no"] or 0) - rank)
        reach_rate = rate([delta < -8 for delta in rank_deltas])
        value_pick_rate = rate([delta > 8 for delta in rank_deltas])
        manager_name = picks[0]["team_name"] or picks[0]["display_name"] or f"Roster {roster_id}"
        conn.execute(
            """
            INSERT INTO manager_draft_tendencies (
                league_id, roster_id, manager_name, round, position, pick_count,
                avg_pick_no, avg_player_rank, reach_rate, value_pick_rate, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(league_id, roster_id, round, position) DO UPDATE SET
                manager_name = excluded.manager_name,
                pick_count = excluded.pick_count,
                avg_pick_no = excluded.avg_pick_no,
                avg_player_rank = excluded.avg_player_rank,
                reach_rate = excluded.reach_rate,
                value_pick_rate = excluded.value_pick_rate,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                league_id,
                roster_id,
                manager_name,
                round_no,
                position,
                len(picks),
                avg(pick_numbers),
                avg(ranks),
                reach_rate,
                value_pick_rate,
            ),
        )
        imported += 1
    conn.commit()
    return {"rows_analyzed": len(rows), "tendencies_imported": imported}


def avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def rate(values: list[bool]) -> float | None:
    return round(sum(1 for value in values if value) / len(values), 2) if values else None
