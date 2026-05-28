"""HTTP server for the fantasy football assistant MVP."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db
from .config import settings
from .models import DraftPick, Keeper
from .providers.http import ProviderError
from .providers.odds import OddsClient
from .providers.rankings_csv import import_ranking_rows
from .providers.sleeper import SleeperClient
from .sample_data import SAMPLE_PLAYERS, players_by_id
from .services.availability import estimate_availability
from .services.consensus import get_consensus_for_player, get_consensus_rows
from .services.data_imports import import_prop_rows, import_stat_rows
from .services.draft_board import get_draft_board
from .services.draft_room import get_draft_state, make_draft_pick, remove_draft_pick
from .services.league_import import import_sleeper_league, set_my_team
from .services.player_detail import player_detail, search_players
from .services.practice_draft import (
    get_current_practice,
    make_user_pick,
    reset_practice,
    simulate_next,
    simulate_to_my_next_pick,
    start_practice,
)
from .services.recommendations import (
    chat_response,
    current_pick_number,
    database_draft_recommendations,
    draft_recommendations,
    waiver_risers,
)
from .services.sleeper_import import import_sleeper_players
from .services.startup import ensure_sleeper_players


def json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(f"{value!r} is not JSON serializable")


class FantasyHandler(BaseHTTPRequestHandler):
    server_version = "FantasyAssistant/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api("GET", parsed.path, parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api("POST", parsed.path, parse_qs(parsed.query))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api("DELETE", parsed.path, parse_qs(parsed.query))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        try:
            with db.connect() as conn:
                db.init_db(conn)
                result = self.route_api(conn, method, path, query)
                self.send_json(result)
        except ProviderError as exc:
            self.send_json({"error": str(exc)}, status=502)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - final safety net
            self.send_json({"error": f"Unexpected server error: {exc}"}, status=500)

    def route_api(self, conn, method: str, path: str, query: dict[str, list[str]]) -> Any:
        settings_record = db.get_league_settings(conn)
        keepers = db.get_keepers(conn)
        picks = db.get_draft_picks(conn)

        if method == "GET" and path == "/api/health":
            return {"ok": True, "app": settings.app_name}

        if method == "GET" and path == "/api/setup/status":
            latest_players = db.latest_import_run(conn, "sleeper", "players")
            league_id = first(query, "league_id")
            return {
                "players_loaded": db.count_players_by_source(conn, "sleeper"),
                "latest_player_import": dict(latest_players) if latest_players else None,
                "league": league_status(conn, league_id) if league_id else None,
            }

        if method == "GET" and path == "/api/architecture":
            return {
                "stack": {
                    "mvp": "Python stdlib API + SQLite + static HTML/CSS/JS",
                    "production": "FastAPI or NestJS API, Postgres + pgvector, Redis, scheduled workers, React/Next.js UI",
                },
                "data_sources": [
                    "Sleeper for league settings, rosters, drafts, users, players, trending adds/drops",
                    "Paid or licensed projections/depth charts for rankings and weekly projections",
                    "The Odds API or similar odds feed for spreads, totals, implied team totals, and line movement",
                    "Optional ESPN/NFL.com adapters only where authenticated or licensed access is available",
                ],
            }

        if method == "GET" and path == "/api/players":
            position = first(query, "position")
            search = first(query, "search")
            active = optional_query_int(first(query, "active"))
            players, source = db.get_players_for_api(conn, position=position, search=search, active=active)
            return {"players": players, "source": source}

        if method == "GET" and path == "/api/players/search":
            return search_players(
                conn,
                search=first(query, "search"),
                position=first(query, "position"),
                team=first(query, "team"),
                age_min=optional_query_int(first(query, "age_min")),
                age_max=optional_query_int(first(query, "age_max")),
                number=first(query, "number"),
                active=optional_query_int(first(query, "active")),
                limit=int(first(query, "limit") or "50"),
                offset=int(first(query, "offset") or "0"),
                sort=first(query, "sort"),
            )

        if method == "GET" and path == "/api/players/detail":
            return player_detail(conn, require_query(query, "player_id"))

        if method == "GET" and path == "/api/players/consensus":
            position = first(query, "position")
            limit = int(first(query, "limit") or "100")
            current_pick = int(first(query, "current_pick") or current_pick_number(picks, keepers))
            return {
                "current_pick": current_pick,
                "players": get_consensus_rows(
                    conn,
                    position=position,
                    limit=limit,
                    current_pick=current_pick,
                ),
            }

        if path == "/api/league/settings":
            if method == "GET":
                return settings_record.to_dict()
            if method == "POST":
                return db.update_league_settings(conn, self.read_json()).to_dict()

        if method == "GET" and path == "/api/league/managers":
            league_id = require_query(query, "league_id")
            return {"managers": league_managers(conn, league_id)}

        if method == "POST" and path == "/api/league/my-team":
            payload = self.read_json()
            league_id = require(payload, "league_id")
            roster_id = int(require(payload, "roster_id"))
            return {"my_team": dict(set_my_team(conn, league_id, roster_id))}

        if path == "/api/keepers":
            if method == "GET":
                return {"keepers": [enrich_keeper(conn, keeper) for keeper in keepers]}
            if method == "POST":
                payload = self.read_json()
                keeper = Keeper(
                    player_id=require(payload, "player_id"),
                    team_name=str(payload.get("team_name") or "Unknown team"),
                    round=optional_int(payload.get("round")),
                    pick_no=optional_int(payload.get("pick_no")),
                )
                validate_player_id(conn, keeper.player_id)
                db.upsert_keeper(conn, keeper)
                return {"keepers": [enrich_keeper(conn, item) for item in db.get_keepers(conn)]}
            if method == "DELETE":
                player_id = first(query, "player_id")
                team_name = first(query, "team_name")
                if player_id and team_name:
                    db.delete_keeper(conn, player_id, team_name)
                else:
                    db.clear_keepers(conn)
                return {"keepers": [enrich_keeper(conn, item) for item in db.get_keepers(conn)]}

        if path == "/api/draft/picks":
            if method == "GET":
                return {"picks": [enrich_pick(conn, pick) for pick in picks]}
            if method == "POST":
                payload = self.read_json()
                pick = DraftPick(
                    pick_no=int(payload.get("pick_no") or len(picks) + 1),
                    player_id=require(payload, "player_id"),
                    manager=str(payload.get("manager") or "opponent"),
                    source=str(payload.get("source") or "manual"),
                )
                validate_player_id(conn, pick.player_id)
                db.add_draft_pick(conn, pick)
                return {"picks": [enrich_pick(conn, item) for item in db.get_draft_picks(conn)]}
            if method == "DELETE":
                pick_no = first(query, "pick_no")
                if pick_no:
                    db.remove_draft_pick(conn, int(pick_no))
                else:
                    db.clear_draft_picks(conn)
                return {"picks": [enrich_pick(conn, item) for item in db.get_draft_picks(conn)]}

        if method == "GET" and path == "/api/draft/recommendations":
            limit = int(first(query, "limit") or "12")
            manager = first(query, "manager") or "me"
            if db.has_database_players(conn):
                recs = database_draft_recommendations(
                    conn,
                    settings_record,
                    keepers,
                    picks,
                    limit=limit,
                    manager=manager,
                    position=first(query, "position"),
                    search=first(query, "search"),
                    hide_drafted=bool_query(first(query, "hide_drafted"), default=True),
                    hide_keepers=bool_query(first(query, "hide_keepers"), default=True),
                )
                return {
                    "current_pick": current_pick_number(picks, keepers),
                    "source": "database",
                    "recommendations": recs,
                }
            recs = draft_recommendations(settings_record, keepers, picks, limit=limit, manager=manager)
            return {
                "current_pick": current_pick_number(picks, keepers),
                "source": "sample",
                "recommendations": [rec.to_dict() for rec in recs],
            }

        if method == "GET" and path == "/api/draft/board":
            league_id = require_query(query, "league_id")
            return get_draft_board(conn, league_id)

        if method == "GET" and path == "/api/draft/state":
            league_id = require_query(query, "league_id")
            return get_draft_state(
                conn,
                league_id,
                position=first(query, "position"),
                search=first(query, "search"),
            )

        if method == "POST" and path == "/api/draft/pick":
            payload = self.read_json()
            return make_draft_pick(
                conn,
                require(payload, "league_id"),
                require(payload, "player_id"),
                pick_no=optional_int(payload.get("pick_no")),
                practice_draft_id=optional_int(payload.get("practice_draft_id")),
            )

        if method == "DELETE" and path == "/api/draft/pick":
            league_id = require_query(query, "league_id")
            pick_no = int(require_query(query, "pick_no"))
            return remove_draft_pick(conn, league_id, pick_no)

        if method == "GET" and path == "/api/draft/availability":
            league_id = require_query(query, "league_id")
            pick_no = int(require_query(query, "pick_no"))
            return estimate_availability(conn, league_id, pick_no)

        if method == "GET" and path == "/api/waivers/rising":
            positions_raw = first(query, "positions")
            positions = [item.strip().upper() for item in positions_raw.split(",")] if positions_raw else None
            return {"groups": waiver_risers(keepers, picks, positions=positions)}

        if method == "POST" and path == "/api/chat":
            payload = self.read_json()
            message = str(payload.get("message") or "")
            if not message.strip():
                raise ValueError("message is required")
            if db.has_database_players(conn) and any(term in message.lower() for term in ("draft next", "draft", "pick next", "best available")):
                recs = database_draft_recommendations(conn, settings_record, keepers, picks, limit=5)
                best = recs[0] if recs else None
                answer = f"My top draft target is {best['player']['full_name']} because {best['reasons'][0].lower()}" if best else "I do not see an available imported player on the board."
                return {"intent": "draft_recommendation", "answer": answer, "cards": recs}
            return chat_response(message, settings_record, keepers, picks)

        if method == "POST" and path == "/api/integrations/sleeper/import":
            payload = self.read_json()
            league_id = require(payload, "league_id")
            imported = import_sleeper_league(conn, league_id)
            return {"imported": imported, "snapshot": imported}

        if method == "POST" and path == "/api/integrations/sleeper/players/import":
            players = SleeperClient().players("nfl")
            return import_sleeper_players(conn, players)

        if method == "GET" and path == "/api/integrations/sleeper/trending":
            trend_type = first(query, "type") or "add"
            limit = int(first(query, "limit") or "25")
            return {"trending": SleeperClient().trending(trend_type=trend_type, limit=limit)}

        if method == "GET" and path == "/api/integrations/sleeper/trending/enriched":
            trend_type = first(query, "type") or "add"
            limit = int(first(query, "limit") or "25")
            lookback = int(first(query, "lookback_hours") or "24")
            return enriched_sleeper_trending(conn, trend_type=trend_type, limit=limit, lookback_hours=lookback)

        if method == "POST" and path == "/api/rankings/import/csv":
            payload = self.read_json()
            rows = payload.get("rows")
            if not isinstance(rows, list):
                raise ValueError("rows must be a list")
            source_name = require(payload, "source_name")
            return import_ranking_rows(conn, source_name, rows)

        if method == "POST" and path == "/api/player-stats/import/json":
            payload = self.read_json()
            rows = payload.get("rows")
            if not isinstance(rows, list):
                raise ValueError("rows must be a list")
            return import_stat_rows(conn, require(payload, "source_name"), rows)

        if method == "POST" and path == "/api/player-props/import/json":
            payload = self.read_json()
            rows = payload.get("rows")
            if not isinstance(rows, list):
                raise ValueError("rows must be a list")
            return import_prop_rows(conn, require(payload, "source_name"), payload.get("sportsbook"), rows)

        if method == "POST" and path == "/api/practice/start":
            payload = self.read_json()
            return start_practice(conn, require(payload, "league_id"), payload.get("name"))

        if method == "GET" and path == "/api/practice/current":
            return get_current_practice(conn, require_query(query, "league_id"))

        if method == "POST" and path == "/api/practice/pick":
            payload = self.read_json()
            return make_user_pick(conn, require(payload, "league_id"), require(payload, "player_id"))

        if method == "POST" and path == "/api/practice/simulate-next":
            return simulate_next(conn, require(self.read_json(), "league_id"))

        if method == "POST" and path == "/api/practice/simulate-to-my-next-pick":
            return simulate_to_my_next_pick(conn, require(self.read_json(), "league_id"))

        if method == "DELETE" and path == "/api/practice/reset":
            league_id = require_query(query, "league_id")
            return reset_practice(conn, league_id)

        if method == "GET" and path == "/api/integrations/odds/nfl":
            return {"games": OddsClient().fetch_nfl_odds()}

        raise ValueError(f"No route for {method} {path}")

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=json_default, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        frontend = settings.frontend_dir
        target = frontend / "index.html" if path in {"", "/"} else frontend / path.lstrip("/")
        resolved = target.resolve()
        if not str(resolved).startswith(str(frontend.resolve())) or not resolved.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def enrich_keeper(conn, keeper: Keeper) -> dict[str, Any]:
    player = get_api_player(conn, keeper.player_id)
    data = keeper.to_dict()
    data["player"] = player
    return data


def enrich_pick(conn, pick: DraftPick) -> dict[str, Any]:
    player = get_api_player(conn, pick.player_id)
    data = pick.to_dict()
    data["player"] = player
    return data


def get_api_player(conn, player_id: str) -> dict[str, Any] | None:
    row = db.get_player_row(conn, player_id)
    if row:
        return db.player_row_to_api(row)
    sample = players_by_id().get(player_id)
    return sample.to_dict() if sample else None


def validate_player_id(conn, player_id: str) -> None:
    if not db.get_player_row(conn, player_id) and player_id not in players_by_id():
        raise ValueError(f"Unknown player_id: {player_id}")


def enriched_sleeper_trending(
    conn,
    trend_type: str = "add",
    limit: int = 25,
    lookback_hours: int = 24,
) -> dict[str, Any]:
    trending = SleeperClient().trending(trend_type=trend_type, lookback_hours=lookback_hours, limit=limit)
    players: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in trending:
        sleeper_id = str(item.get("player_id") or "")
        row = db.get_player_by_sleeper_id(conn, sleeper_id)
        player = db.player_row_to_api(row) if row else {
            "id": f"sleeper_{sleeper_id}",
            "internal_player_id": f"sleeper_{sleeper_id}",
            "sleeper_id": sleeper_id,
            "name": f"Sleeper player {sleeper_id}",
            "full_name": f"Sleeper player {sleeper_id}",
            "position": "",
            "team": "",
        }
        consensus = get_consensus_for_player(conn, player["internal_player_id"]) if row else None
        entry = {
            "player": player,
            "trend_count": item.get("count"),
            "consensus": consensus["consensus"] if consensus else None,
            "sources": consensus["sources"] if consensus else {},
            "why": [
                f"Trending {trend_type} count: {item.get('count', 0)} over the last {lookback_hours} hours.",
                "Matched to local player database." if row else "Import Sleeper players to enrich this result.",
            ],
        }
        players.append(entry)
        position = player.get("position") or "UNK"
        groups.setdefault(position, []).append(entry)
    return {
        "trend_type": trend_type,
        "lookback_hours": lookback_hours,
        "players": players,
        "groups": groups,
    }


def import_sleeper_settings(conn, snapshot: dict[str, Any]) -> dict[str, Any]:
    league = snapshot["league"]
    scoring = league.get("scoring_settings", {})
    rec_points = scoring.get("rec", 0)
    scoring_label = "PPR" if rec_points == 1 else "Half PPR" if rec_points == 0.5 else "Standard"
    roster_positions = league.get("roster_positions") or []
    slots: dict[str, int] = {}
    for position in roster_positions:
        normalized = "DEF" if position in {"DST", "DEF"} else position
        slots[normalized] = slots.get(normalized, 0) + 1
    payload = {
        "teams": league.get("total_rosters") or 10,
        "scoring": scoring_label,
    }
    if slots:
        payload["roster_slots"] = slots
    updated = db.update_league_settings(conn, payload)
    return {"league_settings": updated.to_dict()}


def summarize_sleeper_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    league = snapshot["league"]
    return {
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "season": league.get("season"),
        "total_rosters": league.get("total_rosters"),
        "rosters": len(snapshot.get("rosters") or []),
        "users": len(snapshot.get("users") or []),
        "drafts": len(snapshot.get("drafts") or []),
        "picks": len(snapshot.get("picks") or []),
    }


def league_managers(conn, league_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM league_managers WHERE league_id = ? ORDER BY roster_id",
            (league_id,),
        ).fetchall()
    ]


def league_status(conn, league_id: str | None) -> dict[str, Any] | None:
    if not league_id:
        return None
    league = conn.execute("SELECT * FROM sleeper_leagues WHERE league_id = ?", (league_id,)).fetchone()
    if not league:
        return None
    counts = {
        "managers_imported": conn.execute("SELECT COUNT(*) AS count FROM league_managers WHERE league_id = ?", (league_id,)).fetchone()["count"],
        "drafts_imported": conn.execute("SELECT COUNT(*) AS count FROM league_drafts WHERE league_id = ?", (league_id,)).fetchone()["count"],
        "draft_picks_imported": conn.execute("SELECT COUNT(*) AS count FROM league_draft_picks WHERE league_id = ?", (league_id,)).fetchone()["count"],
    }
    return {"league": dict(league), **counts}


def first(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values else None


def require(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if value is None or value == "":
        raise ValueError(f"{name} is required")
    return str(value)


def require_query(query: dict[str, list[str]], name: str) -> str:
    value = first(query, name)
    if value is None or value == "":
        raise ValueError(f"{name} is required")
    return value


def optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def optional_query_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def bool_query(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value not in {"0", "false", "False", "no", "No"}


def run() -> None:
    with db.connect() as conn:
        db.init_db(conn)
        result = ensure_sleeper_players(conn)
        if result.get("status") in {"success", "error"}:
            print(f"Sleeper player startup import: {result}")
    server = ThreadingHTTPServer((settings.host, settings.port), FantasyHandler)
    print(f"{settings.app_name} running at http://{settings.host}:{settings.port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
