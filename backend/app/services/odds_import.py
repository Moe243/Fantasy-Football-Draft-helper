"""Import NFL odds and player props from The Odds API."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from ..providers.odds import OddsClient
from .normalization import normalize_name


def import_nfl_odds(conn: sqlite3.Connection) -> dict[str, Any]:
    client = OddsClient()
    games = client.fetch_nfl_odds()
    imported = 0
    for game in games:
        event_id = game.get("id")
        home = game.get("home_team")
        away = game.get("away_team")
        spread_home, total = _extract_lines(game)
        conn.execute(
            """
            INSERT INTO game_odds_snapshots (
                event_id, home_team, away_team, commence_time, spread_home, total, raw_json, imported_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                home,
                away,
                game.get("commence_time"),
                spread_home,
                total,
                json.dumps(game),
                datetime.utcnow().isoformat(),
            ),
        )
        imported += 1
    conn.execute(
        """
        INSERT INTO source_import_runs (source_name, import_type, status, records_imported, finished_at)
        VALUES ('odds_api', 'game_odds', 'ok', ?, CURRENT_TIMESTAMP)
        """,
        (imported,),
    )
    conn.commit()
    return {"imported": imported, "events": len(games)}


def import_event_props(
    conn: sqlite3.Connection,
    event_id: str,
    markets: str = "player_pass_yds,player_rush_yds,player_reception_yds",
) -> dict[str, Any]:
    client = OddsClient()
    payload = client.fetch_event_odds(event_id, markets=markets)
    imported = 0
    for bookmaker in payload.get("bookmakers") or []:
        sportsbook = bookmaker.get("title") or bookmaker.get("key")
        for market in bookmaker.get("markets") or []:
            market_key = market.get("key") or "unknown"
            for outcome in market.get("outcomes") or []:
                player_name = outcome.get("description") or outcome.get("name")
                if not player_name:
                    continue
                player_id = match_player(conn, player_name)
                if not player_id:
                    continue
                line = outcome.get("point")
                price = outcome.get("price")
                conn.execute(
                    """
                    INSERT INTO player_props (
                        internal_player_id, source_name, sportsbook, market, line,
                        over_odds, implied_probability, game_id, raw_json, imported_at
                    )
                    VALUES (?, 'odds_api', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        player_id,
                        sportsbook,
                        market_key,
                        line,
                        str(price) if price is not None else None,
                        _american_implied(price),
                        event_id,
                        json.dumps(outcome),
                        datetime.utcnow().isoformat(),
                    ),
                )
                imported += 1
    conn.commit()
    return {"imported": imported, "event_id": event_id}


def list_odds_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_id, home_team, away_team, commence_time, spread_home, total, imported_at
        FROM game_odds_snapshots
        ORDER BY imported_at DESC
        LIMIT 50
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _extract_lines(game: dict[str, Any]) -> tuple[float | None, float | None]:
    spread_home = None
    total = None
    for bookmaker in game.get("bookmakers") or []:
        for market in bookmaker.get("markets") or []:
            key = market.get("key")
            if key == "spreads":
                for outcome in market.get("outcomes") or []:
                    if outcome.get("name") == game.get("home_team"):
                        spread_home = outcome.get("point")
            if key == "totals":
                for outcome in market.get("outcomes") or []:
                    if outcome.get("name") == "Over":
                        total = outcome.get("point")
        if spread_home is not None and total is not None:
            break
    return spread_home, total


def match_player(conn: sqlite3.Connection, name: str) -> str | None:
    normalized = normalize_name(name)
    row = conn.execute(
        "SELECT internal_player_id FROM players WHERE normalized_name = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    return row["internal_player_id"] if row else None


def _american_implied(price: Any) -> float | None:
    if price is None:
        return None
    try:
        american = float(price)
    except (TypeError, ValueError):
        return None
    if american > 0:
        return round(100.0 / (american + 100.0), 4)
    return round(abs(american) / (abs(american) + 100.0), 4)
