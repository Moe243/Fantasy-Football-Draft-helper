"""Fetch public FantasyPros consensus rankings from ranking pages."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .http import ProviderError

USER_AGENT = "Mozilla/5.0 (compatible; fantasy-football-assistant/0.1)"
PLAYER_ARRAY_RE = re.compile(r'\[\{"player_id":\d+,"player_name":')

POSITION_URLS: dict[str, str] = {
    "overall": "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
    "qb": "https://www.fantasypros.com/nfl/rankings/qb.php",
    "rb": "https://www.fantasypros.com/nfl/rankings/rb.php",
    "wr": "https://www.fantasypros.com/nfl/rankings/wr.php",
    "te": "https://www.fantasypros.com/nfl/rankings/te.php",
}


class FantasyProsFetchError(RuntimeError):
    pass


def normalize_position_key(position: str) -> str:
    key = str(position or "overall").strip().lower()
    if key not in POSITION_URLS:
        raise FantasyProsFetchError(f"Unsupported position: {position}")
    return key


def fetch_fantasypros_rankings(position: str = "overall") -> list[dict[str, Any]]:
    """Download and parse ranking rows from a public FantasyPros page."""
    position_key = normalize_position_key(position)
    html = fetch_rankings_html(POSITION_URLS[position_key])
    entries = parse_ranking_entries(html)
    if not entries:
        raise FantasyProsFetchError("No ranking rows found in FantasyPros response")
    return [entry_to_row(entry, position_key) for entry in entries]


def fetch_rankings_html(url: str, timeout: int = 20) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"{exc.code} from {url}: {body[:300]}") from exc
    except URLError as exc:
        raise ProviderError(f"Could not reach {url}: {exc.reason}") from exc


def parse_ranking_entries(html: str) -> list[dict[str, Any]]:
    match = PLAYER_ARRAY_RE.search(html)
    if not match:
        return []
    start = match.start()
    depth = 0
    for index in range(start, len(html)):
        char = html[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                try:
                    payload = json.loads(html[start : index + 1])
                except json.JSONDecodeError:
                    return []
                if isinstance(payload, list):
                    return [item for item in payload if isinstance(item, dict)]
                return []
    return []


def entry_to_row(entry: dict[str, Any], position_key: str) -> dict[str, Any]:
    player_name = str(entry.get("player_name") or "").strip()
    team = str(entry.get("player_team_id") or "").strip() or None
    player_position = str(entry.get("player_position_id") or entry.get("player_positions") or "").strip() or None
    row: dict[str, Any] = {
        "player_name": player_name,
        "team": team,
        "position": player_position,
        "source_player_id": optional_str(entry.get("player_id")),
        "position_rank": optional_str(entry.get("pos_rank")),
        "tier": entry.get("tier"),
        "bye_week": optional_int(entry.get("player_bye_week")),
    }
    rank_ecr = entry.get("rank_ecr")
    if position_key == "overall":
        row["overall_rank"] = rank_ecr
    elif rank_ecr is not None and not row.get("position_rank"):
        row["position_rank"] = str(rank_ecr)
    return row


def optional_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
