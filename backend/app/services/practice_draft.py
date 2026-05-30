"""Practice draft simulator backed by SQLite."""

from __future__ import annotations

import sqlite3
from typing import Any

from .availability import drafted_player_ids
from .consensus import get_consensus_rows
from .draft_board import get_draft_board


def start_practice(conn: sqlite3.Connection, league_id: str, name: str | None = None) -> dict[str, Any]:
    conn.execute("UPDATE practice_drafts SET status = 'archived' WHERE league_id = ? AND status = 'active'", (league_id,))
    cursor = conn.execute(
        """
        INSERT INTO practice_drafts (league_id, name, status, current_pick)
        VALUES (?, ?, 'active', 1)
        """,
        (league_id, name or "Practice Draft"),
    )
    conn.commit()
    return get_current_practice(conn, league_id)


def get_current_practice(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    draft = active_practice(conn, league_id)
    board = get_draft_board(conn, league_id)
    if not draft:
        return {"practice": None, "picks": [], "board": board}
    recalculate_current_pick(conn, league_id, int(draft["id"]))
    draft = active_practice(conn, league_id)
    picks = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM practice_draft_picks WHERE practice_draft_id = ? ORDER BY pick_no",
            (draft["id"],),
        ).fetchall()
    ]
    overlay_practice_picks(conn, board, picks)
    return {"practice": dict(draft), "picks": picks, "board": board}


def make_user_pick(conn: sqlite3.Connection, league_id: str, player_id: str) -> dict[str, Any]:
    draft = require_active(conn, league_id)
    if player_id in practice_drafted_player_ids(conn, int(draft["id"])):
        raise ValueError("That player has already been selected in this practice draft")
    pick_context = pick_context_for(conn, league_id, int(draft["current_pick"]))
    insert_practice_pick(conn, draft["id"], pick_context, player_id, "user")
    recalculate_current_pick(conn, league_id, int(draft["id"]))
    return get_current_practice(conn, league_id)


def make_pick_at(
    conn: sqlite3.Connection,
    league_id: str,
    player_id: str,
    pick_no: int | None = None,
    practice_draft_id: int | None = None,
    source: str = "user",
) -> dict[str, Any]:
    draft = active_practice_by_id(conn, league_id, practice_draft_id) if practice_draft_id else require_active(conn, league_id)
    if draft is None:
        raise ValueError("Could not find practice draft")
    if player_id in practice_drafted_player_ids(conn, int(draft["id"])):
        raise ValueError("That player has already been selected in this practice draft")
    target_pick = int(pick_no or draft["current_pick"] or 1)
    pick_context = pick_context_for(conn, league_id, target_pick)
    insert_practice_pick(conn, draft["id"], pick_context, player_id, source)
    recalculate_current_pick(conn, league_id, int(draft["id"]))
    return get_current_practice(conn, league_id)


def simulate_next(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    draft = require_active(conn, league_id)
    pick_context = pick_context_for(conn, league_id, int(draft["current_pick"]))
    if pick_context.get("is_mine"):
        raise ValueError("Cannot simulate while you are on the clock. Make your pick first.")
    player_id = choose_auto_pick(conn, league_id, int(draft["id"]))
    insert_practice_pick(conn, draft["id"], pick_context, player_id, "simulated")
    recalculate_current_pick(conn, league_id, int(draft["id"]))
    return get_current_practice(conn, league_id)


def simulate_to_my_next_pick(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    for _ in range(300):
        draft = require_active(conn, league_id)
        context = pick_context_for(conn, league_id, int(draft["current_pick"]))
        if context.get("is_mine"):
            return get_current_practice(conn, league_id)
        simulate_next(conn, league_id)
    return get_current_practice(conn, league_id)


def reset_practice(conn: sqlite3.Connection, league_id: str) -> dict[str, Any]:
    drafts = conn.execute("SELECT id FROM practice_drafts WHERE league_id = ?", (league_id,)).fetchall()
    for draft in drafts:
        conn.execute("DELETE FROM practice_draft_picks WHERE practice_draft_id = ?", (draft["id"],))
    conn.execute("DELETE FROM practice_drafts WHERE league_id = ?", (league_id,))
    conn.commit()
    return {"status": "reset"}


def remove_practice_pick(
    conn: sqlite3.Connection,
    league_id: str,
    pick_no: int,
    practice_draft_id: int | None = None,
) -> bool:
    draft = active_practice_by_id(conn, league_id, practice_draft_id) if practice_draft_id else active_practice(conn, league_id)
    if not draft:
        return False
    cursor = conn.execute(
        "DELETE FROM practice_draft_picks WHERE practice_draft_id = ? AND pick_no = ?",
        (draft["id"], pick_no),
    )
    conn.commit()
    recalculate_current_pick(conn, league_id, int(draft["id"]))
    return cursor.rowcount > 0


def active_practice(conn: sqlite3.Connection, league_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM practice_drafts WHERE league_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
        (league_id,),
    ).fetchone()


def active_practice_by_id(
    conn: sqlite3.Connection,
    league_id: str,
    practice_draft_id: int | None,
) -> sqlite3.Row | None:
    if practice_draft_id is None:
        return active_practice(conn, league_id)
    return conn.execute(
        "SELECT * FROM practice_drafts WHERE id = ? AND league_id = ? AND status = 'active'",
        (practice_draft_id, league_id),
    ).fetchone()


def require_active(conn: sqlite3.Connection, league_id: str) -> sqlite3.Row:
    draft = active_practice(conn, league_id)
    if not draft:
        start_practice(conn, league_id)
        draft = active_practice(conn, league_id)
    if draft is None:
        raise ValueError("Could not start practice draft")
    return draft


def pick_context_for(conn: sqlite3.Connection, league_id: str, pick_no: int) -> dict[str, Any]:
    board = get_draft_board(conn, league_id)
    for row_item in board.get("board") or []:
        for cell in row_item.get("picks") or []:
            if int(cell["pick_no"]) == int(pick_no):
                return {
                    "league_id": league_id,
                    "pick_no": pick_no,
                    "round": cell.get("round"),
                    "draft_slot": cell.get("draft_slot"),
                    "original_roster_id": cell.get("roster_id"),
                    "current_roster_id": cell.get("roster_id"),
                    "manager_name": cell.get("manager_name"),
                    "is_mine": 1 if cell.get("is_mine") else 0,
                    "source": "board",
                }
    row = conn.execute(
        "SELECT * FROM user_draft_picks WHERE league_id = ? AND pick_no = ?",
        (league_id, pick_no),
    ).fetchone()
    if row:
        return dict(row)
    teams = conn.execute("SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?", (league_id,)).fetchone()["count"] or 10
    round_no = ((pick_no - 1) // teams) + 1
    slot = ((pick_no - 1) % teams) + 1
    return {"pick_no": pick_no, "round": round_no, "draft_slot": slot, "manager_name": f"Slot {slot}", "is_mine": 0}


def choose_auto_pick(conn: sqlite3.Connection, league_id: str, practice_draft_id: int) -> str:
    unavailable = drafted_player_ids(conn, league_id) | practice_drafted_player_ids(conn, practice_draft_id)
    for row in get_consensus_rows(conn, limit=500, current_pick=1):
        player_id = row["player"]["internal_player_id"]
        position = row["player"].get("position")
        if player_id in unavailable:
            continue
        if position in {"K", "DEF"} and len(unavailable) < 100:
            continue
        return player_id
    raise ValueError("No available players to simulate")


def practice_drafted_player_ids(conn: sqlite3.Connection, practice_draft_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT player_id FROM practice_draft_picks WHERE practice_draft_id = ? AND player_id IS NOT NULL",
        (practice_draft_id,),
    ).fetchall()
    return {row["player_id"] for row in rows}


def overlay_practice_picks(conn: sqlite3.Connection, board: dict[str, Any], picks: list[dict[str, Any]]) -> None:
    pick_lookup = {int(pick["pick_no"]): pick for pick in picks}
    for row in board.get("board") or []:
        for cell in row.get("picks") or []:
            practice_pick = pick_lookup.get(int(cell["pick_no"]))
            if not practice_pick:
                continue
            player = player_for_practice_pick(conn, practice_pick["player_id"])
            cell["player"] = player
            cell["practice_source"] = practice_pick["source"]


def player_for_practice_pick(conn: sqlite3.Connection, player_id: str | None) -> dict[str, Any] | None:
    if not player_id:
        return None
    row = conn.execute("SELECT * FROM players WHERE internal_player_id = ?", (player_id,)).fetchone()
    if not row:
        return {"id": player_id, "internal_player_id": player_id, "name": player_id, "full_name": player_id}
    return {
        "id": row["internal_player_id"],
        "internal_player_id": row["internal_player_id"],
        "name": row["full_name"],
        "full_name": row["full_name"],
        "position": row["position"],
        "team": row["team"],
    }


def insert_practice_pick(
    conn: sqlite3.Connection,
    practice_draft_id: int,
    context: dict[str, Any],
    player_id: str,
    source: str,
) -> None:
    conn.execute(
        """
        INSERT INTO practice_draft_picks (
            practice_draft_id, pick_no, round, draft_slot, manager_name, roster_id, player_id, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(practice_draft_id, pick_no) DO UPDATE SET
            player_id = excluded.player_id,
            source = excluded.source
        """,
        (
            practice_draft_id,
            context.get("pick_no"),
            context.get("round"),
            context.get("draft_slot"),
            context.get("manager_name"),
            context.get("current_roster_id"),
            player_id,
            source,
        ),
    )
    conn.commit()


def advance_pick(conn: sqlite3.Connection, practice_draft_id: int, next_pick: int) -> None:
    conn.execute(
        "UPDATE practice_drafts SET current_pick = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (next_pick, practice_draft_id),
    )
    conn.commit()


def recalculate_current_pick(conn: sqlite3.Connection, league_id: str, practice_draft_id: int) -> int:
    max_pick = max_pick_for_league(conn, league_id)
    picked = {
        int(row["pick_no"])
        for row in conn.execute(
            "SELECT pick_no FROM practice_draft_picks WHERE practice_draft_id = ?",
            (practice_draft_id,),
        ).fetchall()
        if row["pick_no"] is not None
    }
    next_pick = 1
    while next_pick in picked and next_pick <= max_pick:
        next_pick += 1
    advance_pick(conn, practice_draft_id, next_pick)
    return next_pick


def max_pick_for_league(conn: sqlite3.Connection, league_id: str) -> int:
    rows = [
        conn.execute("SELECT MAX(pick_no) AS max_pick FROM user_draft_picks WHERE league_id = ?", (league_id,)).fetchone(),
        conn.execute("SELECT MAX(pick_no) AS max_pick FROM league_draft_picks WHERE league_id = ?", (league_id,)).fetchone(),
    ]
    max_pick = max((int(row["max_pick"] or 0) for row in rows), default=0)
    if max_pick:
        return max_pick
    teams = conn.execute("SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?", (league_id,)).fetchone()["count"] or 10
    return int(teams) * 16
