"""Rule-based 2026 player outlook from imported data only."""

from __future__ import annotations

from typing import Any


def build_player_outlook(
    player: dict[str, Any],
    history: dict[str, Any],
    props: list[dict[str, Any]],
    ranking_signals: dict[str, Any] | None = None,
) -> str:
    position = (player.get("position") or "UNK").upper()
    injury = str(player.get("injury_status") or "").lower()
    has_2026_proj = bool((ranking_signals or {}).get("projection_score"))
    props_2026 = [p for p in props if int(p.get("season") or 0) >= 2026] or props[:6]

    if not has_2026_proj and not props_2026 and not history.get("2025") and not history.get("2024"):
        return "No projection or props imported yet, so outlook is based mostly on ranking and roster fit."

    parts: list[str] = []

    if position == "QB":
        if has_2026_proj:
            parts.append("Elite QB profile with a usable projection")
        else:
            parts.append("QB profile")
        if (ranking_signals or {}).get("qb_round_penalty", 0) < -50:
            parts.append("but the algorithm avoids early QB unless value is strong after Round 3")
        elif injury and injury not in {"healthy", "active", ""}:
            parts.append("with injury risk to monitor")
        return _sentence(parts)

    if position == "RB":
        rush_prop = _has_market(props_2026, ("rushing_yards", "rush_yards", "rushing_tds", "rush_tds"))
        if rush_prop:
            parts.append("Upside RB with rushing TD value")
            parts.append("but projection depends on workload")
        elif has_2026_proj:
            parts.append("RB with stable volume projection and roster-fit value")
        else:
            parts.append("RB value tied to consensus rank and roster need")
        return _sentence(parts)

    if position == "WR":
        recv_prop = _has_market(props_2026, ("receiving_yards", "receptions", "receiving_tds", "anytime_td"))
        if recv_prop:
            parts.append("High-volume WR profile with strong receiving-yard props")
            if has_2026_proj:
                parts.append("and stable projection")
            else:
                parts.append("with market upside")
        elif has_2026_proj:
            parts.append("WR with solid projection and target-share upside")
        else:
            parts.append("WR ranked on consensus and fit more than fresh props")
        return _sentence(parts)

    if position == "TE":
        parts.append("TE with red-zone and target-path value")
        if has_2026_proj:
            parts.append("supported by imported projection")
        return _sentence(parts)

    if position in {"DEF", "DST"}:
        return "Defense streamer profile; best value in later rounds when roster core is set."

    if position == "K":
        return "Kicker profile; draft late unless your build already locks core starters."

    if injury and injury not in {"healthy", "active", ""}:
        parts.append(f"{position} with injury flag on the profile")
    else:
        parts.append(f"{position} outlook driven by ranking fit and imported signals")
    return _sentence(parts)


def _has_market(props: list[dict[str, Any]], markets: tuple[str, ...]) -> bool:
    for prop in props:
        market = str(prop.get("market") or "").lower()
        if any(token in market for token in markets):
            return True
    return False


def _sentence(parts: list[str]) -> str:
    text = ", ".join(part.strip() for part in parts if part).strip()
    if not text:
        return "Outlook is based on ranking, roster fit, and any imported props."
    if not text.endswith("."):
        text += "."
    return text[0].upper() + text[1:]
