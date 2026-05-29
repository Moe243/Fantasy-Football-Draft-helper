"""Current and future pick ownership calculations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def calculate_pick_ownership(
    league_id: str,
    draft_id: str | None,
    season: str | None,
    managers: list[dict[str, Any]],
    draft_slots: list[dict[str, Any]],
    traded_picks: list[dict[str, Any]],
    teams: int,
    rounds: int,
    my_roster_id: int | None = None,
) -> list[dict[str, Any]]:
    roster_by_slot = {
        int(row["draft_slot"]): optional_int(row.get("roster_id"))
        for row in draft_slots
        if row.get("draft_slot") is not None
    }
    manager_by_roster = {
        optional_int(manager.get("roster_id")): manager
        for manager in managers
        if manager.get("roster_id") is not None
    }
    trade_by_round_roster = traded_pick_lookup(traded_picks, season)
    picks: list[dict[str, Any]] = []
    for pick_no in range(1, teams * rounds + 1):
        round_no = ((pick_no - 1) // teams) + 1
        draft_slot = snake_draft_slot(pick_no, teams)
        original_roster_id = roster_by_slot.get(draft_slot)
        trade = trade_by_round_roster.get((round_no, original_roster_id or 0))
        current_roster_id = optional_int((trade or {}).get("owner_id")) or original_roster_id
        manager = manager_by_roster.get(current_roster_id)
        picks.append(
            {
                "league_id": league_id,
                "draft_id": draft_id,
                "season": season,
                "round": round_no,
                "pick_no": pick_no,
                "draft_slot": draft_slot,
                "original_roster_id": original_roster_id,
                "current_roster_id": current_roster_id,
                "manager_name": manager_name(manager),
                "is_mine": 1 if my_roster_id and current_roster_id == my_roster_id else 0,
                "source": "traded_pick" if trade else "default_snake",
                "raw_json": json.dumps({"traded_pick": trade} if trade else {}),
            }
        )
    return picks


def save_pick_ownership(
    conn: sqlite3.Connection,
    league_id: str,
    draft_id: str | None,
    season: str | None,
    picks: list[dict[str, Any]],
) -> int:
    if draft_id:
        conn.execute(
            "DELETE FROM user_draft_picks WHERE league_id = ? AND draft_id = ?",
            (league_id, draft_id),
        )
    else:
        conn.execute(
            "DELETE FROM user_draft_picks WHERE league_id = ? AND draft_id IS NULL",
            (league_id,),
        )
    imported = 0
    for pick in picks:
        conn.execute(
            """
            INSERT INTO user_draft_picks (
                league_id, draft_id, season, round, pick_no, draft_slot,
                original_roster_id, current_roster_id, manager_name, is_mine, source, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                league_id,
                draft_id,
                season,
                pick["round"],
                pick["pick_no"],
                pick["draft_slot"],
                pick.get("original_roster_id"),
                pick.get("current_roster_id"),
                pick.get("manager_name"),
                pick.get("is_mine", 0),
                pick.get("source"),
                pick.get("raw_json"),
            ),
        )
        imported += 1
    conn.commit()
    return imported


def traded_pick_lookup(traded_picks: list[dict[str, Any]], season: str | None) -> dict[tuple[int, int], dict[str, Any]]:
    lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for item in traded_picks:
        item_season = str(item.get("season") or "")
        if season and item_season and item_season != str(season):
            continue
        round_no = optional_int(item.get("round"))
        original_roster_id = optional_int(item.get("roster_id") or item.get("original_roster_id"))
        if not round_no or not original_roster_id:
            continue
        lookup[(round_no, original_roster_id)] = item
    return lookup


def snake_draft_slot(pick_no: int, teams: int) -> int:
    pick_index = (pick_no - 1) % teams
    round_no = ((pick_no - 1) // teams) + 1
    return pick_index + 1 if round_no % 2 == 1 else teams - pick_index


def snake_pick_no(round_no: int, draft_slot: int, teams: int) -> int:
    slot = draft_slot if round_no % 2 == 1 else teams - draft_slot + 1
    return (round_no - 1) * teams + slot


def manager_name(manager: dict[str, Any] | None) -> str | None:
    if not manager:
        return None
    return manager.get("team_name") or manager.get("display_name") or manager.get("manager_name")


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

