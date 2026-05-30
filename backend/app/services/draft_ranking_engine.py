"""Composable best-available scoring for draft recommendations."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from .normalization import normalize_position
from .user_preferences import favorite_player_ids, get_preferences, user_tendencies_for_round



def fit_label(score: float) -> str:
    if score >= 120:
        return "Priority target"
    if score >= 80:
        return "Strong fit"
    if score >= 45:
        return "Consider"
    return "Watch list"


def score_draft_candidate(
    conn: sqlite3.Connection,
    league_id: str | None,
    item: dict[str, Any],
    desired: dict[str, int],
    counts: Counter[str],
    current_pick: int,
    teams: int = 10,
) -> dict[str, Any]:
    player = item["player"]
    consensus = item["consensus"]
    sources = item["sources"]
    position = normalize_position(player.get("position") or "")
    consensus_rank = consensus.get("consensus_rank")
    projected_points = consensus.get("projected_points_avg") or 0.0
    source_adps = [source.get("adp") for source in sources.values() if source.get("adp") is not None]
    avg_adp = sum(float(value) for value in source_adps) / len(source_adps) if source_adps else None
    value_vs_rank = (current_pick - consensus_rank) if consensus_rank is not None else 0.0
    value_vs_adp = (current_pick - avg_adp) if avg_adp is not None else 0.0
    need_gap = desired.get(position, 0) - counts.get(position, 0)
    need_bonus = 22.0 if need_gap > 0 else -6.0
    if position in {"DEF", "K"} and current_pick < 120:
        need_bonus -= 22.0
    scarcity_bonus = {"RB": 16.0, "WR": 14.0, "TE": 10.0, "QB": 7.0, "DEF": 0.0, "K": 0.0}.get(position, 0.0)
    injury_text = str(player.get("injury_status") or player.get("status") or "")
    injury_penalty = 18.0 if injury_text and injury_text.lower() not in {"healthy", "active"} else 0.0
    disagreement = consensus.get("disagreement_score") or 0.0
    disagreement_adjustment = 5.0 if disagreement >= 20 and value_vs_rank >= 8 else -3.0 if disagreement >= 20 else 0.0
    rank_component = max(0.0, 220.0 - float(consensus_rank or 220.0)) * 0.55

    position_weight = 1.0
    reach_mult = 1.0
    value_mult = 1.0
    if league_id:
        prefs = get_preferences(conn, league_id)
        position_weight = float(prefs.get("position_weights", {}).get(position, 1.0))
        reach_mult = 1.0 + float(prefs.get("reach_bias") or 0)
        value_mult = 1.0 + float(prefs.get("value_bias") or 0)
        round_no = ((current_pick - 1) // max(teams, 1)) + 1
        tendency = user_tendencies_for_round(conn, league_id, round_no, position)
        if tendency and float(tendency["reach_rate"] or 0) > 0.35:
            reach_mult += 0.08
        if tendency and float(tendency["value_pick_rate"] or 0) > 0.35:
            value_mult += 0.08

    player_id = player.get("internal_player_id")
    favorite_boost = 20.0 if league_id and player_id in favorite_player_ids(conn, league_id) else 0.0
    odds_bonus, prop_bonus, odds_reason = scoring_odds_signals(conn, player_id, player.get("team"))
    projection_bonus = sleeper_projection_bonus(conn, player_id, projected_points)

    score = (
        rank_component * position_weight
        + projected_points * 0.24
        + projection_bonus
        + value_vs_rank * 2.8 * value_mult
        + max(0.0, -value_vs_rank) * 1.4 * reach_mult
        + value_vs_adp * 1.7
        + need_bonus
        + scarcity_bonus
        + disagreement_adjustment
        + favorite_boost
        + odds_bonus
        + prop_bonus
        - injury_penalty
    )

    from .recommendations import database_reasons as full_database_reasons
    reasons = list(
        full_database_reasons(player, consensus, sources, current_pick, value_vs_rank, value_vs_adp, need_gap, injury_text)
    )
    if favorite_boost:
        reasons.insert(0, "On your favorites list.")
    if projection_bonus:
        reasons.insert(0, "Sleeper projection is above consensus average.")
    if odds_reason:
        reasons.append(odds_reason)

    result = dict(item)
    result["score"] = round(score, 2)
    result["fit"] = fit_label(score)
    result["reasons"] = reasons[:5]
    result["signals"] = {
        "favorite": favorite_boost > 0,
        "projection": projection_bonus > 0,
        "odds": odds_bonus > 0 or prop_bonus > 0,
    }
    return result


def scoring_odds_signals(
    conn: sqlite3.Connection,
    player_id: str | None,
    team: str | None,
) -> tuple[float, float, str | None]:
    if not player_id:
        return 0.0, 0.0, None
    prop_row = conn.execute(
        """
        SELECT market, line FROM player_props
        WHERE internal_player_id = ?
        ORDER BY imported_at DESC LIMIT 1
        """,
        (player_id,),
    ).fetchone()
    prop_bonus = 4.0 if prop_row else 0.0
    game_bonus = 0.0
    reason = None
    if team:
        game = conn.execute(
            """
            SELECT total FROM game_odds_snapshots
            WHERE home_team = ? OR away_team = ?
            ORDER BY imported_at DESC LIMIT 1
            """,
            (team, team),
        ).fetchone()
        if game and game["total"] and float(game["total"]) >= 47:
            game_bonus = 3.0
            reason = "High game total supports offensive upside."
    if prop_row:
        reason = f"Active prop market: {prop_row['market']} {prop_row['line']}."
    return game_bonus, prop_bonus, reason


def sleeper_projection_bonus(conn: sqlite3.Connection, player_id: str | None, baseline: float) -> float:
    if not player_id:
        return 0.0
    row = conn.execute(
        """
        SELECT projected_points FROM player_source_rankings
        WHERE internal_player_id = ? AND source_name = 'sleeper_projection'
        ORDER BY imported_at DESC LIMIT 1
        """,
        (player_id,),
    ).fetchone()
    if not row or row["projected_points"] is None:
        return 0.0
    sleeper_pts = float(row["projected_points"])
    if sleeper_pts > baseline + 8:
        return 6.0
    if sleeper_pts > baseline:
        return 3.0
    return 0.0

