"""Multi-source comparison payloads for player detail and draft cards."""

from __future__ import annotations

from typing import Any


def nflverse_fantasy_points(stats: dict[str, list[dict[str, Any]]]) -> float | None:
    actual_rows = [
        row
        for row in stats.get("actual", [])
        if str(row.get("source_name") or "").lower() == "nflverse"
    ]
    if not actual_rows:
        return None
    values = [float(row["fantasy_points"]) for row in actual_rows if row.get("fantasy_points") is not None]
    return round(sum(values), 2) if values else None


def build_source_comparison(
    consensus: dict[str, Any] | None,
    rankings: dict[str, dict[str, Any]],
    stats: dict[str, list[dict[str, Any]]],
    current_pick: int = 1,
) -> dict[str, Any]:
    consensus_data = consensus or {}
    sleeper = rankings.get("sleeper") or {}
    espn = rankings.get("espn") or {}
    fantasypros = rankings.get("fantasypros") or {}

    return {
        "sleeper_adp": first_rank_value(sleeper.get("adp"), consensus_data.get("sleeper_adp")),
        "sleeper_rank": first_rank_value(sleeper.get("overall_rank"), consensus_data.get("sleeper_rank")),
        "espn_rank": first_rank_value(espn.get("overall_rank"), consensus_data.get("espn_rank")),
        "fantasypros_rank": first_rank_value(
            fantasypros.get("overall_rank"),
            consensus_data.get("fantasypros_rank"),
        ),
        "nflverse_fantasy_points": nflverse_fantasy_points(stats),
        "projected_points": consensus_data.get("projected_points_avg"),
        "consensus_rank": consensus_data.get("consensus_rank"),
        "rank_spread": consensus_data.get("rank_spread"),
        "source_count": consensus_data.get("source_count") or 0,
        "best_source_rank": consensus_data.get("best_source_rank"),
        "worst_source_rank": consensus_data.get("worst_source_rank"),
        "lowest_source_rank": consensus_data.get("best_source_rank"),
        "highest_source_rank": consensus_data.get("worst_source_rank"),
        "value_label": consensus_data.get("label") or "Not Enough Sources",
        "current_pick": current_pick,
        "value_vs_current_pick": consensus_data.get("value_vs_current_pick"),
    }


def attach_source_comparison(item: dict[str, Any], current_pick: int) -> dict[str, Any]:
    consensus = item.get("consensus") or {}
    item = dict(item)
    item["source_comparison"] = {
        "consensus_rank": consensus.get("consensus_rank"),
        "source_count": consensus.get("source_count") or 0,
        "lowest_source_rank": consensus.get("best_source_rank"),
        "highest_source_rank": consensus.get("worst_source_rank"),
        "rank_spread": consensus.get("rank_spread"),
        "value_label": consensus.get("label") or "Not Enough Sources",
        "sleeper_adp": consensus.get("sleeper_adp"),
        "espn_rank": consensus.get("espn_rank"),
        "fantasypros_rank": consensus.get("fantasypros_rank"),
        "projected_points": consensus.get("projected_points_avg"),
        "current_pick": current_pick,
    }
    return item


def first_rank_value(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None
