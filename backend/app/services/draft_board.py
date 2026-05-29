"""Draft board assembly for imported Sleeper leagues."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .availability import estimate_availability


def get_draft_board(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    league = get_league(conn, league_id)
    draft = latest_draft(conn, league_id)
    draft_id = draft["draft_id"] if draft else None
    managers = get_managers(conn, league_id, draft_id)
    teams = len(managers) or int((league or {}).get("total_rosters") or 10)
    rounds = draft_rounds(conn, league_id, draft)
    draft_order = get_draft_order(conn, league_id, managers, draft_id)
    picks_by_no = get_picks_by_no(conn, league_id, draft_id)
    ownership_by_no = get_pick_ownership_by_no(conn, league_id, draft_id)
    board: list[dict[str, Any]] = []
    for round_no in range(1, rounds + 1):
        row_picks: list[dict[str, Any]] = []
        for draft_slot in range(1, teams + 1):
            pick_no = snake_pick_no(round_no, draft_slot, teams)
            slot = draft_order[draft_slot - 1] if draft_slot - 1 < len(draft_order) else {}
            existing = picks_by_no.get(pick_no)
            ownership = ownership_by_no.get(pick_no, {})
            original_roster_id = ownership.get("original_roster_id") or slot.get("roster_id")
            current_roster_id = ownership.get("current_roster_id") or (existing or {}).get("roster_id") or original_roster_id
            is_traded = bool(ownership.get("source") == "traded_pick" or (original_roster_id and current_roster_id and original_roster_id != current_roster_id))
            row_picks.append(
                {
                    "pick_no": pick_no,
                    "round": round_no,
                    "draft_slot": draft_slot,
                    "manager_name": (existing or {}).get("manager_name") or ownership.get("manager_name") or slot.get("manager_name"),
                    "roster_id": current_roster_id,
                    "original_roster_id": original_roster_id,
                    "current_roster_id": current_roster_id,
                    "player": (existing or {}).get("player"),
                    "is_mine": bool(ownership.get("is_mine") or (slot.get("is_me") and not is_traded)),
                    "is_traded": is_traded,
                    "is_keeper": bool((existing or {}).get("is_keeper")),
                }
            )
        board.append({"round": round_no, "picks": row_picks})

    my_team = next((manager for manager in managers if manager.get("is_me")), None)
    my_picks = get_my_picks(conn, league_id, draft_id)
    for pick in my_picks[:5]:
        pick["likely_available"] = estimate_availability(conn, league_id, int(pick["pick_no"]), limit=3)["likely_available"]
    return {
        "league": league,
        "active_draft_id": draft_id,
        "managers": managers,
        "rounds": list(range(1, rounds + 1)),
        "my_team": my_team,
        "my_picks": my_picks,
        "draft_mapping": draft_order,
        "traded_picks": get_traded_picks(conn, league_id, draft_id),
        "warnings": [] if ownership_by_no else ["Future pick ownership was inferred from the default snake order."],
        "draft_order": draft_order,
        "board": board,
    }


def get_league(conn: sqlite3.Connection, league_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM sleeper_leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not row:
        return None
    return {
        "league_id": row["league_id"],
        "name": row["name"],
        "season": row["season"],
        "status": row["status"],
        "total_rosters": row["total_rosters"],
        "previous_league_id": row["previous_league_id"],
    }


def get_managers(conn: sqlite3.Connection, league_id: str, draft_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    draft_join_filter = ""
    if draft_id:
        draft_join_filter = "AND (ds.draft_id = ? OR ds.draft_id IS NULL)"
        params.append(draft_id)
    params.append(league_id)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT lm.*, ds.draft_slot
            FROM league_managers lm
            LEFT JOIN draft_slots ds ON ds.league_id = lm.league_id AND ds.roster_id = lm.roster_id {draft_join_filter}
            WHERE lm.league_id = ?
            ORDER BY COALESCE(ds.draft_slot, 9999), lm.id
            """,
            params,
        ).fetchall()
    ]


def latest_draft(conn: sqlite3.Connection, league_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM league_drafts WHERE league_id = ? ORDER BY season DESC, id DESC LIMIT 1",
        (league_id,),
    ).fetchone()


def draft_rounds(conn: sqlite3.Connection, league_id: str, draft: sqlite3.Row | None) -> int:
    if draft:
        settings = json.loads(draft["settings_json"] or "{}")
        if settings.get("rounds"):
            return int(settings["rounds"])
    if draft:
        row = conn.execute(
            "SELECT MAX(round) AS max_round FROM user_draft_picks WHERE league_id = ? AND draft_id = ?",
            (league_id, draft["draft_id"]),
        ).fetchone()
    else:
        row = conn.execute("SELECT MAX(round) AS max_round FROM user_draft_picks WHERE league_id = ?", (league_id,)).fetchone()
    return int(row["max_round"] or 16)


def snake_pick_no(round_no: int, draft_slot: int, teams: int) -> int:
    slot = draft_slot if round_no % 2 == 1 else teams - draft_slot + 1
    return (round_no - 1) * teams + slot


def get_draft_order(
    conn: sqlite3.Connection,
    league_id: str,
    managers: list[dict[str, Any]],
    draft_id: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [league_id]
    draft_filter = ""
    if draft_id:
        draft_filter = "AND (ds.draft_id = ? OR ds.draft_id IS NULL)"
        params.append(draft_id)
    slots = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT ds.*, lm.is_me
            FROM draft_slots ds
            LEFT JOIN league_managers lm ON lm.league_id = ds.league_id AND lm.roster_id = ds.roster_id
            WHERE ds.league_id = ? {draft_filter}
            ORDER BY ds.draft_slot
            """,
            params,
        ).fetchall()
    ]
    if slots:
        return slots
    return [
        {
            "draft_slot": index + 1,
            "roster_id": manager.get("roster_id"),
            "manager_name": manager.get("team_name") or manager.get("display_name"),
            "is_me": manager.get("is_me"),
        }
        for index, manager in enumerate(managers)
    ]


def get_picks_by_no(conn: sqlite3.Connection, league_id: str, draft_id: str | None) -> dict[int, dict[str, Any]]:
    params: list[Any] = [league_id]
    draft_filter = ""
    if draft_id:
        draft_filter = "AND p.draft_id = ?"
        params.append(draft_id)
    rows = conn.execute(
        f"""
        SELECT p.*, lm.team_name, lm.display_name
        FROM league_draft_picks p
        LEFT JOIN league_managers lm ON lm.league_id = p.league_id AND lm.roster_id = p.roster_id
        WHERE p.league_id = ? {draft_filter}
        """,
        params,
    ).fetchall()
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        result[int(row["pick_no"])] = {
            "roster_id": row["roster_id"],
            "manager_name": row["team_name"] or row["display_name"],
            "is_keeper": row["is_keeper"],
            "player": {
                "id": row["player_id"],
                "internal_player_id": row["player_id"],
                "sleeper_id": row["sleeper_player_id"],
                "name": row["player_name"],
                "full_name": row["player_name"],
                "position": row["position"],
                "team": row["team"],
            } if row["player_id"] or row["player_name"] else None,
        }
    return result


def get_pick_ownership_by_no(conn: sqlite3.Connection, league_id: str, draft_id: str | None) -> dict[int, dict[str, Any]]:
    params: list[Any] = [league_id]
    draft_filter = ""
    if draft_id:
        draft_filter = "AND (draft_id = ? OR draft_id IS NULL)"
        params.append(draft_id)
    rows = conn.execute(
        f"""
        SELECT *
        FROM user_draft_picks
        WHERE league_id = ? {draft_filter}
        """,
        params,
    ).fetchall()
    return {int(row["pick_no"]): dict(row) for row in rows}


def get_traded_picks(conn: sqlite3.Connection, league_id: str, draft_id: str | None) -> list[dict[str, Any]]:
    params: list[Any] = [league_id]
    draft_filter = ""
    if draft_id:
        draft_filter = "AND (draft_id = ? OR draft_id IS NULL)"
        params.append(draft_id)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT *
            FROM league_traded_picks
            WHERE league_id = ? {draft_filter}
            ORDER BY season, round, roster_id, id
            """,
            params,
        ).fetchall()
    ]


def get_my_picks(conn: sqlite3.Connection, league_id: str, draft_id: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = [league_id]
    draft_filter = ""
    if draft_id:
        draft_filter = "AND (draft_id = ? OR draft_id IS NULL)"
        params.append(draft_id)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT *
            FROM user_draft_picks
            WHERE league_id = ? {draft_filter} AND is_mine = 1
            ORDER BY pick_no
            """,
            params,
        ).fetchall()
    ]
