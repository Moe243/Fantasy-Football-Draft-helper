"""Consensus ranking calculations across imported sources."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import db
from .normalization import normalize_position


def get_consensus_rows(
    conn: sqlite3.Connection,
    position: str | None = None,
    limit: int = 100,
    current_pick: int = 1,
    include_player_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if position:
        clauses.append("p.position = ?")
        params.append(normalize_position(position))
    if include_player_ids:
        placeholders = ",".join("?" for _ in include_player_ids)
        clauses.append(f"p.internal_player_id IN ({placeholders})")
        params.extend(sorted(include_player_ids))
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
            p.*,
            r.source_name,
            r.source_player_id,
            r.overall_rank,
            r.position_rank,
            r.adp,
            r.projected_points,
            r.tier,
            r.bye_week,
            r.imported_at
        FROM players p
        LEFT JOIN player_source_rankings r
            ON r.internal_player_id = p.internal_player_id
        {where}
        ORDER BY COALESCE(p.search_rank, 999999), p.full_name
        """,
        params,
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        player_id = row["internal_player_id"]
        if player_id not in grouped:
            grouped[player_id] = {
                "player": db.player_row_to_api(row),
                "ranking_rows": [],
            }
        if row["source_name"]:
            grouped[player_id]["ranking_rows"].append(row)

    consensus_rows = [
        build_consensus_row(item["player"], item["ranking_rows"], current_pick)
        for item in grouped.values()
    ]
    consensus_rows.sort(
        key=lambda item: (
            item["consensus"]["consensus_rank"] is None,
            item["consensus"]["consensus_rank"] or 999999,
            item["player"]["full_name"],
        )
    )
    return consensus_rows[:limit]


def get_consensus_for_player(
    conn: sqlite3.Connection,
    internal_player_id: str,
    current_pick: int = 1,
) -> dict[str, Any] | None:
    rows = get_consensus_rows(
        conn,
        limit=1,
        current_pick=current_pick,
        include_player_ids={internal_player_id},
    )
    return rows[0] if rows else None


def build_consensus_row(
    player: dict[str, Any],
    ranking_rows: list[sqlite3.Row],
    current_pick: int,
) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    rank_values: list[float] = []
    projected_points: list[float] = []
    for row in ranking_rows:
        source_name = row["source_name"]
        source = {
            "source_player_id": row["source_player_id"],
            "overall_rank": row["overall_rank"],
            "position_rank": row["position_rank"],
            "adp": row["adp"],
            "projected_points": row["projected_points"],
            "tier": row["tier"],
            "bye_week": row["bye_week"],
            "imported_at": row["imported_at"],
        }
        sources[source_name] = source
        rank_value = first_number(row["overall_rank"], row["adp"])
        if rank_value is not None:
            rank_values.append(rank_value)
        if row["projected_points"] is not None:
            projected_points.append(float(row["projected_points"]))

    consensus_rank = avg(rank_values)
    best_source_rank = min(rank_values) if rank_values else None
    worst_source_rank = max(rank_values) if rank_values else None
    rank_spread = (worst_source_rank - best_source_rank) if len(rank_values) > 1 else 0
    projected_points_avg = avg(projected_points)
    value_vs_current_pick = consensus_rank - current_pick if consensus_rank is not None else None
    label = label_value(value_vs_current_pick, rank_spread)

    return {
        "player": player,
        "sources": sources,
        "consensus": {
            "consensus_rank": round(consensus_rank, 2) if consensus_rank is not None else None,
            "best_source_rank": round(best_source_rank, 2) if best_source_rank is not None else None,
            "worst_source_rank": round(worst_source_rank, 2) if worst_source_rank is not None else None,
            "rank_spread": round(rank_spread, 2) if rank_spread is not None else 0,
            "source_count": len(rank_values),
            "projected_points_avg": round(projected_points_avg, 2) if projected_points_avg is not None else None,
            "sleeper_adp": nested_value(sources, "sleeper", "adp"),
            "sleeper_rank": nested_value(sources, "sleeper", "overall_rank"),
            "fantasypros_rank": nested_value(sources, "fantasypros", "overall_rank"),
            "espn_rank": nested_value(sources, "espn", "overall_rank"),
            "value_vs_current_pick": round(value_vs_current_pick, 2) if value_vs_current_pick is not None else None,
            "disagreement_score": round(rank_spread, 2) if rank_spread is not None else 0,
            "label": label,
        },
    }


def first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def nested_value(data: dict[str, dict[str, Any]], source: str, key: str) -> Any:
    return data.get(source, {}).get(key)


def label_value(value_vs_current_pick: float | None, rank_spread: float | None) -> str:
    if rank_spread is not None and rank_spread >= 20:
        return "High Disagreement"
    if value_vs_current_pick is None:
        return "No Consensus"
    if value_vs_current_pick <= -8:
        return "Undervalued"
    if value_vs_current_pick >= 8:
        return "Overpriced"
    return "Fair Price"
