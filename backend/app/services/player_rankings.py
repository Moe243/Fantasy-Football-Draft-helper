"""Player and draft-board ranking payloads for the comparison UI."""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import db
from ..models import DraftPick, Keeper, LeagueSettings
from .recommendations import current_pick_number, database_draft_recommendations

DISPLAY_SOURCES = ("sleeper", "espn", "fantasypros")


def get_player_rankings(
    conn: sqlite3.Connection,
    player_id: str,
    current_pick: int = 1,
) -> dict[str, Any]:
    row = db.get_player_row(conn, player_id)
    if not row:
        raise ValueError(f"Unknown player_id: {player_id}")

    ranking_rows = conn.execute(
        """
        SELECT source_name, source_player_id, overall_rank, position_rank, adp,
               projected_points, tier, bye_week, imported_at
        FROM player_source_rankings
        WHERE internal_player_id = ?
        ORDER BY source_name
        """,
        (player_id,),
    ).fetchall()

    stat_rows = conn.execute(
        """
        SELECT source_name, season, week, stat_type, fantasy_points, imported_at
        FROM player_stat_lines
        WHERE internal_player_id = ? AND stat_type = 'actual'
        ORDER BY season DESC, week DESC
        LIMIT 24
        """,
        (player_id,),
    ).fetchall()

    sources = [ranking_row_to_source(row) for row in ranking_rows]
    consensus = build_consensus_payload(sources, current_pick)
    message = None
    if not sources:
        message = "No rankings imported yet"

    return {
        "player_id": player_id,
        "sources": sources,
        "consensus": consensus,
        "actual_stats": [dict(row) for row in stat_rows],
        "message": message,
    }


def get_draft_board_rankings(
    conn: sqlite3.Connection,
    settings: LeagueSettings,
    keepers: list[Keeper],
    picks: list[DraftPick],
    *,
    limit: int = 12,
    manager: str = "me",
    position: str | None = None,
    search: str | None = None,
    hide_drafted: bool = True,
    hide_keepers: bool = True,
    current_pick_override: int | None = None,
) -> dict[str, Any]:
    current_pick = current_pick_override or current_pick_number(picks, keepers)
    if not db.has_database_players(conn):
        return {"current_pick": current_pick, "players": []}

    recs = database_draft_recommendations(
        conn,
        settings,
        keepers,
        picks,
        limit=limit,
        manager=manager,
        position=position,
        search=search,
        hide_drafted=hide_drafted,
        hide_keepers=hide_keepers,
        current_pick_override=current_pick,
    )
    players: list[dict[str, Any]] = []
    for item in recs:
        player_id = item["player"]["internal_player_id"]
        try:
            payload = get_player_rankings(conn, player_id, current_pick=current_pick)
        except ValueError:
            continue
        players.append(payload)
    return {"current_pick": current_pick, "players": players}


def ranking_row_to_source(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source_name": row["source_name"],
        "overall_rank": row["overall_rank"],
        "position_rank": row["position_rank"],
        "adp": row["adp"],
        "projected_points": row["projected_points"],
        "tier": row["tier"],
        "bye_week": row["bye_week"],
    }


def build_consensus_payload(sources: list[dict[str, Any]], current_pick: int) -> dict[str, Any]:
    rank_values: list[float] = []
    adp_values: list[float] = []
    for source in sources:
        rank = first_number(source.get("overall_rank"), source.get("adp"))
        if rank is not None:
            rank_values.append(rank)
        if source.get("adp") is not None:
            try:
                adp_values.append(float(source["adp"]))
            except (TypeError, ValueError):
                pass

    avg_rank = avg(rank_values)
    avg_adp = avg(adp_values)
    rank_spread = (max(rank_values) - min(rank_values)) if len(rank_values) > 1 else 0.0
    source_count = len(rank_values)

    return {
        "avg_rank": round(avg_rank, 2) if avg_rank is not None else None,
        "avg_adp": round(avg_adp, 2) if avg_adp is not None else None,
        "source_count": source_count,
        "rank_spread": round(rank_spread, 2),
        "label": consensus_label(source_count, rank_spread, avg_rank, current_pick),
    }


def consensus_label(
    source_count: int,
    rank_spread: float,
    avg_rank: float | None,
    current_pick: int,
) -> str:
    if source_count < 2:
        return "Not Enough Sources"
    if rank_spread > 3:
        return "Split Opinions"
    if avg_rank is not None and avg_rank < current_pick:
        return "Strong Value"
    return "Fair Value"


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
