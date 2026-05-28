"""SQLite persistence for the local MVP."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import settings
from .models import DraftPick, Keeper, LeagueSettings
from .sample_data import SAMPLE_PLAYERS
from .services.normalization import normalize_name, normalize_position, normalize_team


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

        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            internal_player_id TEXT UNIQUE NOT NULL,
            sleeper_id TEXT UNIQUE,
            espn_id TEXT,
            fantasypros_id TEXT,
            full_name TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            normalized_name TEXT NOT NULL,
            position TEXT,
            team TEXT,
            fantasy_positions TEXT,
            active INTEGER,
            age INTEGER,
            years_exp INTEGER,
            status TEXT,
            injury_status TEXT,
            search_rank INTEGER,
            source TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_players_position ON players(position);
        CREATE INDEX IF NOT EXISTS idx_players_team ON players(team);
        CREATE INDEX IF NOT EXISTS idx_players_normalized_name ON players(normalized_name);

        CREATE TABLE IF NOT EXISTS player_source_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            internal_player_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_player_id TEXT,
            overall_rank REAL,
            position_rank TEXT,
            adp REAL,
            projected_points REAL,
            tier INTEGER,
            bye_week INTEGER,
            raw_json TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(internal_player_id, source_name)
        );

        CREATE INDEX IF NOT EXISTS idx_rankings_source ON player_source_rankings(source_name);
        CREATE INDEX IF NOT EXISTS idx_rankings_player ON player_source_rankings(internal_player_id);

        CREATE TABLE IF NOT EXISTS source_import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            import_type TEXT NOT NULL,
            status TEXT NOT NULL,
            records_imported INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
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


def start_import_run(conn: sqlite3.Connection, source_name: str, import_type: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO source_import_runs (source_name, import_type, status)
        VALUES (?, ?, 'running')
        """,
        (source_name, import_type),
    )
    conn.commit()
    return int(cursor.lastrowid)


def finish_import_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    records_imported: int = 0,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE source_import_runs
        SET status = ?, records_imported = ?, error_message = ?, finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, records_imported, error_message, run_id),
    )
    conn.commit()


def upsert_player(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    fantasy_positions = payload.get("fantasy_positions")
    if isinstance(fantasy_positions, list):
        fantasy_positions = json.dumps([normalize_position(str(item)) for item in fantasy_positions if item])
    elif fantasy_positions is None:
        fantasy_positions = json.dumps([])

    full_name = str(payload.get("full_name") or "").strip()
    normalized = payload.get("normalized_name") or normalize_name(full_name)
    conn.execute(
        """
        INSERT INTO players (
            internal_player_id,
            sleeper_id,
            espn_id,
            fantasypros_id,
            full_name,
            first_name,
            last_name,
            normalized_name,
            position,
            team,
            fantasy_positions,
            active,
            age,
            years_exp,
            status,
            injury_status,
            search_rank,
            source,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(internal_player_id) DO UPDATE SET
            sleeper_id = COALESCE(excluded.sleeper_id, players.sleeper_id),
            espn_id = COALESCE(excluded.espn_id, players.espn_id),
            fantasypros_id = COALESCE(excluded.fantasypros_id, players.fantasypros_id),
            full_name = excluded.full_name,
            first_name = COALESCE(excluded.first_name, players.first_name),
            last_name = COALESCE(excluded.last_name, players.last_name),
            normalized_name = excluded.normalized_name,
            position = COALESCE(excluded.position, players.position),
            team = COALESCE(excluded.team, players.team),
            fantasy_positions = excluded.fantasy_positions,
            active = COALESCE(excluded.active, players.active),
            age = COALESCE(excluded.age, players.age),
            years_exp = COALESCE(excluded.years_exp, players.years_exp),
            status = COALESCE(excluded.status, players.status),
            injury_status = COALESCE(excluded.injury_status, players.injury_status),
            search_rank = COALESCE(excluded.search_rank, players.search_rank),
            source = COALESCE(excluded.source, players.source),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            payload["internal_player_id"],
            payload.get("sleeper_id"),
            payload.get("espn_id"),
            payload.get("fantasypros_id"),
            full_name,
            payload.get("first_name"),
            payload.get("last_name"),
            normalized,
            normalize_position(str(payload.get("position") or "")) or None,
            normalize_team(str(payload.get("team") or "")) or None,
            fantasy_positions,
            optional_bool_int(payload.get("active")),
            optional_int_value(payload.get("age")),
            optional_int_value(payload.get("years_exp")),
            payload.get("status"),
            payload.get("injury_status"),
            optional_int_value(payload.get("search_rank")),
            payload.get("source"),
        ),
    )
    conn.commit()


def upsert_source_ranking(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO player_source_rankings (
            internal_player_id,
            source_name,
            source_player_id,
            overall_rank,
            position_rank,
            adp,
            projected_points,
            tier,
            bye_week,
            raw_json,
            imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(internal_player_id, source_name) DO UPDATE SET
            source_player_id = COALESCE(excluded.source_player_id, player_source_rankings.source_player_id),
            overall_rank = excluded.overall_rank,
            position_rank = excluded.position_rank,
            adp = excluded.adp,
            projected_points = excluded.projected_points,
            tier = excluded.tier,
            bye_week = excluded.bye_week,
            raw_json = excluded.raw_json,
            imported_at = CURRENT_TIMESTAMP
        """,
        (
            payload["internal_player_id"],
            payload["source_name"],
            payload.get("source_player_id"),
            optional_float_value(payload.get("overall_rank")),
            payload.get("position_rank"),
            optional_float_value(payload.get("adp")),
            optional_float_value(payload.get("projected_points")),
            optional_int_value(payload.get("tier")),
            optional_int_value(payload.get("bye_week")),
            payload.get("raw_json"),
        ),
    )
    conn.commit()


def has_database_players(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM players LIMIT 1").fetchone()
    return row is not None


def get_player_row(conn: sqlite3.Connection, internal_player_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM players WHERE internal_player_id = ?",
        (internal_player_id,),
    ).fetchone()


def get_player_by_sleeper_id(conn: sqlite3.Connection, sleeper_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM players WHERE sleeper_id = ?", (sleeper_id,)).fetchone()


def query_player_rows(
    conn: sqlite3.Connection,
    position: str | None = None,
    search: str | None = None,
    active: int | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if position:
        clauses.append("position = ?")
        params.append(normalize_position(position))
    if search:
        clauses.append("(normalized_name LIKE ? OR full_name LIKE ?)")
        normalized_search = f"%{normalize_name(search)}%"
        params.extend([normalized_search, f"%{search}%"])
    if active is not None:
        clauses.append("active = ?")
        params.append(active)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    limit_sql = " LIMIT ?" if limit else ""
    if limit:
        params.append(limit)
    return conn.execute(
        f"""
        SELECT *
        FROM players
        {where}
        ORDER BY COALESCE(search_rank, 999999), full_name
        {limit_sql}
        """,
        params,
    ).fetchall()


def get_players_for_api(
    conn: sqlite3.Connection,
    position: str | None = None,
    search: str | None = None,
    active: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    rows = query_player_rows(conn, position=position, search=search, active=active)
    if rows:
        return [player_row_to_api(row) for row in rows], "database"

    sample_players = SAMPLE_PLAYERS
    if position:
        normalized_position = normalize_position(position)
        sample_players = [player for player in sample_players if player.position == normalized_position]
    if search:
        normalized_search = normalize_name(search)
        sample_players = [player for player in sample_players if normalized_search in normalize_name(player.name)]
    if active is not None and active != 1:
        sample_players = []
    return [player.to_dict() for player in sample_players], "sample"


def player_row_to_api(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    getter = row.get if isinstance(row, dict) else lambda key, default=None: row[key] if key in row.keys() else default
    fantasy_positions_raw = getter("fantasy_positions") or "[]"
    try:
        fantasy_positions = json.loads(fantasy_positions_raw)
    except json.JSONDecodeError:
        fantasy_positions = []
    injury_status = getter("injury_status") or getter("status") or "Healthy"
    return {
        "id": getter("internal_player_id"),
        "internal_player_id": getter("internal_player_id"),
        "sleeper_id": getter("sleeper_id"),
        "espn_id": getter("espn_id"),
        "fantasypros_id": getter("fantasypros_id"),
        "name": getter("full_name"),
        "full_name": getter("full_name"),
        "first_name": getter("first_name"),
        "last_name": getter("last_name"),
        "normalized_name": getter("normalized_name"),
        "position": getter("position") or "",
        "team": getter("team") or "",
        "fantasy_positions": fantasy_positions,
        "active": bool(getter("active")),
        "age": getter("age"),
        "years_exp": getter("years_exp"),
        "status": getter("status"),
        "injury_status": injury_status,
        "search_rank": getter("search_rank"),
        "source": getter("source"),
        "updated_at": getter("updated_at"),
        "projected_points": 0.0,
        "adp": 999.0,
        "rank": getter("search_rank") or 999999,
        "bye": None,
        "depth_chart": "Unknown",
        "snap_share": 0.0,
        "target_share": 0.0,
        "carry_share": 0.0,
        "trend_score": 0.0,
        "rostered_pct": 0.0,
        "odds_signal": "Neutral",
        "notes": "",
    }


def optional_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def optional_int_value(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float_value(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
