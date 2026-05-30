"""Round 15 keeper assignment for league draft boards."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db
from ..models import Keeper
from .draft_board import latest_draft
from .draft_room import ensure_live_draft, get_draft_state


DEFAULT_KEEPER_ROUND = 15


def keeper_pick_no(round_no: int, draft_slot: int, teams: int) -> int:
    """Snake draft pick number for an odd round (Round 15 uses natural slot order)."""
    if round_no % 2 == 0:
        slot = teams - draft_slot + 1
    else:
        slot = draft_slot
    return (round_no - 1) * teams + slot


def league_team_count(conn: sqlite3.Connection, league_id: str) -> int:
    league = conn.execute(
        "SELECT total_rosters FROM sleeper_leagues WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    if league and league["total_rosters"]:
        return int(league["total_rosters"])
    settings = db.get_league_settings(conn)
    count = conn.execute(
        "SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?",
        (league_id,),
    ).fetchone()["count"]
    return int(count or settings.teams or 10)


def manager_for_roster(conn: sqlite3.Connection, league_id: str, roster_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM league_managers WHERE league_id = ? AND roster_id = ?",
        (league_id, roster_id),
    ).fetchone()


def draft_slot_for_roster(conn: sqlite3.Connection, league_id: str, roster_id: int) -> int:
    draft = latest_draft(conn, league_id)
    draft_id = draft["draft_id"] if draft else None
    params: list[Any] = [league_id, roster_id]
    draft_filter = ""
    if draft_id:
        draft_filter = "AND (draft_id = ? OR draft_id IS NULL)"
        params.append(draft_id)
    row = conn.execute(
        f"""
        SELECT draft_slot FROM draft_slots
        WHERE league_id = ? AND roster_id = ? {draft_filter}
        ORDER BY draft_slot
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row and row["draft_slot"]:
        return int(row["draft_slot"])
    managers = conn.execute(
        "SELECT roster_id FROM league_managers WHERE league_id = ? ORDER BY id",
        (league_id,),
    ).fetchall()
    for index, manager in enumerate(managers, start=1):
        if int(manager["roster_id"] or 0) == roster_id:
            return index
    raise ValueError(f"No draft slot found for roster {roster_id}")


def resolve_roster_id(
    conn: sqlite3.Connection,
    league_id: str,
    roster_id: int | None,
    sleeper_user_id: str | None,
) -> int:
    if roster_id is not None:
        return int(roster_id)
    if sleeper_user_id:
        row = conn.execute(
            "SELECT roster_id FROM league_managers WHERE league_id = ? AND sleeper_user_id = ?",
            (league_id, sleeper_user_id),
        ).fetchone()
        if row and row["roster_id"] is not None:
            return int(row["roster_id"])
    raise ValueError("roster_id or sleeper_user_id is required")


def add_keeper(
    conn: sqlite3.Connection,
    league_id: str,
    player_id: str,
    roster_id: int | None = None,
    sleeper_user_id: str | None = None,
    round_no: int | None = None,
    pick_no: int | None = None,
) -> dict[str, Any]:
    player = db.get_player_row(conn, player_id)
    if not player:
        raise ValueError(f"Unknown player_id: {player_id}")

    resolved_roster = resolve_roster_id(conn, league_id, roster_id, sleeper_user_id)
    manager = manager_for_roster(conn, league_id, resolved_roster)
    if not manager:
        raise ValueError(f"Unknown roster_id {resolved_roster} for league {league_id}")

    teams = league_team_count(conn, league_id)
    keeper_round = int(round_no or DEFAULT_KEEPER_ROUND)
    draft_slot = draft_slot_for_roster(conn, league_id, resolved_roster)
    target_pick = int(pick_no) if pick_no is not None else keeper_pick_no(keeper_round, draft_slot, teams)

    team_name = manager["team_name"] or manager["display_name"] or f"Roster {resolved_roster}"
    keeper = Keeper(
        player_id=player_id,
        team_name=team_name,
        round=keeper_round,
        pick_no=target_pick,
        league_id=league_id,
        roster_id=resolved_roster,
        sleeper_user_id=manager["sleeper_user_id"],
    )
    db.upsert_keeper(conn, keeper)
    save_keeper_board_pick(conn, league_id, keeper_round, draft_slot, target_pick, resolved_roster, player, manager)

    payload = {
        "keeper": enrich_keeper_row(conn, keeper),
        "keepers": list_keepers(conn, league_id),
    }
    payload["draft_state"] = get_draft_state(conn, league_id)
    return payload


def save_keeper_board_pick(
    conn: sqlite3.Connection,
    league_id: str,
    round_no: int,
    draft_slot: int,
    pick_no: int,
    roster_id: int,
    player: sqlite3.Row,
    manager: sqlite3.Row,
) -> None:
    draft_id = ensure_live_draft(conn, league_id)
    conn.execute(
        """
        INSERT INTO league_draft_picks (
            league_id, draft_id, pick_no, round, draft_slot, roster_id, picked_by,
            player_id, sleeper_player_id, player_name, position, team, is_keeper, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(draft_id, pick_no) DO UPDATE SET
            round = excluded.round,
            draft_slot = excluded.draft_slot,
            roster_id = excluded.roster_id,
            picked_by = excluded.picked_by,
            player_id = excluded.player_id,
            sleeper_player_id = excluded.sleeper_player_id,
            player_name = excluded.player_name,
            position = excluded.position,
            team = excluded.team,
            is_keeper = 1,
            raw_json = excluded.raw_json
        """,
        (
            league_id,
            draft_id,
            pick_no,
            round_no,
            draft_slot,
            roster_id,
            manager["sleeper_user_id"],
            player["internal_player_id"],
            player["sleeper_id"],
            player["full_name"],
            player["position"],
            player["team"],
            json.dumps({"source": "keeper", "manager_name": manager["team_name"] or manager["display_name"]}),
        ),
    )
    conn.commit()


def remove_keeper(
    conn: sqlite3.Connection,
    league_id: str,
    player_id: str,
    roster_id: int | None = None,
    team_name: str | None = None,
) -> dict[str, Any]:
    if roster_id is not None:
        row = conn.execute(
            "SELECT * FROM keepers WHERE league_id = ? AND roster_id = ? AND player_id = ?",
            (league_id, roster_id, player_id),
        ).fetchone()
        if not row and team_name:
            db.delete_keeper(conn, player_id, team_name)
        elif row:
            db.delete_keeper_by_roster(conn, league_id, int(roster_id))
        else:
            raise ValueError("Keeper not found")
        pick_no = row["pick_no"] if row else None
    elif team_name:
        row = conn.execute(
            "SELECT pick_no FROM keepers WHERE player_id = ? AND team_name = ?",
            (player_id, team_name),
        ).fetchone()
        db.delete_keeper(conn, player_id, team_name)
        pick_no = row["pick_no"] if row else None
    else:
        raise ValueError("roster_id or team_name is required")

    if pick_no:
        draft = latest_draft(conn, league_id)
        if draft:
            conn.execute(
                """
                DELETE FROM league_draft_picks
                WHERE league_id = ? AND draft_id = ? AND pick_no = ? AND is_keeper = 1
                """,
                (league_id, draft["draft_id"], pick_no),
            )
            conn.commit()

    return {
        "keepers": list_keepers(conn, league_id),
        "draft_state": get_draft_state(conn, league_id),
    }


def list_keepers(conn: sqlite3.Connection, league_id: str | None = None) -> list[dict[str, Any]]:
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
    return [enrich_keeper_row(conn, db.keeper_from_row(row)) for row in rows]


def enrich_keeper_row(conn: sqlite3.Connection, keeper: Keeper) -> dict[str, Any]:
    data = keeper.to_dict()
    data["player"] = db.player_row_to_api(db.get_player_row(conn, keeper.player_id))
    if keeper.league_id and keeper.roster_id is not None:
        manager = manager_for_roster(conn, keeper.league_id, int(keeper.roster_id))
        if manager:
            data["manager"] = {
                "roster_id": manager["roster_id"],
                "sleeper_user_id": manager["sleeper_user_id"],
                "display_name": manager["display_name"],
                "team_name": manager["team_name"],
            }
    return data
