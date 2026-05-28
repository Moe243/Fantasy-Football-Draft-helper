"""Sleeper league import and draft-board persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .. import db
from ..providers.http import ProviderError
from ..providers.sleeper import SleeperClient
from .draft_history import calculate_manager_tendencies
from .normalization import normalize_position, normalize_team


def import_sleeper_league(conn: sqlite3.Connection, league_id: str, client: SleeperClient | None = None) -> dict[str, Any]:
    sleeper = client or SleeperClient()
    snapshot = sleeper.fetch_league_snapshot(league_id)
    league = snapshot["league"]
    save_league(conn, league)
    update_local_settings(conn, league)
    managers = save_managers(conn, league_id, snapshot.get("users") or [], snapshot.get("rosters") or [])
    drafts = save_drafts_and_picks(conn, league_id, snapshot.get("drafts") or [], sleeper)
    traded = save_user_draft_picks(conn, league_id, drafts[0] if drafts else None, snapshot.get("traded_picks") or [])
    previous_count = import_previous_drafts(conn, league, sleeper)
    tendencies = calculate_manager_tendencies(conn, league_id)
    return {
        "league_settings": db.get_league_settings(conn).to_dict(),
        "league": league_summary(league),
        "managers_imported": managers,
        "drafts_imported": len(drafts),
        "draft_picks_imported": sum(item["pick_count"] for item in drafts),
        "previous_drafts_imported": previous_count,
        "traded_picks_found": len(snapshot.get("traded_picks") or []),
        "traded_pick_note": None if snapshot.get("traded_picks") else "Traded pick data was not found; default snake draft picks were generated.",
        "user_draft_picks_imported": traded,
        "manager_tendencies": tendencies,
        "needs_team_selection": current_my_manager(conn, league_id) is None,
    }


def save_league(conn: sqlite3.Connection, league: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO sleeper_leagues (
            league_id, name, season, status, total_rosters, roster_positions_json,
            scoring_settings_json, settings_json, previous_league_id, raw_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(league_id) DO UPDATE SET
            name = excluded.name,
            season = excluded.season,
            status = excluded.status,
            total_rosters = excluded.total_rosters,
            roster_positions_json = excluded.roster_positions_json,
            scoring_settings_json = excluded.scoring_settings_json,
            settings_json = excluded.settings_json,
            previous_league_id = excluded.previous_league_id,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            league.get("league_id"),
            league.get("name"),
            league.get("season"),
            league.get("status"),
            league.get("total_rosters"),
            json.dumps(league.get("roster_positions") or []),
            json.dumps(league.get("scoring_settings") or {}),
            json.dumps(league.get("settings") or {}),
            league.get("previous_league_id"),
            json.dumps(league),
        ),
    )
    conn.commit()


def update_local_settings(conn: sqlite3.Connection, league: dict[str, Any]) -> None:
    scoring = league.get("scoring_settings", {})
    rec_points = scoring.get("rec", 0)
    scoring_label = "PPR" if rec_points == 1 else "Half PPR" if rec_points == 0.5 else "Standard"
    slots: dict[str, int] = {}
    for position in league.get("roster_positions") or []:
        normalized = normalize_position(position)
        slots[normalized] = slots.get(normalized, 0) + 1
    db.update_league_settings(
        conn,
        {
            "teams": league.get("total_rosters") or 10,
            "scoring": scoring_label,
            "roster_slots": slots or None,
        },
    )


def save_managers(
    conn: sqlite3.Connection,
    league_id: str,
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
) -> int:
    users_by_id = {str(user.get("user_id")): user for user in users}
    existing_me = current_my_manager(conn, league_id)
    imported = 0
    for roster in rosters:
        owner_id = str(roster.get("owner_id") or "")
        user = users_by_id.get(owner_id, {})
        metadata = user.get("metadata") or {}
        display_name = user.get("display_name") or user.get("username") or f"Roster {roster.get('roster_id')}"
        team_name = metadata.get("team_name") or metadata.get("display_name") or display_name
        is_me = 1 if existing_me and int(existing_me["roster_id"] or 0) == int(roster.get("roster_id") or 0) else 0
        conn.execute(
            """
            INSERT INTO league_managers (
                league_id, sleeper_user_id, roster_id, display_name, team_name,
                avatar, is_me, raw_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(league_id, roster_id) DO UPDATE SET
                sleeper_user_id = excluded.sleeper_user_id,
                display_name = excluded.display_name,
                team_name = excluded.team_name,
                avatar = excluded.avatar,
                is_me = CASE WHEN excluded.is_me = 1 THEN 1 ELSE league_managers.is_me END,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                league_id,
                owner_id or None,
                roster.get("roster_id"),
                display_name,
                team_name,
                user.get("avatar"),
                is_me,
                json.dumps({"user": user, "roster": roster}),
            ),
        )
        imported += 1
    conn.commit()
    return imported


def save_drafts_and_picks(
    conn: sqlite3.Connection,
    league_id: str,
    drafts: list[dict[str, Any]],
    sleeper: SleeperClient,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for draft_stub in drafts:
        draft_id = draft_stub.get("draft_id")
        if not draft_id:
            continue
        try:
            draft = sleeper.draft(draft_id)
        except ProviderError:
            draft = draft_stub
        picks = sleeper.draft_picks(draft_id)
        save_draft(conn, league_id, draft)
        save_draft_slots(conn, league_id, draft)
        save_draft_picks(conn, league_id, draft_id, picks)
        imported.append({"draft_id": draft_id, "pick_count": len(picks)})
    return imported


def save_draft(conn: sqlite3.Connection, league_id: str, draft: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO league_drafts (
            league_id, draft_id, season, status, type, settings_json,
            metadata_json, draft_order_json, slot_to_roster_json, raw_json, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(draft_id) DO UPDATE SET
            league_id = excluded.league_id,
            season = excluded.season,
            status = excluded.status,
            type = excluded.type,
            settings_json = excluded.settings_json,
            metadata_json = excluded.metadata_json,
            draft_order_json = excluded.draft_order_json,
            slot_to_roster_json = excluded.slot_to_roster_json,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            league_id,
            draft.get("draft_id"),
            draft.get("season"),
            draft.get("status"),
            draft.get("type"),
            json.dumps(draft.get("settings") or {}),
            json.dumps(draft.get("metadata") or {}),
            json.dumps(draft.get("draft_order") or {}),
            json.dumps(draft.get("slot_to_roster_id") or {}),
            json.dumps(draft),
        ),
    )
    conn.commit()


def save_draft_slots(conn: sqlite3.Connection, league_id: str, draft: dict[str, Any]) -> None:
    slot_to_roster = draft.get("slot_to_roster_id") or {}
    draft_order = draft.get("draft_order") or {}
    if not slot_to_roster and draft_order:
        owner_to_roster = {
            str(row["sleeper_user_id"]): row["roster_id"]
            for row in conn.execute("SELECT sleeper_user_id, roster_id FROM league_managers WHERE league_id = ?", (league_id,))
        }
        slot_to_roster = {
            str(slot): owner_to_roster.get(str(user_id))
            for user_id, slot in draft_order.items()
        }
    managers = managers_by_roster(conn, league_id)
    for slot_raw, roster_id in slot_to_roster.items():
        if roster_id is None:
            continue
        manager = managers.get(int(roster_id), {})
        conn.execute(
            """
            INSERT INTO draft_slots (league_id, roster_id, sleeper_user_id, manager_name, draft_slot)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(league_id, draft_slot) DO UPDATE SET
                roster_id = excluded.roster_id,
                sleeper_user_id = excluded.sleeper_user_id,
                manager_name = excluded.manager_name
            """,
            (
                league_id,
                int(roster_id),
                manager.get("sleeper_user_id"),
                manager.get("team_name") or manager.get("display_name"),
                int(slot_raw),
            ),
        )
    conn.commit()


def save_draft_picks(conn: sqlite3.Connection, league_id: str, draft_id: str, picks: list[dict[str, Any]]) -> None:
    for pick in picks:
        metadata = pick.get("metadata") or {}
        sleeper_player_id = str(pick.get("player_id") or metadata.get("player_id") or "")
        player_row = db.get_player_by_sleeper_id(conn, sleeper_player_id) if sleeper_player_id else None
        conn.execute(
            """
            INSERT INTO league_draft_picks (
                league_id, draft_id, pick_no, round, draft_slot, roster_id, picked_by,
                player_id, sleeper_player_id, player_name, position, team, is_keeper, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(draft_id, pick_no) DO UPDATE SET
                league_id = excluded.league_id,
                round = excluded.round,
                draft_slot = excluded.draft_slot,
                roster_id = excluded.roster_id,
                picked_by = excluded.picked_by,
                player_id = excluded.player_id,
                sleeper_player_id = excluded.sleeper_player_id,
                player_name = excluded.player_name,
                position = excluded.position,
                team = excluded.team,
                is_keeper = excluded.is_keeper,
                raw_json = excluded.raw_json
            """,
            (
                league_id,
                draft_id,
                pick.get("pick_no"),
                pick.get("round"),
                pick.get("draft_slot"),
                pick.get("roster_id"),
                pick.get("picked_by"),
                player_row["internal_player_id"] if player_row else (f"sleeper_{sleeper_player_id}" if sleeper_player_id else None),
                sleeper_player_id or None,
                player_name_from_pick(metadata, player_row),
                normalize_position(metadata.get("position") or (player_row["position"] if player_row else "")),
                normalize_team(metadata.get("team") or (player_row["team"] if player_row else "")),
                1 if pick.get("is_keeper") else 0,
                json.dumps(pick),
            ),
        )
    conn.commit()


def save_user_draft_picks(
    conn: sqlite3.Connection,
    league_id: str,
    draft: dict[str, Any] | None,
    traded_picks: list[dict[str, Any]],
) -> int:
    if not draft:
        return 0
    settings = draft.get("settings") or {}
    teams = int(settings.get("teams") or count_league_teams(conn, league_id) or 10)
    rounds = int(settings.get("rounds") or 16)
    season = str(draft.get("season") or "")
    slot_rows = conn.execute("SELECT * FROM draft_slots WHERE league_id = ?", (league_id,)).fetchall()
    roster_by_slot = {int(row["draft_slot"]): int(row["roster_id"]) for row in slot_rows if row["draft_slot"] and row["roster_id"]}
    managers = managers_by_roster(conn, league_id)
    my_roster = current_my_manager(conn, league_id)
    trades = {
        (int(item.get("round") or 0), int(item.get("roster_id") or 0)): int(item.get("owner_id") or 0)
        for item in traded_picks
        if not season or str(item.get("season") or season) == season
    }
    conn.execute("DELETE FROM user_draft_picks WHERE league_id = ?", (league_id,))
    imported = 0
    for round_no in range(1, rounds + 1):
        for draft_slot in range(1, teams + 1):
            pick_no = snake_pick_no(round_no, draft_slot, teams)
            original_roster = roster_by_slot.get(draft_slot)
            current_roster = trades.get((round_no, original_roster or 0), original_roster)
            manager = managers.get(current_roster or -1, {})
            conn.execute(
                """
                INSERT INTO user_draft_picks (
                    league_id, round, pick_no, draft_slot, original_roster_id,
                    current_roster_id, manager_name, is_mine, source, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    league_id,
                    round_no,
                    pick_no,
                    draft_slot,
                    original_roster,
                    current_roster,
                    manager.get("team_name") or manager.get("display_name"),
                    1 if my_roster and current_roster == my_roster["roster_id"] else 0,
                    "sleeper_traded_picks" if (round_no, original_roster or 0) in trades else "snake",
                    json.dumps({"traded_picks_found": bool(traded_picks)}),
                ),
            )
            imported += 1
    conn.commit()
    return imported


def import_previous_drafts(conn: sqlite3.Connection, league: dict[str, Any], sleeper: SleeperClient, depth: int = 3) -> int:
    previous_id = league.get("previous_league_id")
    imported = 0
    root_league_id = league.get("league_id")
    seen: set[str] = set()
    while previous_id and previous_id not in seen and imported < depth:
        seen.add(previous_id)
        try:
            previous_league = sleeper.league(previous_id)
            previous_drafts = sleeper.drafts(previous_id)
            imported_drafts = save_drafts_and_picks(conn, root_league_id, previous_drafts, sleeper)
            imported += len(imported_drafts)
            previous_id = previous_league.get("previous_league_id")
        except ProviderError:
            break
    return imported


def set_my_team(conn: sqlite3.Connection, league_id: str, roster_id: int) -> dict[str, Any]:
    conn.execute("UPDATE league_managers SET is_me = 0 WHERE league_id = ?", (league_id,))
    conn.execute(
        "UPDATE league_managers SET is_me = 1 WHERE league_id = ? AND roster_id = ?",
        (league_id, roster_id),
    )
    conn.commit()
    latest_draft = latest_draft_for_league(conn, league_id)
    if latest_draft:
        raw = json.loads(latest_draft["raw_json"] or "{}")
        traded = []
        save_user_draft_picks(conn, league_id, raw, traded)
    return current_my_manager(conn, league_id) or {}


def latest_draft_for_league(conn: sqlite3.Connection, league_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM league_drafts WHERE league_id = ? ORDER BY season DESC, id DESC LIMIT 1",
        (league_id,),
    ).fetchone()


def current_my_manager(conn: sqlite3.Connection, league_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM league_managers WHERE league_id = ? AND is_me = 1 LIMIT 1",
        (league_id,),
    ).fetchone()


def managers_by_roster(conn: sqlite3.Connection, league_id: str) -> dict[int, dict[str, Any]]:
    rows = conn.execute("SELECT * FROM league_managers WHERE league_id = ?", (league_id,)).fetchall()
    return {int(row["roster_id"]): dict(row) for row in rows if row["roster_id"] is not None}


def count_league_teams(conn: sqlite3.Connection, league_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?",
        (league_id,),
    ).fetchone()
    return int(row["count"] or 0)


def snake_pick_no(round_no: int, draft_slot: int, teams: int) -> int:
    slot = draft_slot if round_no % 2 == 1 else teams - draft_slot + 1
    return (round_no - 1) * teams + slot


def player_name_from_pick(metadata: dict[str, Any], player_row: sqlite3.Row | None) -> str | None:
    if player_row:
        return player_row["full_name"]
    name = " ".join(str(metadata.get(part) or "").strip() for part in ("first_name", "last_name")).strip()
    return name or None


def league_summary(league: dict[str, Any]) -> dict[str, Any]:
    return {
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "season": league.get("season"),
        "status": league.get("status"),
        "total_rosters": league.get("total_rosters"),
        "previous_league_id": league.get("previous_league_id"),
    }
