"""Startup data refresh helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from .. import db
from ..providers.http import ProviderError
from ..providers.sleeper import SleeperClient
from .sleeper_import import import_sleeper_players


def should_refresh_sleeper_players(conn: sqlite3.Connection, max_age_days: int = 7) -> bool:
    if db.count_players_by_source(conn, "sleeper") == 0:
        return True
    latest = db.latest_import_run(conn, "sleeper", "players")
    if latest is None or latest["status"] != "success":
        return True
    finished_at = parse_timestamp(latest["finished_at"] or latest["started_at"])
    if finished_at is None:
        return True
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now - finished_at > timedelta(days=max_age_days)


def ensure_sleeper_players(conn: sqlite3.Connection) -> dict[str, object]:
    if not should_refresh_sleeper_players(conn):
        return {
            "status": "fresh",
            "imported_count": 0,
            "player_count": db.count_players_by_source(conn, "sleeper"),
        }
    try:
        players = SleeperClient().players("nfl")
        return import_sleeper_players(conn, players)
    except ProviderError as exc:
        return {"status": "error", "error_message": str(exc)}


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None
