"""Draft, keeper, waiver, and chat recommendation logic."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import re
from typing import Any

from ..models import DraftPick, Keeper, LeagueSettings, Player, Recommendation
from ..sample_data import SAMPLE_PLAYERS, players_by_id


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
    selected.extend(keeper.pick_no for keeper in keepers if keeper.pick_no)
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
