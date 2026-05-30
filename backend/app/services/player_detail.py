"""Player search and detail aggregation."""

from __future__ import annotations

from collections import defaultdict
import json
import sqlite3
from typing import Any

from .. import db
from .consensus import get_consensus_for_player
from .player_outlook import build_player_outlook
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


def compact_recommendation_profile(
    conn: sqlite3.Connection,
    player_id: str,
    player: dict[str, Any],
    signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history = season_fantasy_history(conn, player_id)
    props_2026 = props_summary_2026(conn, player_id)
    outlook = build_player_outlook(player, history, props_2026, signals)
    market_signal = market_signal_from_props(props_2026)
    return {
        "history": history,
        "props_2026": props_2026,
        "outlook": outlook,
        "market_signal": market_signal,
    }


def season_fantasy_history(conn: sqlite3.Connection, player_id: str) -> dict[str, Any]:
    history: dict[str, Any] = {}
    for season in (2025, 2024):
        row = conn.execute(
            """
            SELECT fantasy_points, raw_json, stat_type
            FROM player_stat_lines
            WHERE internal_player_id = ? AND season = ?
              AND (week IS NULL OR week = 0)
            ORDER BY
              CASE stat_type
                WHEN 'season' THEN 0
                WHEN 'season_total' THEN 1
                WHEN 'fantasy_season' THEN 2
                ELSE 3
              END,
              id DESC
            LIMIT 1
            """,
            (player_id, season),
        ).fetchone()
        rank = season_rank(conn, player_id, season)
        if row or rank is not None:
            points = row["fantasy_points"] if row else None
            if points is None and row and row["raw_json"]:
                try:
                    payload = json.loads(row["raw_json"])
                    points = payload.get("fantasy_points") or payload.get("points")
                except json.JSONDecodeError:
                    points = None
            history[str(season)] = {
                "rank": rank,
                "fantasy_points": float(points) if points is not None else None,
            }
    return history


def season_rank(conn: sqlite3.Connection, player_id: str, season: int) -> int | None:
    row = conn.execute(
        """
        SELECT overall_rank FROM player_source_rankings
        WHERE internal_player_id = ?
          AND (source_name LIKE ? OR source_name LIKE ?)
        ORDER BY overall_rank ASC
        LIMIT 1
        """,
        (player_id, f"%{season}%", f"fantasy_{season}"),
    ).fetchone()
    if row and row["overall_rank"] is not None:
        return int(round(float(row["overall_rank"])))
    row = conn.execute(
        """
        SELECT raw_json FROM player_stat_lines
        WHERE internal_player_id = ? AND season = ?
          AND (week IS NULL OR week = 0)
        ORDER BY id DESC LIMIT 1
        """,
        (player_id, season),
    ).fetchone()
    if row and row["raw_json"]:
        try:
            payload = json.loads(row["raw_json"])
            rank = payload.get("rank") or payload.get("overall_rank") or payload.get("fantasy_rank")
            if rank is not None:
                return int(round(float(rank)))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def props_summary_2026(conn: sqlite3.Connection, player_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT market, line, over_odds, under_odds, implied_probability, season
        FROM player_props
        WHERE internal_player_id = ?
          AND (season IS NULL OR season >= 2026)
        ORDER BY imported_at DESC
        LIMIT 12
        """,
        (player_id,),
    ).fetchall()
    summaries: list[dict[str, Any]] = []
    for row in rows:
        summaries.append(
            {
                "market": row["market"],
                "line": row["line"],
                "over_odds": row["over_odds"],
                "under_odds": row["under_odds"],
                "implied_probability": row["implied_probability"],
                "season": row["season"],
            }
        )
    return summaries


def market_signal_from_props(props: list[dict[str, Any]]) -> str | None:
    if not props:
        return None
    markets = ", ".join(sorted({str(p.get("market") or "").replace("_", " ") for p in props[:4] if p.get("market")}))
    return f"Markets: {markets}." if markets else None


def props_display_summary(props: list[dict[str, Any]]) -> str:
    if not props:
        return "No 2026 props imported"
    bits: list[str] = []
    for prop in props[:4]:
        market = str(prop.get("market") or "").replace("_", " ")
        line = prop.get("line")
        if market and line is not None:
            bits.append(f"{market} {line}")
    return "; ".join(bits) if bits else "No 2026 props imported"


def history_display_line(history: dict[str, Any], season: int) -> str:
    key = str(season)
    entry = history.get(key)
    if not entry:
        return f"No {season} history imported"
    rank = entry.get("rank")
    points = entry.get("fantasy_points")
    if rank is None and points is None:
        return f"No {season} history imported"
    rank_text = f"Rank {rank}" if rank is not None else "Rank —"
    points_text = f"{points:.1f} pts" if points is not None else "— pts"
    return f"{rank_text} / {points_text}"


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
