"""Draft, keeper, waiver, and chat recommendation logic."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import re
import sqlite3
from typing import Any

from ..models import DraftPick, Keeper, LeagueSettings, Player, Recommendation
from ..sample_data import SAMPLE_PLAYERS, players_by_id
from .consensus import get_consensus_rows
from .normalization import normalize_name, normalize_position


FANTASY_POSITIONS = ("QB", "RB", "WR", "TE", "DEF", "K")


def desired_position_counts(settings: LeagueSettings) -> dict[str, int]:
    slots = settings.roster_slots
    flex = int(slots.get("FLEX", 0))
    return {
        "QB": int(slots.get("QB", 1)),
        "RB": int(slots.get("RB", 2)) + max(1, flex),
        "WR": int(slots.get("WR", 2)) + max(1, flex),
        "TE": int(slots.get("TE", 1)),
        "DEF": int(slots.get("DEF", 1)),
        "K": int(slots.get("K", 1)),
    }


def available_players(
    players: list[Player],
    keepers: list[Keeper],
    picks: list[DraftPick],
) -> list[Player]:
    unavailable = {keeper.player_id for keeper in keepers}
    unavailable.update(pick.player_id for pick in picks)
    return [player for player in players if player.id not in unavailable]


def current_pick_number(picks: list[DraftPick], keepers: list[Keeper]) -> int:
    selected = [pick.pick_no for pick in picks]
    for keeper in keepers:
        pick_no = keeper.pick_no if hasattr(keeper, "pick_no") else keeper.get("pick_no")
        if pick_no:
            selected.append(int(pick_no))
    return max(selected, default=0) + 1


def replacement_baselines(players: list[Player], settings: LeagueSettings) -> dict[str, float]:
    baselines: dict[str, float] = {}
    needs = desired_position_counts(settings)
    for position in FANTASY_POSITIONS:
        ranked = sorted(
            [player.projected_points for player in players if player.position == position],
            reverse=True,
        )
        depth_index = min(max(settings.teams * needs.get(position, 1) - 1, 0), len(ranked) - 1)
        baselines[position] = ranked[depth_index] if ranked else 0.0
    return baselines


def roster_counts(picks: list[DraftPick], manager: str = "me") -> Counter[str]:
    by_id = players_by_id()
    counts: Counter[str] = Counter()
    for pick in picks:
        if pick.manager.lower() == manager.lower() and pick.player_id in by_id:
            counts[by_id[pick.player_id].position] += 1
    return counts


def database_roster_counts(
    conn: sqlite3.Connection,
    picks: list[DraftPick],
    manager: str = "me",
) -> Counter[str]:
    counts: Counter[str] = Counter()
    player_ids = [pick.player_id for pick in picks if pick.manager.lower() == manager.lower()]
    if not player_ids:
        return counts
    placeholders = ",".join("?" for _ in player_ids)
    rows = conn.execute(
        f"SELECT internal_player_id, position FROM players WHERE internal_player_id IN ({placeholders})",
        player_ids,
    ).fetchall()
    by_id = {row["internal_player_id"]: row["position"] for row in rows}
    for pick in picks:
        if pick.manager.lower() == manager.lower() and pick.player_id in by_id:
            counts[by_id[pick.player_id]] += 1
    return counts


def score_player(
    player: Player,
    settings: LeagueSettings,
    picks: list[DraftPick],
    baselines: dict[str, float],
    pick_number: int,
    manager: str = "me",
) -> tuple[float, list[str], str]:
    desired = desired_position_counts(settings)
    counts = roster_counts(picks, manager=manager)
    vbd = max(0.0, player.projected_points - baselines.get(player.position, 0.0))
    adp_delta = max(-18.0, min(30.0, pick_number - player.adp))
    trend = player.trend_score
    usage = max(player.snap_share * 6, player.target_share * 22, player.carry_share * 14)
    need_gap = desired.get(player.position, 0) - counts.get(player.position, 0)
    need_bonus = 18.0 if need_gap > 0 else -5.0
    if player.position in {"K", "DEF"} and pick_number < 120:
        need_bonus -= 20.0
    injury_penalty = 16.0 if player.injury_status.lower() not in {"healthy", ""} else 0.0

    score = (vbd * 1.15) + (adp_delta * 0.8) + (trend * 3.1) + usage + need_bonus - injury_penalty

    reasons: list[str] = []
    if vbd >= 40:
        reasons.append("Major value above replacement at the position.")
    elif vbd >= 20:
        reasons.append("Solid value above replacement.")
    if adp_delta > 6:
        reasons.append(f"Has slipped about {round(adp_delta)} picks past ADP.")
    elif adp_delta < -10:
        reasons.append("Likely available later based on ADP.")
    if need_gap > 0:
        reasons.append(f"Fills a current {player.position} roster need.")
    if trend >= 7.5:
        reasons.append("Trend score is rising from usage, role, or market signals.")
    if player.injury_status.lower() not in {"healthy", ""}:
        reasons.append(f"Injury status: {player.injury_status}.")
    if player.odds_signal and player.odds_signal != "Neutral":
        reasons.append(player.odds_signal + ".")
    if player.notes:
        reasons.append(player.notes)

    if score >= 120:
        fit = "Priority target"
    elif score >= 80:
        fit = "Strong fit"
    elif score >= 45:
        fit = "Consider"
    else:
        fit = "Watch list"
    return score, reasons[:5], fit


def draft_recommendations(
    settings: LeagueSettings,
    keepers: list[Keeper],
    picks: list[DraftPick],
    limit: int = 12,
    manager: str = "me",
    players: list[Player] | None = None,
) -> list[Recommendation]:
    pool = players or SAMPLE_PLAYERS
    candidates = available_players(pool, keepers, picks)
    baselines = replacement_baselines(pool, settings)
    pick_number = current_pick_number(picks, keepers)
    recommendations: list[Recommendation] = []
    for player in candidates:
        score, reasons, fit = score_player(player, settings, picks, baselines, pick_number, manager=manager)
        recommendations.append(Recommendation(player=player, score=score, reasons=reasons, fit=fit))
    return sorted(recommendations, key=lambda rec: rec.score, reverse=True)[:limit]


def database_draft_recommendations(
    conn: sqlite3.Connection,
    settings: LeagueSettings,
    keepers: list[Keeper],
    picks: list[DraftPick],
    limit: int = 30,
    manager: str = "me",
    position: str | None = None,
    search: str | None = None,
    hide_drafted: bool = True,
    hide_keepers: bool = True,
    current_pick_override: int | None = None,
    league_id: str | None = None,
) -> list[dict[str, Any]]:
    from .draft_ranking_engine import score_draft_candidate
    from .player_detail import compact_recommendation_profile

    current_pick = current_pick_override or current_pick_number(picks, keepers)
    filter_position = None if not position or position.upper() == "ALL" else position
    consensus_rows = get_consensus_rows(
        conn,
        position=filter_position,
        limit=800,
        current_pick=current_pick,
    )
    drafted_ids = {pick.player_id for pick in picks}
    keeper_ids = set()
    for keeper in keepers:
        if isinstance(keeper, dict):
            player = keeper.get("player_id") or (keeper.get("player") or {}).get("internal_player_id")
            if player:
                keeper_ids.add(player)
        else:
            keeper_ids.add(keeper.player_id)
    normalized_search = normalize_name(search or "")
    filtered: list[dict[str, Any]] = []
    for row in consensus_rows:
        player = row["player"]
        if hide_drafted and player["internal_player_id"] in drafted_ids:
            continue
        if hide_keepers and player["internal_player_id"] in keeper_ids:
            continue
        if normalized_search and normalized_search not in normalize_name(player["full_name"]):
            continue
        filtered.append(row)

    counts = database_roster_counts(conn, picks, manager=manager)
    desired = desired_position_counts(settings)
    teams = int(settings.teams or 10)
    from .draft_ranking_engine import score_draft_candidate
    from .player_detail import compact_recommendation_profile

    scored: list[dict[str, Any]] = []
    for item in filtered:
        ranked = score_draft_candidate(
            conn,
            item,
            league_id=league_id,
            desired=desired,
            counts=counts,
            current_pick=current_pick,
            teams=teams,
        )
        player = ranked["player"]
        profile = compact_recommendation_profile(
            conn,
            player["internal_player_id"],
            player,
            ranked.get("signals"),
        )
        ranked["history"] = profile["history"]
        ranked["props_2026"] = profile["props_2026"]
        ranked["outlook"] = profile["outlook"]
        ranked["market_signal"] = profile["market_signal"]
        scored.append(ranked)
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def score_database_player(
    item: dict[str, Any],
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
    score = (
        rank_component
        + projected_points * 0.24
        + value_vs_rank * 2.8
        + value_vs_adp * 1.7
        + need_bonus
        + scarcity_bonus
        + disagreement_adjustment
        - injury_penalty
    )
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
    item = dict(item)
    item["score"] = round(score, 2)
    item["fit"] = fit_label(score)
    item["reasons"] = reasons
    return item


def database_reasons(
    player: dict[str, Any],
    consensus: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    current_pick: int,
    value_vs_rank: float,
    value_vs_adp: float,
    need_gap: int,
    injury_text: str,
) -> list[str]:
    reasons: list[str] = []
    label = consensus.get("label")
    if label == "Undervalued" and value_vs_rank >= 8:
        reasons.append(f"He is available {round(value_vs_rank)} picks after his consensus rank.")
    elif label == "Overpriced" and value_vs_rank <= -8:
        reasons.append(f"He is going {abs(round(value_vs_rank))} picks earlier than consensus value.")
    elif consensus.get("consensus_rank") is not None:
        reasons.append(f"Consensus rank is {consensus['consensus_rank']} at current pick {current_pick}.")
    if value_vs_adp >= 8:
        reasons.append(f"He is available {round(value_vs_adp)} picks after imported ADP.")
    if need_gap > 0:
        reasons.append(f"You still need a starting {player.get('position')}.")
    disagreement_reason = source_disagreement_reason(sources)
    if disagreement_reason:
        reasons.append(disagreement_reason)
    if (consensus.get("disagreement_score") or 0) >= 20:
        reasons.append("High source disagreement, so this is a risk/reward pick.")
    if injury_text and injury_text.lower() not in {"healthy", "active"}:
        reasons.append("Injury status should be monitored.")
    if consensus.get("projected_points_avg") is not None:
        reasons.append(f"Average imported projection is {consensus['projected_points_avg']} points.")
    return reasons[:6] or ["Imported consensus data makes him one of the better available fits."]


def source_disagreement_reason(sources: dict[str, dict[str, Any]]) -> str | None:
    source_ranks: list[tuple[str, float]] = []
    for source_name, source in sources.items():
        rank = source.get("overall_rank") if source.get("overall_rank") is not None else source.get("adp")
        if rank is not None:
            source_ranks.append((source_name, float(rank)))
    if len(source_ranks) < 2:
        return None
    high_source, high_rank = min(source_ranks, key=lambda item: item[1])
    low_source, low_rank = max(source_ranks, key=lambda item: item[1])
    spread = low_rank - high_rank
    if spread < 8:
        return None
    return f"{display_source(high_source)} is higher on him than {display_source(low_source)} by {round(spread)} picks."


def display_source(source_name: str) -> str:
    names = {
        "fantasypros": "FantasyPros",
        "espn": "ESPN",
        "sleeper": "Sleeper",
    }
    return names.get(source_name, source_name.replace("_", " ").title())


def fit_label(score: float) -> str:
    if score >= 140:
        return "Priority target"
    if score >= 95:
        return "Strong fit"
    if score >= 55:
        return "Consider"
    return "Watch list"


def waiver_risers(
    keepers: list[Keeper],
    picks: list[DraftPick],
    positions: list[str] | None = None,
    limit_per_position: int = 5,
    players: list[Player] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    pool = available_players(players or SAMPLE_PLAYERS, keepers, picks)
    wanted = positions or list(FANTASY_POSITIONS)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player in pool:
        if player.position not in wanted:
            continue
        usage_signal = player.snap_share * 35 + player.target_share * 45 + player.carry_share * 35
        score = player.trend_score * 10 + usage_signal - (player.rostered_pct * 0.12)
        grouped[player.position].append(
            {
                "player": player.to_dict(),
                "score": round(score, 2),
                "why": [
                    f"Trend score {player.trend_score}/10 from role, usage, and market context.",
                    f"Rostered in {player.rostered_pct}% of leagues in the seed data.",
                    player.notes or "Monitor news and depth-chart movement.",
                ],
            }
        )
    return {
        position: sorted(items, key=lambda item: item["score"], reverse=True)[:limit_per_position]
        for position, items in grouped.items()
    }


def evaluate_keeper(
    player_name: str,
    keep_round: int | None,
    settings: LeagueSettings,
    players: list[Player] | None = None,
) -> dict[str, Any]:
    player = find_player(player_name, players or SAMPLE_PLAYERS)
    if not player:
        return {
            "decision": "Need more info",
            "summary": "I could not match that player in the current player pool.",
            "player": None,
        }
    round_value_pick = keep_round * settings.teams if keep_round else player.adp
    surplus = round_value_pick - player.adp
    if surplus >= 24:
        decision = "Keep"
    elif surplus >= 8:
        decision = "Lean keep"
    elif surplus > -8:
        decision = "Fair price"
    else:
        decision = "Do not keep at that cost"
    return {
        "decision": decision,
        "summary": f"{player.name} costs around pick {round(round_value_pick)} versus ADP {round(player.adp)}.",
        "surplus_picks": round(surplus, 1),
        "player": player.to_dict(),
    }


def find_player(query: str, players: list[Player]) -> Player | None:
    normalized = normalize(query)
    exact = [player for player in players if normalize(player.name) == normalized]
    if exact:
        return exact[0]
    contains = [player for player in players if normalized in normalize(player.name) or normalize(player.name) in normalized]
    return contains[0] if contains else None


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def chat_response(
    message: str,
    settings: LeagueSettings,
    keepers: list[Keeper],
    picks: list[DraftPick],
) -> dict[str, Any]:
    text = message.lower()
    if any(term in text for term in ("draft next", "draft", "pick next", "best available")):
        recs = draft_recommendations(settings, keepers, picks, limit=5)
        best = recs[0] if recs else None
        answer = "My top draft target is "
        answer += f"{best.player.name} because {best.reasons[0].lower()}" if best else "not available from the current board."
        return {
            "intent": "draft_recommendation",
            "answer": answer,
            "cards": [rec.to_dict() for rec in recs],
        }

    if "waiver" in text or "pickup" in text or "rising" in text or "gaining value" in text:
        normalized_tokens = set(normalize(text).split())
        position_aliases = {
            "QB": {"qb", "qbs", "quarterback", "quarterbacks"},
            "RB": {"rb", "rbs", "running", "backs"},
            "WR": {"wr", "wrs", "receiver", "receivers", "wideouts"},
            "TE": {"te", "tes", "tight", "ends"},
            "DEF": {"def", "dst", "defense", "defenses"},
            "K": {"k", "kicker", "kickers"},
        }
        matched_position = next(
            (pos for pos, aliases in position_aliases.items() if normalized_tokens & aliases),
            None,
        )
        positions = [matched_position] if matched_position else ["QB", "RB", "WR", "TE"]
        risers = waiver_risers(keepers, picks, positions=positions)
        first_group = next(iter(risers.values()), [])
        first = first_group[0]["player"]["name"] if first_group else "the top available trend candidates"
        return {
            "intent": "waiver_risers",
            "answer": f"I would start with {first}. The riser board is ranking players by role growth, usage, roster percentage, and market signals.",
            "groups": risers,
        }

    if "keep" in text or "keeper" in text:
        round_match = re.search(r"round\s+(\d+)|(\d+)(?:st|nd|rd|th)\s+round", text)
        keep_round = int(next(group for group in round_match.groups() if group)) if round_match else None
        player = find_player(message, SAMPLE_PLAYERS)
        if player:
            result = evaluate_keeper(player.name, keep_round, settings)
            return {
                "intent": "keeper",
                "answer": f"{result['decision']}: {result['summary']}",
                "keeper": result,
            }
        return {
            "intent": "keeper",
            "answer": "Tell me the player name and keeper round, and I can compare the cost to draft value.",
        }

    if "matchup" in text:
        candidates = sorted(
            available_players(SAMPLE_PLAYERS, keepers, picks),
            key=lambda player: (player.odds_signal != "Neutral", player.projected_points),
            reverse=True,
        )[:5]
        return {
            "intent": "matchups",
            "answer": "The best matchup signals in the current seed data come from implied team totals, favorite scripts, and target/carry concentration.",
            "players": [asdict(player) for player in candidates],
        }

    recs = draft_recommendations(settings, keepers, picks, limit=3)
    return {
        "intent": "general",
        "answer": "I can help with draft picks, keeper values, waiver risers, and weekly matchup checks. Based on the current board, my next draft targets are below.",
        "cards": [rec.to_dict() for rec in recs],
    }
