"""Full Sleeper draft import orchestration."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..providers.sleeper import SleeperClient
from .league_import import import_sleeper_league


def import_league_draft_data(
    conn: sqlite3.Connection,
    league_id: str,
    client: SleeperClient | None = None,
) -> dict[str, Any]:
    """Import league, drafts, picks, traded picks, and draft-slot mapping."""
    return import_sleeper_league(conn, league_id, client=client)

