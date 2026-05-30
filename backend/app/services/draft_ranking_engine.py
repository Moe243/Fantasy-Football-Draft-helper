"""Composable draft ranking beyond raw consensus ADP."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from .recommendations import database_reasons, desired_position_counts, fit_label
from .normalization import normalize_position


def score_draft_candidate(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    league_id: str | None,
    desired: dict[str, int],
    counts: Counter[str],
    current_pick: int,
) -> dict[str, Any]:
    player = item["player"]
    consensus = item["consensus"]
    sources = item["sources"]
    position = normalize_position(player.get("position") or "")
    consensus_rank = consensus.get("consensus_rank")
    projected_points = consensus.get("projected_points_avg") or 0.0
    source_adps = [
        source.get("adp")
        for source in sources.values()
        if source.get("adp") is not None
    ]
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

    prefs = load_preferences(conn, league_id) if league_id else {}
    reach_bias = float(prefs.get("reach_bias") or 0.0)
    value_bias = float(prefs.get("value_bias") or 0.0)
    position_weights = prefs.get("position_weights") or {}
    position_multiplier = float(position_weights.get(position, 1.0))

    sleeper_proj = projection_bonus(conn, player["internal_player_id"], sources)
    odds_signal, prop_bonus = odds_signals(conn, player["internal_player_id"], team=player.get("team"))
    favorite_boost = favorite_bonus(conn, league_id, player["internal_player_id"])
    tendency_adjust = tendency_adjustment(conn, league_id, position, value_vs_rank, reach_bias, value_bias)

    score = (
        rank_component * position_multiplier
        + projected_points * 0.24
        + value_vs_rank * (2.8 + value_bias * 4.0)
        + value_vs_adp * 1.7
        + need_bonus
        + scarcity_bonus
        + disagreement_adjustment
        + sleeper_proj
        + prop_bonus
        + favorite_boost
        + tendency_adjust
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
    if favorite_boost:
        reasons.insert(0, "Marked as one of your favorite targets.")
    if sleeper_proj >= 8:
        reasons.append("Sleeper projection is above imported consensus average.")
    if odds_signal:
        reasons.append(odds_signal)
    if tendency_adjust > 5:
        reasons.append("Matches your historical tendency to take value at this position.")
    elif tendency_adjust < -5:
        reasons.append("Adjusted down based on your reach/value preferences.")

    signals = {
        "projection": round(projected_points, 2),
        "adp": avg_adp,
        "odds": prop_bonus,
        "favorite": favorite_boost > 0,
        "tendency": round(tendency_adjust, 2),
        "sleeper_projection": sleeper_proj,
    }
    result = dict(item)
    result["score"] = round(score, 2)
    result["fit"] = fit_label(score)
    result["reasons"] = reasons[:6]
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
    team: str | None,
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


def tendency_adjustment(
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
