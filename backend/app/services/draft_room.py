"""Central draft-room state and pick actions."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any

from .. import db
from ..models import DraftPick
from .availability import drafted_player_ids, estimate_availability
from .draft_board import get_draft_board, latest_draft
from .practice_draft import (
    active_practice,
    active_practice_by_id,
    make_pick_at,
    overlay_practice_picks,
    recalculate_current_pick,
    remove_practice_pick,
)
from .recommendations import database_draft_recommendations, desired_position_counts


def get_draft_state(
    conn: sqlite3.Connection,
    league_id: str,
    position: str | None = None,
    search: str | None = None,
    last_pick: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = db.get_league_settings(conn)
    keepers = db.get_keepers(conn)
    practice = active_practice(conn, league_id)
    if practice:
        recalculate_current_pick(conn, league_id, int(practice["id"]))
        practice = active_practice(conn, league_id)

    board_data = get_draft_board(conn, league_id)
    practice_picks = get_practice_picks(conn, int(practice["id"])) if practice else []
    if practice:
        overlay_practice_picks(conn, board_data, practice_picks)

    current_pick = int(practice["current_pick"]) if practice else first_open_pick(board_data)
    current_pick_cell = mark_current_pick(board_data, current_pick)
    board_picks = board_to_draft_picks(board_data)
    best_available = database_draft_recommendations(
        conn,
        settings,
        keepers,
        board_picks,
        limit=18,
        manager="me",
        position=position,
        search=search,
        hide_drafted=True,
        hide_keepers=True,
        current_pick_override=current_pick,
    )
    my_picks = enrich_my_picks(conn, league_id, board_data.get("my_picks") or [], current_pick)
    likely_available = []
    next_my_pick = next((pick for pick in my_picks if int(pick["pick_no"]) >= current_pick), None)
    if next_my_pick:
        likely_available = next_my_pick.get("likely_available") or []

    return {
        "league": board_data.get("league"),
        "active_draft_id": board_data.get("active_draft_id"),
        "managers": board_data.get("managers") or [],
        "rounds": board_data.get("rounds") or [],
        "draft_order": board_data.get("draft_order") or [],
        "draft_mapping": board_data.get("draft_mapping") or board_data.get("draft_order") or [],
        "traded_picks": board_data.get("traded_picks") or [],
        "warnings": board_data.get("warnings") or [],
        "my_team": board_data.get("my_team"),
        "current_pick": current_pick,
        "current_pick_team": current_pick_cell,
        "is_my_pick": bool(current_pick_cell and current_pick_cell.get("is_mine")),
        "board": board_data.get("board") or [],
        "my_picks": my_picks,
        "best_available": best_available,
        "likely_available": likely_available,
        "roster_needs": roster_needs(settings, board_data),
        "practice": dict(practice) if practice else None,
        "practice_picks": practice_picks,
        "last_pick": last_pick,
    }


def make_draft_pick(
    conn: sqlite3.Connection,
    league_id: str,
    player_id: str,
    pick_no: int | None = None,
    practice_draft_id: int | None = None,
) -> dict[str, Any]:
    player = db.get_player_row(conn, player_id)
    if not player:
        raise ValueError(f"Unknown player_id: {player_id}")
    practice = active_practice_by_id(conn, league_id, practice_draft_id) if practice_draft_id else active_practice(conn, league_id)
    if player_id in drafted_player_ids(conn, league_id):
        raise ValueError("That player has already been drafted or kept")

    if practice:
        target_pick = int(pick_no or practice["current_pick"] or 1)
        make_pick_at(conn, league_id, player_id, target_pick, int(practice["id"]), source="user")
        last_pick = pick_summary(conn, league_id, target_pick, player_id, "practice")
    else:
        board_data = get_draft_board(conn, league_id)
        target_pick = int(pick_no or first_open_pick(board_data))
        cell = find_pick_cell(board_data, target_pick)
        if not cell:
            raise ValueError(f"Pick {target_pick} is outside the draft board")
        if cell.get("player"):
            raise ValueError(f"Pick {target_pick} already has a player")
        save_live_pick(conn, league_id, target_pick, cell, player)
        last_pick = pick_summary(conn, league_id, target_pick, player_id, "live")

    return get_draft_state(conn, league_id, last_pick=last_pick)


def remove_draft_pick(conn: sqlite3.Connection, league_id: str, pick_no: int) -> dict[str, Any]:
    practice = active_practice(conn, league_id)
    removed = False
    if practice:
        removed = remove_practice_pick(conn, league_id, pick_no, int(practice["id"]))
    if not removed:
        draft = latest_draft(conn, league_id)
        if draft:
            cursor = conn.execute(
                "DELETE FROM league_draft_picks WHERE league_id = ? AND draft_id = ? AND pick_no = ?",
                (league_id, draft["draft_id"], pick_no),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM league_draft_picks WHERE league_id = ? AND pick_no = ?",
                (league_id, pick_no),
            )
        conn.commit()
        removed = cursor.rowcount > 0
    if not removed:
        raise ValueError(f"No pick found at {pick_no}")
    return get_draft_state(conn, league_id)


def save_live_pick(
    conn: sqlite3.Connection,
    league_id: str,
    pick_no: int,
    cell: dict[str, Any],
    player: sqlite3.Row,
) -> None:
    draft_id = ensure_live_draft(conn, league_id)
    manager = manager_for_roster(conn, league_id, cell.get("roster_id"))
    conn.execute(
        """
        INSERT INTO league_draft_picks (
            league_id, draft_id, pick_no, round, draft_slot, roster_id, picked_by,
            player_id, sleeper_player_id, player_name, position, team, is_keeper, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(draft_id, pick_no) DO UPDATE SET
            roster_id = excluded.roster_id,
            picked_by = excluded.picked_by,
            player_id = excluded.player_id,
            sleeper_player_id = excluded.sleeper_player_id,
            player_name = excluded.player_name,
            position = excluded.position,
            team = excluded.team,
            raw_json = excluded.raw_json
        """,
        (
            league_id,
            draft_id,
            pick_no,
            cell.get("round"),
            cell.get("draft_slot"),
            cell.get("roster_id"),
            manager.get("sleeper_user_id") if manager else None,
            player["internal_player_id"],
            player["sleeper_id"],
            player["full_name"],
            player["position"],
            player["team"],
            json.dumps({"source": "draft_room", "manager_name": cell.get("manager_name")}),
        ),
    )
    conn.commit()


def ensure_live_draft(conn: sqlite3.Connection, league_id: str) -> str:
    draft = latest_draft(conn, league_id)
    if draft:
        return draft["draft_id"]
    draft_id = f"{league_id}_manual"
    conn.execute(
        """
        INSERT OR IGNORE INTO league_drafts (league_id, draft_id, status, type, settings_json, raw_json)
        VALUES (?, ?, 'local', 'snake', '{}', '{}')
        """,
        (league_id, draft_id),
    )
    conn.commit()
    return draft_id


def first_open_pick(board_data: dict[str, Any]) -> int:
    open_picks = [
        int(cell["pick_no"])
        for row in board_data.get("board") or []
        for cell in row.get("picks") or []
        if not cell.get("player")
    ]
    return min(open_picks) if open_picks else 1


def find_pick_cell(board_data: dict[str, Any], pick_no: int) -> dict[str, Any] | None:
    for row in board_data.get("board") or []:
        for cell in row.get("picks") or []:
            if int(cell["pick_no"]) == int(pick_no):
                return cell
    return None


def mark_current_pick(board_data: dict[str, Any], current_pick: int) -> dict[str, Any] | None:
    current_cell = None
    for row in board_data.get("board") or []:
        for cell in row.get("picks") or []:
            is_current = int(cell["pick_no"]) == int(current_pick)
            cell["is_current_pick"] = is_current
            cell["is_my_current_pick"] = bool(is_current and cell.get("is_mine"))
            if is_current:
                current_cell = cell
    return current_cell


def board_to_draft_picks(board_data: dict[str, Any]) -> list[DraftPick]:
    picks: list[DraftPick] = []
    for row in board_data.get("board") or []:
        for cell in row.get("picks") or []:
            player = cell.get("player")
            if not player:
                continue
            player_id = player.get("internal_player_id") or player.get("id")
            if not player_id:
                continue
            picks.append(
                DraftPick(
                    pick_no=int(cell["pick_no"]),
                    player_id=player_id,
                    manager="me" if cell.get("is_mine") else "opponent",
                    source="draft_room",
                )
            )
    return picks


def enrich_my_picks(
    conn: sqlite3.Connection,
    league_id: str,
    my_picks: list[dict[str, Any]],
    current_pick: int,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for pick in my_picks:
        item = dict(pick)
        item["is_past"] = int(item["pick_no"]) < current_pick
        item["is_current"] = int(item["pick_no"]) == current_pick
        if int(item["pick_no"]) >= current_pick:
            item["likely_available"] = estimate_availability(conn, league_id, int(item["pick_no"]), limit=3)["likely_available"]
        else:
            item["likely_available"] = []
        enriched.append(item)
    return enriched


def roster_needs(settings, board_data: dict[str, Any]) -> list[dict[str, Any]]:
    desired = desired_position_counts(settings)
    counts: Counter[str] = Counter()
    for row in board_data.get("board") or []:
        for cell in row.get("picks") or []:
            player = cell.get("player")
            if cell.get("is_mine") and player:
                counts[player.get("position") or "UNK"] += 1
    needs: list[dict[str, Any]] = []
    for position in ("QB", "RB", "WR", "TE", "DEF", "K"):
        target = int(desired.get(position, 0))
        current = int(counts.get(position, 0))
        needs.append(
            {
                "position": position,
                "current": current,
                "target": target,
                "remaining": max(0, target - current),
                "status": "Filled" if current >= target else "Need",
            }
        )
    return needs


def get_practice_picks(conn: sqlite3.Connection, practice_draft_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM practice_draft_picks WHERE practice_draft_id = ? ORDER BY pick_no",
            (practice_draft_id,),
        ).fetchall()
    ]


def manager_for_roster(conn: sqlite3.Connection, league_id: str, roster_id: Any) -> dict[str, Any] | None:
    if roster_id is None:
        return None
    row = conn.execute(
        "SELECT * FROM league_managers WHERE league_id = ? AND roster_id = ?",
        (league_id, roster_id),
    ).fetchone()
    return dict(row) if row else None


def pick_summary(conn: sqlite3.Connection, league_id: str, pick_no: int, player_id: str, source: str) -> dict[str, Any]:
    board_data = get_draft_board(conn, league_id)
    cell = find_pick_cell(board_data, pick_no) or {"pick_no": pick_no}
    player = db.player_row_to_api(db.get_player_row(conn, player_id))
    return {
        "pick_no": pick_no,
        "round": cell.get("round"),
        "draft_slot": cell.get("draft_slot"),
        "manager_name": cell.get("manager_name"),
        "player": player,
        "source": source,
    }
