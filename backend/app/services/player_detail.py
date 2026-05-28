"""Player search and detail aggregation."""

from __future__ import annotations

from collections import defaultdict
import sqlite3
from typing import Any

from .. import db
from .consensus import get_consensus_for_player
from .props_analysis import analyze_props


def search_players(
    conn: sqlite3.Connection,
    search: str | None = None,
    position: str | None = None,
    team: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    number: str | None = None,
    active: int | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
) -> dict[str, Any]:
    rows = db.query_player_rows(
        conn,
        position=position,
        search=search,
        team=team,
        age_min=age_min,
        age_max=age_max,
        jersey_number=number,
        active=active,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    players: list[dict[str, Any]] = []
    for row in rows:
        player = db.player_row_to_api(row)
        consensus = get_consensus_for_player(conn, player["internal_player_id"])
        players.append(
            {
                "internal_player_id": player["internal_player_id"],
                "full_name": player["full_name"],
                "position": player["position"],
                "team": player["team"],
                "age": player["age"],
                "jersey_number": player["jersey_number"],
                "injury_status": player["injury_status"],
                "active": player["active"],
                "consensus_rank": consensus["consensus"]["consensus_rank"] if consensus else None,
                "projected_points_avg": consensus["consensus"]["projected_points_avg"] if consensus else None,
                "source_count": consensus["consensus"]["source_count"] if consensus else 0,
            }
        )
    total = db.count_player_search(
        conn,
        position=position,
        search=search,
        team=team,
        age_min=age_min,
        age_max=age_max,
        jersey_number=number,
        active=active,
    )
    return {"players": players, "total": total, "limit": limit, "offset": offset}


def player_detail(conn: sqlite3.Connection, player_id: str) -> dict[str, Any]:
    row = db.get_player_row(conn, player_id)
    if not row:
        raise ValueError(f"Unknown player_id: {player_id}")
    player = db.player_row_to_api(row)
    consensus = get_consensus_for_player(conn, player_id)
    rankings = rankings_by_source(conn, player_id)
    stats = stats_by_type(conn, player_id)
    props = props_for_player(conn, player_id)
    news = news_for_player(conn, player_id)
    notes = insight_notes(consensus, rankings, props, player)
    return {
        "player": player,
        "rankings": rankings,
        "consensus": consensus["consensus"] if consensus else None,
        "stats": stats,
        "props": props,
        "props_analysis": analyze_props(props),
        "news": news,
        "notes": notes,
    }


def rankings_by_source(conn: sqlite3.Connection, player_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM player_source_rankings WHERE internal_player_id = ? ORDER BY source_name",
        (player_id,),
    ).fetchall()
    return {
        row["source_name"]: {
            "source_player_id": row["source_player_id"],
            "overall_rank": row["overall_rank"],
            "position_rank": row["position_rank"],
            "adp": row["adp"],
            "projected_points": row["projected_points"],
            "tier": row["tier"],
            "bye_week": row["bye_week"],
            "imported_at": row["imported_at"],
        }
        for row in rows
    }


def stats_by_type(conn: sqlite3.Connection, player_id: str) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        "SELECT * FROM player_stat_lines WHERE internal_player_id = ? ORDER BY season DESC, week DESC",
        (player_id,),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["stat_type"]].append(dict(row))
    return dict(grouped)


def props_for_player(conn: sqlite3.Connection, player_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM player_props WHERE internal_player_id = ? ORDER BY season DESC, week DESC, market, sportsbook",
            (player_id,),
        ).fetchall()
    ]


def news_for_player(conn: sqlite3.Connection, player_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM player_news WHERE internal_player_id = ? ORDER BY published_at DESC, imported_at DESC",
            (player_id,),
        ).fetchall()
    ]


def insight_notes(
    consensus: dict[str, Any] | None,
    rankings: dict[str, dict[str, Any]],
    props: list[dict[str, Any]],
    player: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if consensus and consensus["consensus"].get("disagreement_score", 0) >= 20:
        notes.append("Sources disagree meaningfully on this player.")
    if "espn" in rankings and "fantasypros" in rankings:
        espn = rankings["espn"].get("overall_rank")
        fp = rankings["fantasypros"].get("overall_rank")
        if espn is not None and fp is not None and abs(float(espn) - float(fp)) >= 8:
            lower = "ESPN" if float(espn) > float(fp) else "FantasyPros"
            higher = "FantasyPros" if lower == "ESPN" else "ESPN"
            notes.append(f"{lower} is lower on this player than {higher}.")
    if player.get("injury_status") and str(player["injury_status"]).lower() not in {"healthy", "active"}:
        notes.append("Injury status should be monitored.")
    prop_analysis = analyze_props(props)
    for item in prop_analysis[:2]:
        notes.extend(item["notes"][:1])
    return notes
