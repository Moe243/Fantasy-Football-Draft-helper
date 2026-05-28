"""SQLite persistence for the local MVP."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import settings
from .models import DraftPick, Keeper, LeagueSettings


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS keepers (
            player_id TEXT NOT NULL,
            team_name TEXT NOT NULL,
            round INTEGER,
            pick_no INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, team_name)
        );

        CREATE TABLE IF NOT EXISTS draft_picks (
            pick_no INTEGER PRIMARY KEY,
            player_id TEXT NOT NULL UNIQUE,
            manager TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS league_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            teams INTEGER NOT NULL,
            scoring TEXT NOT NULL,
            draft_slot INTEGER NOT NULL,
            roster_slots TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    default_settings = LeagueSettings()
    conn.execute(
        """
        INSERT OR IGNORE INTO league_settings
            (id, teams, scoring, draft_slot, roster_slots)
        VALUES
            (1, ?, ?, ?, ?)
        """,
        (
            default_settings.teams,
            default_settings.scoring,
            default_settings.draft_slot,
            json.dumps(default_settings.roster_slots),
        ),
    )
    conn.commit()


def get_keepers(conn: sqlite3.Connection) -> list[Keeper]:
    rows = conn.execute(
        "SELECT player_id, team_name, round, pick_no FROM keepers ORDER BY COALESCE(pick_no, 9999), team_name"
    ).fetchall()
    return [
        Keeper(
            player_id=row["player_id"],
            team_name=row["team_name"],
            round=row["round"],
            pick_no=row["pick_no"],
        )
        for row in rows
    ]


def upsert_keeper(conn: sqlite3.Connection, keeper: Keeper) -> None:
    conn.execute(
        """
        INSERT INTO keepers (player_id, team_name, round, pick_no)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(player_id, team_name) DO UPDATE SET
            round = excluded.round,
            pick_no = excluded.pick_no
        """,
        (keeper.player_id, keeper.team_name, keeper.round, keeper.pick_no),
    )
    conn.commit()


def delete_keeper(conn: sqlite3.Connection, player_id: str, team_name: str) -> None:
    conn.execute(
        "DELETE FROM keepers WHERE player_id = ? AND team_name = ?",
        (player_id, team_name),
    )
    conn.commit()


def clear_keepers(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM keepers")
    conn.commit()


def get_draft_picks(conn: sqlite3.Connection) -> list[DraftPick]:
    rows = conn.execute(
        "SELECT pick_no, player_id, manager, source FROM draft_picks ORDER BY pick_no"
    ).fetchall()
    return [
        DraftPick(
            pick_no=row["pick_no"],
            player_id=row["player_id"],
            manager=row["manager"],
            source=row["source"],
        )
        for row in rows
    ]


def add_draft_pick(conn: sqlite3.Connection, pick: DraftPick) -> None:
    conn.execute(
        """
        INSERT INTO draft_picks (pick_no, player_id, manager, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(pick_no) DO UPDATE SET
            player_id = excluded.player_id,
            manager = excluded.manager,
            source = excluded.source
        """,
        (pick.pick_no, pick.player_id, pick.manager, pick.source),
    )
    conn.commit()


def remove_draft_pick(conn: sqlite3.Connection, pick_no: int) -> None:
    conn.execute("DELETE FROM draft_picks WHERE pick_no = ?", (pick_no,))
    conn.commit()


def clear_draft_picks(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM draft_picks")
    conn.commit()


def get_league_settings(conn: sqlite3.Connection) -> LeagueSettings:
    row = conn.execute(
        "SELECT teams, scoring, draft_slot, roster_slots FROM league_settings WHERE id = 1"
    ).fetchone()
    if row is None:
        return LeagueSettings()
    return LeagueSettings(
        teams=int(row["teams"]),
        scoring=row["scoring"],
        draft_slot=int(row["draft_slot"]),
        roster_slots=json.loads(row["roster_slots"]),
    )


def update_league_settings(conn: sqlite3.Connection, payload: dict[str, Any]) -> LeagueSettings:
    current = get_league_settings(conn)
    roster_slots = payload.get("roster_slots")
    updated = LeagueSettings(
        teams=int(payload.get("teams", current.teams)),
        scoring=str(payload.get("scoring", current.scoring)),
        draft_slot=int(payload.get("draft_slot", current.draft_slot)),
        roster_slots=dict(roster_slots) if roster_slots else current.roster_slots,
    )
    conn.execute(
        """
        INSERT INTO league_settings (id, teams, scoring, draft_slot, roster_slots, updated_at)
        VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            teams = excluded.teams,
            scoring = excluded.scoring,
            draft_slot = excluded.draft_slot,
            roster_slots = excluded.roster_slots,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            updated.teams,
            updated.scoring,
            updated.draft_slot,
            json.dumps(updated.roster_slots),
        ),
    )
    conn.commit()
    return updated
