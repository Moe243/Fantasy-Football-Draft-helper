"""Composable draft ranking beyond raw consensus ADP."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from .normalization import normalize_position
from .recommendations import database_reasons, fit_label


QB_ROUND_PENALTY = 500.0


def score_draft_candidate(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    league_id: str | None,
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
    projected_points = float(consensus.get("projected_points_avg") or 0.0)
    source_adps = [
        source.get("adp")
        for source in sources.values()
        if source.get("adp") is not None
    ]
    avg_adp = sum(float(value) for value in source_adps) / len(source_adps) if source_adps else None
    value_vs_rank = (current_pick - consensus_rank) if consensus_rank is not None else 0.0
    value_vs_adp = (current_pick - avg_adp) if avg_adp is not None else 0.0
    need_gap = desired.get(position, 0) - counts.get(position, 0)
    roster_need_score = 22.0 if need_gap > 0 else -6.0
    if position in {"DEF", "K"} and current_pick < 120:
        roster_need_score -= 22.0
    scarcity_score = {"RB": 16.0, "WR": 14.0, "TE": 10.0, "QB": 7.0, "DEF": 0.0, "K": 0.0}.get(position, 0.0)
    injury_text = str(player.get("injury_status") or player.get("status") or "")
    injury_penalty = 18.0 if injury_text and injury_text.lower() not in {"healthy", "active"} else 0.0
    disagreement = consensus.get("disagreement_score") or 0.0
    disagreement_adjustment = 5.0 if disagreement >= 20 and value_vs_rank >= 8 else -3.0 if disagreement >= 20 else 0.0
    consensus_score = max(0.0, 220.0 - float(consensus_rank or 220.0)) * 0.55
    adp_value_score = value_vs_adp * 1.7
    projection_score = projected_points * 0.24
    rank_value_score = value_vs_rank * 2.8

    prefs = load_preferences(conn, league_id) if league_id else {}
    reach_bias = float(prefs.get("reach_bias") or 0.0)
    value_bias = float(prefs.get("value_bias") or 0.0)
    position_weights = prefs.get("position_weights") or {}
    position_multiplier = float(position_weights.get(position, 1.0))

    sleeper_proj = projection_bonus(conn, player["internal_player_id"], sources)
    odds_signal, market_signal_score = odds_signals(conn, player["internal_player_id"])
    favorite_boost = favorite_bonus(conn, league_id, player["internal_player_id"])
    tendency_adjustment = tendency_adjustment_score(
        conn, league_id, position, value_vs_rank, reach_bias, value_bias
    )

    round_no = max(1, ((int(current_pick) - 1) // max(teams, 1)) + 1)
    qb_round_penalty = 0.0
    if position == "QB" and round_no < 3:
        qb_round_penalty = -QB_ROUND_PENALTY

    score = (
        consensus_score * position_multiplier
        + projection_score
        + rank_value_score * (1.0 + value_bias * 0.4)
        + adp_value_score
        + roster_need_score
        + scarcity_score
        + disagreement_adjustment
        + sleeper_proj
        + market_signal_score
        + favorite_boost
        + tendency_adjustment
        + qb_round_penalty
        - injury_penalty
    )
    if value_vs_rank < -8 and reach_bias < 0:
        score += reach_bias * 25.0

    reasons = database_reasons(
        player,
        consensus,
        sources,
        current_pick,
        value_vs_rank,
        value_vs_adp,
        need_gap,
        injury_text,
    )
    if qb_round_penalty:
        reasons.insert(0, "QB suppressed before Round 3 by draft strategy.")
    if favorite_boost:
        reasons.insert(0, "Marked as one of your favorite targets.")
    if sleeper_proj >= 8:
        reasons.append("Sleeper projection is above imported consensus average.")
    if odds_signal:
        reasons.append(odds_signal)
    if tendency_adjustment > 5:
        reasons.append("Matches your historical tendency to take value at this position.")
    elif tendency_adjustment < -5:
        reasons.append("Adjusted down based on your reach/value preferences.")

    signals = {
        "consensus_score": round(consensus_score, 2),
        "adp_value_score": round(adp_value_score, 2),
        "projection_score": round(projection_score, 2),
        "roster_need_score": round(roster_need_score, 2),
        "scarcity_score": round(scarcity_score, 2),
        "market_signal_score": round(market_signal_score, 2),
        "favorite_boost": round(favorite_boost, 2),
        "tendency_adjustment": round(tendency_adjustment, 2),
        "qb_round_penalty": round(qb_round_penalty, 2),
        "rank_value_score": round(rank_value_score, 2),
        "favorite": favorite_boost > 0,
    }
    result = dict(item)
    result["score"] = round(score, 2)
    result["fit"] = fit_label(score)
    result["reasons"] = reasons[:8]
    result["signals"] = signals
    return result


def load_preferences(conn: sqlite3.Connection, league_id: str | None) -> dict[str, Any]:
    if not league_id:
        return {}
    row = conn.execute(
        "SELECT * FROM user_draft_preferences WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    if not row:
        return {}
    data = dict(row)
    if data.get("position_weights_json"):
        try:
            data["position_weights"] = json.loads(data["position_weights_json"])
        except json.JSONDecodeError:
            data["position_weights"] = {}
    return data


def favorite_bonus(conn: sqlite3.Connection, league_id: str | None, player_id: str) -> float:
    if not league_id:
        return 0.0
    row = conn.execute(
        "SELECT 1 FROM user_favorite_players WHERE league_id = ? AND player_id = ?",
        (league_id, player_id),
    ).fetchone()
    return 20.0 if row else 0.0


def projection_bonus(
    conn: sqlite3.Connection,
    player_id: str,
    sources: dict[str, dict[str, Any]],
) -> float:
    sleeper = sources.get("sleeper_projection") or {}
    proj = sleeper.get("projected_points")
    if proj is None:
        row = conn.execute(
            """
            SELECT projected_points FROM player_source_rankings
            WHERE internal_player_id = ? AND source_name = 'sleeper_projection'
            """,
            (player_id,),
        ).fetchone()
        proj = row["projected_points"] if row else None
    if proj is None:
        return 0.0
    consensus_proj = 0.0
    count = 0
    for source in sources.values():
        if source.get("projected_points") is not None:
            consensus_proj += float(source["projected_points"])
            count += 1
    if count == 0:
        return min(12.0, float(proj) * 0.04)
    delta = float(proj) - (consensus_proj / count)
    return max(-6.0, min(14.0, delta * 0.35))


def odds_signals(
    conn: sqlite3.Connection,
    player_id: str,
) -> tuple[str | None, float]:
    row = conn.execute(
        """
        SELECT market, line, implied_probability, over_odds, under_odds
        FROM player_props
        WHERE internal_player_id = ?
        ORDER BY imported_at DESC
        LIMIT 1
        """,
        (player_id,),
    ).fetchone()
    if not row:
        return None, 0.0
    implied = row["implied_probability"]
    bonus = 4.0
    message = f"Sportsbook {row['market'].replace('_', ' ')} line {row['line']}."
    if implied is not None and float(implied) < 0.45:
        bonus += 3.0
        message += " Market implies upside vs projection."
    return message, bonus


def tendency_adjustment_score(
    conn: sqlite3.Connection,
    league_id: str | None,
    position: str,
    value_vs_rank: float,
    reach_bias: float,
    value_bias: float,
) -> float:
    if not league_id:
        return 0.0
    row = conn.execute(
        """
        SELECT reach_rate, value_pick_rate FROM user_draft_tendencies
        WHERE league_id = ? AND position = ? AND round IS NULL
        LIMIT 1
        """,
        (league_id, position),
    ).fetchone()
    adjust = 0.0
    if row:
        if (row["value_pick_rate"] or 0) > 0.35 and value_vs_rank > 6:
            adjust += 6.0
        if (row["reach_rate"] or 0) > 0.35 and value_vs_rank < -6:
            adjust -= 4.0
    adjust += value_bias * 8.0
    adjust += reach_bias * (6.0 if value_vs_rank < -6 else -4.0 if value_vs_rank > 8 else 0.0)
    return adjust
