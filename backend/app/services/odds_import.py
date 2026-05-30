"""Import game odds and player props from The Odds API."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db
from ..providers.odds import OddsClient
from ..providers.http import ProviderError
from .normalization import normalize_name


def import_nfl_odds_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    run_id = db.start_import_run(conn, "the_odds_api", "game_odds")
    try:
        games = OddsClient().fetch_nfl_odds()
        imported = store_game_odds(conn, games)
        db.finish_import_run(conn, run_id, "success", records_imported=imported)
        return {"status": "success", "games_imported": imported}
    except ProviderError as exc:
        db.finish_import_run(conn, run_id, "error", error_message=str(exc))
        raise


def store_game_odds(conn: sqlite3.Connection, games: list[dict[str, Any]]) -> int:
    count = 0
    for game in games:
        home = game.get("home_team")
        away = game.get("away_team")
        game_id = game.get("id")
        for bookmaker in game.get("bookmakers") or []:
            spread = None
            total = None
            for market in bookmaker.get("markets") or []:
                key = market.get("key")
                outcomes = market.get("outcomes") or []
                if key == "spreads" and outcomes:
                    spread = outcomes[0].get("point")
                if key == "totals" and outcomes:
                    total = outcomes[0].get("point")
            conn.execute(
                """
                INSERT INTO game_odds_snapshots (
                    game_id, home_team, away_team, spread, total, sportsbook, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (game_id, home, away, spread, total, bookmaker.get("key"), json.dumps(game)),
            )
            count += 1
    conn.commit()
    return count


def import_event_player_props(conn: sqlite3.Connection, event_id: str, markets: str | None = None) -> dict[str, Any]:
    market_list = markets or "player_pass_yds,player_rush_yds,player_reception_yds,player_anytime_td"
    props_data = OddsClient().fetch_event_odds(event_id, markets=market_list)
    run_id = db.start_import_run(conn, "the_odds_api", "player_props")
    imported = store_props_from_event(conn, props_data)
    db.finish_import_run(conn, run_id, "success", records_imported=imported)
    return {"status": "success", "props_imported": imported, "event_id": event_id}


def store_props_from_event(conn: sqlite3.Connection, event: dict[str, Any]) -> int:
    count = 0
    for bookmaker in event.get("bookmakers") or []:
        sportsbook = bookmaker.get("title") or bookmaker.get("key")
        for market in bookmaker.get("markets") or []:
            market_key = market.get("key") or market.get("name")
            for outcome in market.get("outcomes") or []:
                player_name = outcome.get("description") or outcome.get("name")
                if not player_name or player_name in {"Over", "Under"}:
                    continue
                player_row = conn.execute(
                    "SELECT internal_player_id FROM players WHERE lower(full_name) = lower(?)",
                    (player_name,),
                ).fetchone()
                if not player_row:
                    normalized = normalize_name(player_name)
                    player_row = conn.execute(
                        "SELECT internal_player_id FROM players WHERE lower(full_name) LIKE ?",
                        (f"%{normalized}%",),
                    ).fetchone()
                if not player_row:
                    continue
                conn.execute(
                    """
                    INSERT INTO player_props (
                        internal_player_id, source_name, sportsbook, market, line,
                        over_odds, under_odds, game_id, raw_json
                    )
                    VALUES (?, 'the_odds_api', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        player_row["internal_player_id"],
                        sportsbook,
                        market_key,
                        outcome.get("point"),
                        str(outcome.get("price")) if outcome.get("name") == "Over" else None,
                        str(outcome.get("price")) if outcome.get("name") == "Under" else None,
                        event.get("id"),
                        json.dumps(outcome),
                    ),
                )
                count += 1
    conn.commit()
    return count
