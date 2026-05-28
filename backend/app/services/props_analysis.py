"""Neutral sportsbook prop comparison helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def analyze_props(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prop in props:
        grouped[prop.get("market") or "unknown"].append(prop)
    analysis: list[dict[str, Any]] = []
    for market, rows in grouped.items():
        lines = [row for row in rows if row.get("line") is not None]
        if not lines:
            continue
        highest = max(lines, key=lambda row: float(row["line"]))
        lowest = min(lines, key=lambda row: float(row["line"]))
        spread = float(highest["line"]) - float(lowest["line"])
        notes = [
            f"{highest.get('sportsbook') or highest.get('source_name')} has the highest {market.replace('_', ' ')} line.",
            f"{lowest.get('sportsbook') or lowest.get('source_name')} has the lowest {market.replace('_', ' ')} line.",
        ]
        if spread:
            notes.append(f"Books disagree by {round(spread, 2)} on this market.")
        analysis.append(
            {
                "market": market,
                "highest_line": highest,
                "lowest_line": lowest,
                "line_spread": round(spread, 2),
                "best_over_line": lowest,
                "best_under_line": highest,
                "notes": notes,
            }
        )
    return analysis
