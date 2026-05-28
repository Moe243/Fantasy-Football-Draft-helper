"""Safe normalization and player matching helpers."""

from __future__ import annotations

import re
import sqlite3
from typing import Any


FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()

TEAM_ALIASES = {
    "ARI": "ARI",
    "ARZ": "ARI",
    "ARIZONA CARDINALS": "ARI",
    "ATL": "ATL",
    "ATLANTA FALCONS": "ATL",
    "BAL": "BAL",
    "BALTIMORE RAVENS": "BAL",
    "BUF": "BUF",
    "BUFFALO BILLS": "BUF",
    "CAR": "CAR",
    "CAROLINA PANTHERS": "CAR",
    "CHI": "CHI",
    "CHICAGO BEARS": "CHI",
    "CIN": "CIN",
    "CINCINNATI BENGALS": "CIN",
    "CLE": "CLE",
    "CLEVELAND BROWNS": "CLE",
    "DAL": "DAL",
    "DALLAS COWBOYS": "DAL",
    "DEN": "DEN",
    "DENVER BRONCOS": "DEN",
    "DET": "DET",
    "DETROIT LIONS": "DET",
    "GB": "GB",
    "GBP": "GB",
    "GREEN BAY PACKERS": "GB",
    "HOU": "HOU",
    "HOUSTON TEXANS": "HOU",
    "IND": "IND",
    "INDIANAPOLIS COLTS": "IND",
    "JAC": "JAX",
    "JAX": "JAX",
    "JACKSONVILLE JAGUARS": "JAX",
    "KC": "KC",
    "KAN": "KC",
    "KANSAS CITY CHIEFS": "KC",
    "LAC": "LAC",
    "LA CHARGERS": "LAC",
    "LOS ANGELES CHARGERS": "LAC",
    "LAR": "LAR",
    "LA RAMS": "LAR",
    "LOS ANGELES RAMS": "LAR",
    "LV": "LV",
    "LVR": "LV",
    "LAS VEGAS RAIDERS": "LV",
    "MIA": "MIA",
    "MIAMI DOLPHINS": "MIA",
    "MIN": "MIN",
    "MINNESOTA VIKINGS": "MIN",
    "NE": "NE",
    "NEP": "NE",
    "NEW ENGLAND PATRIOTS": "NE",
    "NO": "NO",
    "NOR": "NO",
    "NEW ORLEANS SAINTS": "NO",
    "NYG": "NYG",
    "NEW YORK GIANTS": "NYG",
    "NYJ": "NYJ",
    "NEW YORK JETS": "NYJ",
    "OAK": "LV",
    "PHI": "PHI",
    "PHILADELPHIA EAGLES": "PHI",
    "PIT": "PIT",
    "PITTSBURGH STEELERS": "PIT",
    "SEA": "SEA",
    "SEATTLE SEAHAWKS": "SEA",
    "SF": "SF",
    "SFO": "SF",
    "SAN FRANCISCO 49ERS": "SF",
    "TB": "TB",
    "TAMPA BAY BUCCANEERS": "TB",
    "TEN": "TEN",
    "TENNESSEE TITANS": "TEN",
    "WAS": "WAS",
    "WSH": "WAS",
    "WASHINGTON COMMANDERS": "WAS",
    "WASHINGTON FOOTBALL TEAM": "WAS",
}

DEFENSE_NAME_TO_TEAM = {
    normalize_key(name): code for name, code in TEAM_ALIASES.items() if len(name) > 3
}


def normalize_name(name: str) -> str:
    text = str(name or "").lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_team(team: str) -> str:
    key = normalize_key(team)
    return TEAM_ALIASES.get(key, key if len(key) <= 3 else "")


def normalize_position(position: str) -> str:
    value = str(position or "").upper().strip()
    if value in {"DST", "D/ST", "DEFENSE"}:
        return "DEF"
    return value if value in FANTASY_POSITIONS else value


def normalize_defense_name(name: str) -> str | None:
    key = normalize_key(name)
    team = DEFENSE_NAME_TO_TEAM.get(key)
    if team:
        return f"{team} Defense"
    if key in TEAM_ALIASES:
        return f"{TEAM_ALIASES[key]} Defense"
    return None


def match_player(
    conn: sqlite3.Connection,
    name: str,
    position: str | None = None,
    team: str | None = None,
    source_player_id: str | None = None,
    source_name: str | None = None,
) -> sqlite3.Row | None:
    normalized_name = normalize_name(name)
    normalized_position = normalize_position(position or "")
    normalized_team = normalize_team(team or "")

    if source_player_id and source_name:
        source_key = source_name.lower()
        if source_key == "sleeper":
            row = conn.execute("SELECT * FROM players WHERE sleeper_id = ?", (source_player_id,)).fetchone()
            if row:
                return row
        if source_key == "espn":
            row = conn.execute("SELECT * FROM players WHERE espn_id = ?", (source_player_id,)).fetchone()
            if row:
                return row
        if source_key == "fantasypros":
            row = conn.execute("SELECT * FROM players WHERE fantasypros_id = ?", (source_player_id,)).fetchone()
            if row:
                return row

    if normalized_name and normalized_position:
        row = conn.execute(
            "SELECT * FROM players WHERE normalized_name = ? AND position = ?",
            (normalized_name, normalized_position),
        ).fetchone()
        if row:
            return row

    if normalized_name and normalized_team:
        row = conn.execute(
            "SELECT * FROM players WHERE normalized_name = ? AND team = ?",
            (normalized_name, normalized_team),
        ).fetchone()
        if row:
            return row

    if normalized_position == "DEF":
        defense_name = normalize_defense_name(name)
        if defense_name:
            defense_team = normalize_team(defense_name.replace(" Defense", ""))
            row = conn.execute(
                "SELECT * FROM players WHERE position = 'DEF' AND team = ?",
                (defense_team,),
            ).fetchone()
            if row:
                return row

    return safe_contains_match(conn, normalized_name, normalized_position, normalized_team)


def safe_contains_match(
    conn: sqlite3.Connection,
    normalized_name: str,
    normalized_position: str | None,
    normalized_team: str | None,
) -> sqlite3.Row | None:
    if not normalized_name or len(normalized_name) < 5:
        return None
    clauses = ["(normalized_name LIKE ? OR ? LIKE '%' || normalized_name || '%')"]
    params: list[Any] = [f"%{normalized_name}%", normalized_name]
    if normalized_position:
        clauses.append("position = ?")
        params.append(normalized_position)
    if normalized_team:
        clauses.append("team = ?")
        params.append(normalized_team)
    rows = conn.execute(
        f"SELECT * FROM players WHERE {' AND '.join(clauses)} LIMIT 2",
        params,
    ).fetchall()
    return rows[0] if len(rows) == 1 else None
