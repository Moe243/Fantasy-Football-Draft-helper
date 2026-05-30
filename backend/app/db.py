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

        CREATE TABLE IF NOT EXISTS sleeper_leagues (
            league_id TEXT PRIMARY KEY,
            name TEXT,
            season TEXT,
            status TEXT,
            total_rosters INTEGER,
            roster_positions_json TEXT,
            scoring_settings_json TEXT,
            settings_json TEXT,
            previous_league_id TEXT,
            raw_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS league_managers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            sleeper_user_id TEXT,
            roster_id INTEGER,
            display_name TEXT,
            team_name TEXT,
            avatar TEXT,
            is_me INTEGER DEFAULT 0,
            raw_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(league_id, roster_id)
        );

        CREATE TABLE IF NOT EXISTS league_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            draft_id TEXT UNIQUE NOT NULL,
            season TEXT,
            status TEXT,
            type TEXT,
            settings_json TEXT,
            metadata_json TEXT,
            draft_order_json TEXT,
            slot_to_roster_json TEXT,
            raw_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS league_draft_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            draft_id TEXT NOT NULL,
            pick_no INTEGER,
            round INTEGER,
            draft_slot INTEGER,
            roster_id INTEGER,
            picked_by TEXT,
            player_id TEXT,
            sleeper_player_id TEXT,
            player_name TEXT,
            position TEXT,
            team TEXT,
            is_keeper INTEGER DEFAULT 0,
            raw_json TEXT,
            UNIQUE(draft_id, pick_no)
        );

        CREATE TABLE IF NOT EXISTS league_traded_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            draft_id TEXT,
            season TEXT,
            round INTEGER,
            roster_id INTEGER,
            previous_owner_id INTEGER,
            owner_id INTEGER,
            original_roster_id INTEGER,
            current_roster_id INTEGER,
            raw_json TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS draft_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            draft_id TEXT,
            roster_id INTEGER,
            sleeper_user_id TEXT,
            manager_name TEXT,
            draft_slot INTEGER,
            UNIQUE(league_id, draft_id, draft_slot)
        );

        CREATE TABLE IF NOT EXISTS user_draft_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            draft_id TEXT,
            season TEXT,
            round INTEGER NOT NULL,
            pick_no INTEGER NOT NULL,
            draft_slot INTEGER,
            original_roster_id INTEGER,
            current_roster_id INTEGER,
            manager_name TEXT,
            is_mine INTEGER DEFAULT 0,
            source TEXT,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS manager_draft_tendencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            roster_id INTEGER,
            manager_name TEXT,
            round INTEGER,
            position TEXT,
            pick_count INTEGER,
            avg_pick_no REAL,
            avg_player_rank REAL,
            reach_rate REAL,
            value_pick_rate REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(league_id, roster_id, round, position)
        );

        CREATE TABLE IF NOT EXISTS practice_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            name TEXT,
            status TEXT,
            current_pick INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS practice_draft_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            practice_draft_id INTEGER NOT NULL,
            pick_no INTEGER NOT NULL,
            round INTEGER,
            draft_slot INTEGER,
            manager_name TEXT,
            roster_id INTEGER,
            player_id TEXT,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(practice_draft_id, pick_no)
        );

        CREATE TABLE IF NOT EXISTS player_stat_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            internal_player_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            season INTEGER,
            week INTEGER,
            stat_type TEXT NOT NULL,
            games_played REAL,
            passing_yards REAL,
            passing_tds REAL,
            interceptions REAL,
            rushing_attempts REAL,
            rushing_yards REAL,
            rushing_tds REAL,
            targets REAL,
            receptions REAL,
            receiving_yards REAL,
            receiving_tds REAL,
            fantasy_points REAL,
            raw_json TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS player_props (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            internal_player_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            sportsbook TEXT,
            market TEXT NOT NULL,
            line REAL,
            over_odds TEXT,
            under_odds TEXT,
            implied_probability REAL,
            game_id TEXT,
            opponent TEXT,
            week INTEGER,
            season INTEGER,
            starts_at TEXT,
            raw_json TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS player_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            internal_player_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            url TEXT,
            published_at TEXT,
            raw_json TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_favorite_players (
            league_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (league_id, player_id)
        );

        CREATE TABLE IF NOT EXISTS user_draft_preferences (
            league_id TEXT PRIMARY KEY,
            reach_bias REAL DEFAULT 0,
            value_bias REAL DEFAULT 0,
            position_weights_json TEXT,
            stack_preferences_json TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_draft_tendencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            round INTEGER,
            position TEXT,
            pick_count INTEGER,
            reach_rate REAL,
            value_pick_rate REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(league_id, round, position)
        );
        """
    )
    ensure_columns(
        conn,
        "players",
        {
            "jersey_number": "TEXT",
            "height": "TEXT",
            "weight": "TEXT",
            "college": "TEXT",
            "birth_date": "TEXT",
            "depth_chart_position": "TEXT",
            "depth_chart_order": "INTEGER",
            "news_updated_at": "TEXT",
            "raw_json": "TEXT",
        },
    )
    migrate_draft_slots(conn)
    ensure_columns(
        conn,
        "user_draft_picks",
        {
            "draft_id": "TEXT",
            "season": "TEXT",
        },
    )
    ensure_columns(
        conn,
        "keepers",
        {
            "league_id": "TEXT",
            "roster_id": "INTEGER",
            "sleeper_user_id": "TEXT",
        },
    )
    conn.execute(
        '''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_keepers_league_roster
        ON keepers(league_id, roster_id)
        WHERE league_id IS NOT NULL AND roster_id IS NOT NULL
        '''
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


def migrate_draft_slots(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(draft_slots)").fetchall()}
    if "draft_id" in columns:
        return
    conn.executescript(
        """
        ALTER TABLE draft_slots RENAME TO draft_slots_old;
        CREATE TABLE draft_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id TEXT NOT NULL,
            draft_id TEXT,
            roster_id INTEGER,
            sleeper_user_id TEXT,
            manager_name TEXT,
            draft_slot INTEGER,
            UNIQUE(league_id, draft_id, draft_slot)
        );
        INSERT INTO draft_slots (league_id, draft_id, roster_id, sleeper_user_id, manager_name, draft_slot)
        SELECT league_id, NULL, roster_id, sleeper_user_id, manager_name, draft_slot
        FROM draft_slots_old;
        DROP TABLE draft_slots_old;
        """
    )


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, column_type in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


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
            jersey_number,
            height,
            weight,
            college,
            birth_date,
            depth_chart_position,
            depth_chart_order,
            news_updated_at,
            raw_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
            jersey_number = COALESCE(excluded.jersey_number, players.jersey_number),
            height = COALESCE(excluded.height, players.height),
            weight = COALESCE(excluded.weight, players.weight),
            college = COALESCE(excluded.college, players.college),
            birth_date = COALESCE(excluded.birth_date, players.birth_date),
            depth_chart_position = COALESCE(excluded.depth_chart_position, players.depth_chart_position),
            depth_chart_order = COALESCE(excluded.depth_chart_order, players.depth_chart_order),
            news_updated_at = COALESCE(excluded.news_updated_at, players.news_updated_at),
            raw_json = COALESCE(excluded.raw_json, players.raw_json),
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
            optional_str_value(payload.get("jersey_number")),
            optional_str_value(payload.get("height")),
            optional_str_value(payload.get("weight")),
            optional_str_value(payload.get("college")),
            optional_str_value(payload.get("birth_date")),
            optional_str_value(payload.get("depth_chart_position")),
            optional_int_value(payload.get("depth_chart_order")),
            optional_str_value(payload.get("news_updated_at")),
            payload.get("raw_json"),
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


def count_players_by_source(conn: sqlite3.Connection, source_name: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM players WHERE source = ?",
        (source_name,),
    ).fetchone()
    return int(row["count"] or 0)


def latest_import_run(conn: sqlite3.Connection, source_name: str, import_type: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM source_import_runs
        WHERE source_name = ? AND import_type = ?
        ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
        LIMIT 1
        """,
        (source_name, import_type),
    ).fetchone()


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
    team: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    jersey_number: str | None = None,
    active: int | None = None,
    limit: int | None = None,
    offset: int = 0,
    sort: str | None = None,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[Any] = []
    if position:
        clauses.append("position = ?")
        params.append(normalize_position(position))
    if team:
        clauses.append("team = ?")
        params.append(normalize_team(team))
    if search:
        clauses.append("(normalized_name LIKE ? OR full_name LIKE ?)")
        normalized_search = f"%{normalize_name(search)}%"
        params.extend([normalized_search, f"%{search}%"])
    if age_min is not None:
        clauses.append("age >= ?")
        params.append(age_min)
    if age_max is not None:
        clauses.append("age <= ?")
        params.append(age_max)
    if jersey_number:
        clauses.append("jersey_number = ?")
        params.append(str(jersey_number))
    if active is not None:
        clauses.append("active = ?")
        params.append(active)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    order_sql = player_sort_sql(sort)
    limit_sql = " LIMIT ? OFFSET ?" if limit else ""
    if limit:
        params.extend([limit, offset])
    return conn.execute(
        f"""
        SELECT *
        FROM players
        {where}
        ORDER BY {order_sql}
        {limit_sql}
        """,
        params,
    ).fetchall()


def count_player_search(
    conn: sqlite3.Connection,
    position: str | None = None,
    search: str | None = None,
    team: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    jersey_number: str | None = None,
    active: int | None = None,
) -> int:
    clauses: list[str] = []
    params: list[Any] = []
    if position:
        clauses.append("position = ?")
        params.append(normalize_position(position))
    if team:
        clauses.append("team = ?")
        params.append(normalize_team(team))
    if search:
        clauses.append("(normalized_name LIKE ? OR full_name LIKE ?)")
        normalized_search = f"%{normalize_name(search)}%"
        params.extend([normalized_search, f"%{search}%"])
    if age_min is not None:
        clauses.append("age >= ?")
        params.append(age_min)
    if age_max is not None:
        clauses.append("age <= ?")
        params.append(age_max)
    if jersey_number:
        clauses.append("jersey_number = ?")
        params.append(str(jersey_number))
    if active is not None:
        clauses.append("active = ?")
        params.append(active)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute(f"SELECT COUNT(*) AS count FROM players {where}", params).fetchone()
    return int(row["count"] or 0)


def player_sort_sql(sort: str | None) -> str:
    sorts = {
        "name": "full_name",
        "position": "position, COALESCE(search_rank, 999999), full_name",
        "team": "team, COALESCE(search_rank, 999999), full_name",
        "age": "age IS NULL, age, full_name",
        "rank": "COALESCE(search_rank, 999999), full_name",
    }
    return sorts.get(sort or "rank", sorts["rank"])


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
        "jersey_number": getter("jersey_number"),
        "height": getter("height"),
        "weight": getter("weight"),
        "college": getter("college"),
        "birth_date": getter("birth_date"),
        "depth_chart_position": getter("depth_chart_position"),
        "depth_chart_order": getter("depth_chart_order"),
        "news_updated_at": getter("news_updated_at"),
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


def optional_str_value(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def keeper_from_row(row: sqlite3.Row) -> Keeper:
    keys = row.keys()
    return Keeper(
        player_id=row["player_id"],
        team_name=row["team_name"],
        round=row["round"],
        pick_no=row["pick_no"],
        league_id=row["league_id"] if "league_id" in keys else None,
        roster_id=row["roster_id"] if "roster_id" in keys else None,
        sleeper_user_id=row["sleeper_user_id"] if "sleeper_user_id" in keys else None,
    )


def get_keepers(conn: sqlite3.Connection, league_id: str | None = None) -> list[Keeper]:
    if league_id:
        rows = conn.execute(
            """
            SELECT * FROM keepers
            WHERE league_id = ? OR league_id IS NULL
            ORDER BY COALESCE(pick_no, 9999), team_name
            """,
            (league_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM keepers ORDER BY COALESCE(pick_no, 9999), team_name"
        ).fetchall()
    return [keeper_from_row(row) for row in rows]


def upsert_keeper(conn: sqlite3.Connection, keeper: Keeper) -> None:
    if keeper.league_id and keeper.roster_id is not None:
        conn.execute(
            "DELETE FROM keepers WHERE league_id = ? AND roster_id = ?",
            (keeper.league_id, keeper.roster_id),
        )
    conn.execute(
        """
        INSERT INTO keepers (player_id, team_name, round, pick_no, league_id, roster_id, sleeper_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id, team_name) DO UPDATE SET
            round = excluded.round,
            pick_no = excluded.pick_no,
            league_id = excluded.league_id,
            roster_id = excluded.roster_id,
            sleeper_user_id = excluded.sleeper_user_id
        """,
        (
            keeper.player_id,
            keeper.team_name,
            keeper.round,
            keeper.pick_no,
            keeper.league_id,
            keeper.roster_id,
            keeper.sleeper_user_id,
        ),
    )
    conn.commit()


def delete_keeper(conn: sqlite3.Connection, player_id: str, team_name: str) -> None:
    conn.execute(
        "DELETE FROM keepers WHERE player_id = ? AND team_name = ?",
        (player_id, team_name),
    )
    conn.commit()


def delete_keeper_by_roster(conn: sqlite3.Connection, league_id: str, roster_id: int) -> None:
    conn.execute(
        "DELETE FROM keepers WHERE league_id = ? AND roster_id = ?",
        (league_id, roster_id),
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
