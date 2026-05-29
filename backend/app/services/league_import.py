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
    users = snapshot.get("users") or []
    rosters = snapshot.get("rosters") or []
    save_league(conn, league)
    update_local_settings(conn, league)
    drafts = save_drafts_and_picks(conn, league_id, snapshot.get("drafts") or [], sleeper)
    current_draft = select_current_draft(league, drafts)
    mapping_result = build_draft_slot_mapping_result(league, users, rosters, [current_draft] if current_draft else drafts)
    managers = save_managers(conn, league_id, users, rosters, mapping_result["draft_mapping"])
    save_draft_slots(conn, league_id, mapping_result["draft_mapping"])
    traded = save_user_draft_picks(conn, league_id, current_draft, snapshot.get("traded_picks") or [])
    previous_count = import_previous_drafts(conn, league, sleeper)
    tendencies = calculate_manager_tendencies(conn, league_id)
    return {
        "league_settings": db.get_league_settings(conn).to_dict(),
        "league": league_summary(league),
        "managers_imported": managers,
        "drafts_imported": len(drafts),
        "draft_picks_imported": sum(int(item.get("_pick_count") or 0) for item in drafts),
        "previous_drafts_imported": previous_count,
        "traded_picks_found": len(snapshot.get("traded_picks") or []),
        "traded_pick_note": None if snapshot.get("traded_picks") else "Traded pick data was not found; default snake draft picks were generated.",
        "user_draft_picks_imported": traded,
        "draft_mapping": draft_mapping_for_league(conn, league_id),
        "draft_mapping_source": mapping_result["source"],
        "draft_mapping_warnings": mapping_result["warnings"],
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
    draft_mapping: list[dict[str, Any]] | None = None,
) -> int:
    users_by_id = {str(user.get("user_id")): user for user in users}
    existing_me = current_my_manager(conn, league_id)
    imported = 0
    manager_rows = draft_mapping or fallback_manager_rows(league_id, users, rosters)
    for row in manager_rows:
        roster_id = row.get("roster_id")
        sleeper_user_id = row.get("sleeper_user_id")
        user = users_by_id.get(str(sleeper_user_id), {})
        metadata = user.get("metadata") or {}
        display_name = row.get("display_name") or user.get("display_name") or user.get("username") or f"Roster {roster_id}"
        team_name = row.get("team_name") or metadata.get("team_name") or metadata.get("display_name") or display_name
        is_me = 1 if existing_me and roster_id is not None and int(existing_me["roster_id"] or 0) == int(roster_id or 0) else 0
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
                sleeper_user_id or None,
                roster_id,
                display_name,
                team_name,
                row.get("avatar") or user.get("avatar"),
                is_me,
                json.dumps(row.get("raw_json") or {"user": user, "roster": row.get("roster")}),
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
        save_draft_picks(conn, league_id, draft_id, picks)
        imported_draft = dict(draft)
        imported_draft["_pick_count"] = len(picks)
        imported.append(imported_draft)
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


def save_draft_slots(conn: sqlite3.Connection, league_id: str, draft_mapping: list[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM draft_slots WHERE league_id = ?", (league_id,))
    for row in sorted(draft_mapping, key=lambda item: int(item.get("draft_slot") or 9999)):
        draft_slot = row.get("draft_slot")
        if not draft_slot:
            continue
        conn.execute(
            """
            INSERT INTO draft_slots (league_id, roster_id, sleeper_user_id, manager_name, draft_slot)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                league_id,
                optional_int(row.get("roster_id")),
                row.get("sleeper_user_id"),
                row.get("team_name") or row.get("display_name") or row.get("manager_name"),
                int(draft_slot),
            ),
        )
    conn.commit()


def build_draft_slot_mapping(
    league: dict[str, Any],
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return managers sorted by true Sleeper draft slot."""
    return build_draft_slot_mapping_result(league, users, rosters, drafts)["draft_mapping"]


def build_draft_slot_mapping_result(
    league: dict[str, Any],
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    draft = select_current_draft(league, drafts)
    draft_order = dict((draft or {}).get("draft_order") or {})
    slot_to_roster = dict((draft or {}).get("slot_to_roster_id") or {})
    users_by_id = {str(user.get("user_id")): user for user in users if user.get("user_id") is not None}
    rosters_by_id = {int(roster["roster_id"]): roster for roster in rosters if roster.get("roster_id") is not None}
    rosters_by_owner_id = {
        str(roster.get("owner_id")): roster
        for roster in rosters
        if roster.get("owner_id") is not None
    }
    teams = draft_team_count(league, draft, rosters, draft_order, slot_to_roster)
    warnings: list[str] = []
    by_slot: dict[int, dict[str, Any]] = {}
    source_parts: list[str] = []

    if slot_to_roster:
        source_parts.append("slot_to_roster_id")
        for slot_raw, roster_raw in slot_to_roster.items():
            slot = optional_int(slot_raw)
            roster_id = optional_int(roster_raw)
            if not slot or not roster_id:
                continue
            roster = rosters_by_id.get(roster_id, {"roster_id": roster_id})
            user_id = str(roster.get("owner_id") or "")
            by_slot[slot] = manager_mapping_row(
                league,
                draft,
                slot,
                roster,
                users_by_id.get(user_id, {}),
                "slot_to_roster_id",
            )

    if draft_order:
        source_parts.append("draft_order")
        for user_id_raw, slot_raw in draft_order.items():
            user_id = str(user_id_raw)
            slot = optional_int(slot_raw)
            if not slot:
                continue
            roster = rosters_by_owner_id.get(user_id)
            user = users_by_id.get(user_id, {"user_id": user_id})
            existing = by_slot.get(slot)
            if existing and roster and existing.get("roster_id") and int(existing["roster_id"]) != int(roster["roster_id"]):
                warnings.append(
                    f"Draft metadata disagreement at slot {slot}: slot_to_roster_id points to roster "
                    f"{existing['roster_id']}, but draft_order maps user {user_id} to roster {roster['roster_id']}. "
                    "Using draft_order for this slot."
                )
            if not roster and existing:
                roster = rosters_by_id.get(int(existing["roster_id"])) if existing.get("roster_id") else None
            row = manager_mapping_row(
                league,
                draft,
                slot,
                roster or {},
                user,
                "draft_order+slot_to_roster_id" if existing else "draft_order",
            )
            if existing and not row.get("roster_id"):
                row["roster_id"] = existing.get("roster_id")
            by_slot[slot] = row

    if not slot_to_roster and not draft_order:
        warnings.append("Sleeper draft metadata did not include draft_order or slot_to_roster_id; draft order was inferred from roster order and may need manual correction.")
        source_parts.append("inferred_roster_order")
        for index, roster in enumerate(rosters, start=1):
            if index > teams:
                break
            user_id = str(roster.get("owner_id") or "")
            by_slot[index] = manager_mapping_row(
                league,
                draft,
                index,
                roster,
                users_by_id.get(user_id, {}),
                "inferred_roster_order",
            )

    fill_missing_slots(league, draft, teams, by_slot, rosters, users_by_id, warnings)
    mapping = [by_slot[slot] for slot in sorted(by_slot) if slot > 0]
    return {
        "draft": draft,
        "draft_mapping": mapping,
        "warnings": warnings,
        "source": "+".join(dict.fromkeys(source_parts)) or "unknown",
    }


def fill_missing_slots(
    league: dict[str, Any],
    draft: dict[str, Any] | None,
    teams: int,
    by_slot: dict[int, dict[str, Any]],
    rosters: list[dict[str, Any]],
    users_by_id: dict[str, dict[str, Any]],
    warnings: list[str],
) -> None:
    used_rosters = {int(row["roster_id"]) for row in by_slot.values() if row.get("roster_id") is not None}
    unused_rosters = [roster for roster in rosters if roster.get("roster_id") is not None and int(roster["roster_id"]) not in used_rosters]
    if unused_rosters and len(by_slot) < teams:
        warnings.append("Sleeper draft metadata was partial; missing slots were filled from remaining rosters in Sleeper roster order.")
    empty_slots = [slot for slot in range(1, teams + 1) if slot not in by_slot]
    for slot, roster in zip(empty_slots, unused_rosters):
        user_id = str(roster.get("owner_id") or "")
        by_slot[slot] = manager_mapping_row(
            league,
            draft,
            slot,
            roster,
            users_by_id.get(user_id, {}),
            "inferred_missing_slot",
        )


def manager_mapping_row(
    league: dict[str, Any],
    draft: dict[str, Any] | None,
    draft_slot: int,
    roster: dict[str, Any] | None,
    user: dict[str, Any] | None,
    source: str,
) -> dict[str, Any]:
    roster = roster or {}
    user = user or {}
    metadata = user.get("metadata") or {}
    roster_id = optional_int(roster.get("roster_id"))
    sleeper_user_id = str(user.get("user_id") or roster.get("owner_id") or "") or None
    display_name = user.get("display_name") or user.get("username") or f"Roster {roster_id or draft_slot}"
    team_name = metadata.get("team_name") or metadata.get("display_name") or display_name
    return {
        "league_id": league.get("league_id"),
        "draft_id": (draft or {}).get("draft_id"),
        "draft_slot": int(draft_slot),
        "roster_id": roster_id,
        "sleeper_user_id": sleeper_user_id,
        "display_name": display_name,
        "team_name": team_name,
        "manager_name": team_name or display_name,
        "avatar": user.get("avatar"),
        "source": source,
        "raw_json": {"user": user, "roster": roster, "source": source, "draft": {"draft_id": (draft or {}).get("draft_id")}},
    }


def fallback_manager_rows(
    league_id: str,
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    league = {"league_id": league_id, "total_rosters": len(rosters)}
    return build_draft_slot_mapping_result(league, users, rosters, [])["draft_mapping"]


def select_current_draft(league: dict[str, Any], drafts: list[dict[str, Any] | None]) -> dict[str, Any] | None:
    candidates = [draft for draft in drafts if draft]
    if not candidates:
        return None
    league_draft_id = str(league.get("draft_id") or "")
    if league_draft_id:
        for draft in candidates:
            if str(draft.get("draft_id") or "") == league_draft_id:
                return draft
    season = str(league.get("season") or "")
    if season:
        for draft in candidates:
            if str(draft.get("season") or "") == season:
                return draft
    return candidates[0]


def draft_team_count(
    league: dict[str, Any],
    draft: dict[str, Any] | None,
    rosters: list[dict[str, Any]],
    draft_order: dict[str, Any],
    slot_to_roster: dict[str, Any],
) -> int:
    settings = (draft or {}).get("settings") or {}
    values = [
        optional_int(settings.get("teams")),
        optional_int(league.get("total_rosters")),
        len(rosters) or None,
        max((optional_int(value) or 0 for value in draft_order.values()), default=0) or None,
        max((optional_int(key) or 0 for key in slot_to_roster.keys()), default=0) or None,
    ]
    return next((int(value) for value in values if value), 10)


def draft_mapping_for_league(conn: sqlite3.Connection, league_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                ds.draft_slot,
                ds.roster_id,
                ds.sleeper_user_id,
                COALESCE(lm.display_name, ds.manager_name) AS display_name,
                COALESCE(lm.team_name, ds.manager_name) AS team_name,
                ds.manager_name,
                lm.avatar,
                COALESCE(lm.is_me, 0) AS is_me
            FROM draft_slots ds
            LEFT JOIN league_managers lm
                ON lm.league_id = ds.league_id
                AND (
                    (ds.roster_id IS NOT NULL AND lm.roster_id = ds.roster_id)
                    OR (ds.roster_id IS NULL AND ds.sleeper_user_id IS NOT NULL AND lm.sleeper_user_id = ds.sleeper_user_id)
                )
            WHERE ds.league_id = ?
            ORDER BY ds.draft_slot
            """,
            (league_id,),
        ).fetchall()
    ]


def update_draft_slots(conn: sqlite3.Connection, league_id: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
    if not slots:
        raise ValueError("slots must include at least one draft slot")
    seen_slots: set[int] = set()
    manager_by_roster = managers_by_roster(conn, league_id)
    manager_by_user = {
        str(row["sleeper_user_id"]): dict(row)
        for row in conn.execute(
            "SELECT * FROM league_managers WHERE league_id = ? AND sleeper_user_id IS NOT NULL",
            (league_id,),
        ).fetchall()
    }
    mapping: list[dict[str, Any]] = []
    for item in slots:
        draft_slot = optional_int(item.get("draft_slot"))
        if not draft_slot or draft_slot < 1:
            raise ValueError("Each slot must include a positive draft_slot")
        if draft_slot in seen_slots:
            raise ValueError(f"Duplicate draft slot: {draft_slot}")
        seen_slots.add(draft_slot)
        roster_id = optional_int(item.get("roster_id"))
        sleeper_user_id = str(item.get("sleeper_user_id") or "") or None
        manager = manager_by_roster.get(roster_id or -1) or manager_by_user.get(str(sleeper_user_id or ""), {})
        mapping.append(
            {
                "league_id": league_id,
                "draft_slot": draft_slot,
                "roster_id": roster_id,
                "sleeper_user_id": sleeper_user_id or manager.get("sleeper_user_id"),
                "display_name": manager.get("display_name") or item.get("display_name") or f"Slot {draft_slot}",
                "team_name": manager.get("team_name") or item.get("team_name") or manager.get("display_name") or f"Slot {draft_slot}",
                "manager_name": manager.get("team_name") or item.get("team_name") or manager.get("display_name") or f"Slot {draft_slot}",
                "avatar": manager.get("avatar"),
                "source": "manual",
            }
        )
    save_draft_slots(conn, league_id, mapping)
    latest_draft = latest_draft_for_league(conn, league_id)
    if latest_draft:
        save_user_draft_picks(conn, league_id, json.loads(latest_draft["raw_json"] or "{}"), [])
    return {"draft_mapping": draft_mapping_for_league(conn, league_id)}


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
