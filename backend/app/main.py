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
from .providers.sleeper import SleeperClient
from .sample_data import SAMPLE_PLAYERS, players_by_id
from .services.recommendations import chat_response, current_pick_number, draft_recommendations, waiver_risers


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
            players = SAMPLE_PLAYERS
            if position:
                players = [player for player in players if player.position == position.upper()]
            return {"players": [player.to_dict() for player in players]}

        if path == "/api/league/settings":
            if method == "GET":
                return settings_record.to_dict()
            if method == "POST":
                return db.update_league_settings(conn, self.read_json()).to_dict()

        if path == "/api/keepers":
            if method == "GET":
                return {"keepers": [enrich_keeper(keeper) for keeper in keepers]}
            if method == "POST":
                payload = self.read_json()
                keeper = Keeper(
                    player_id=require(payload, "player_id"),
                    team_name=str(payload.get("team_name") or "Unknown team"),
                    round=optional_int(payload.get("round")),
                    pick_no=optional_int(payload.get("pick_no")),
                )
                validate_player_id(keeper.player_id)
                db.upsert_keeper(conn, keeper)
                return {"keepers": [enrich_keeper(item) for item in db.get_keepers(conn)]}
            if method == "DELETE":
                player_id = first(query, "player_id")
                team_name = first(query, "team_name")
                if player_id and team_name:
                    db.delete_keeper(conn, player_id, team_name)
                else:
                    db.clear_keepers(conn)
                return {"keepers": [enrich_keeper(item) for item in db.get_keepers(conn)]}

        if path == "/api/draft/picks":
            if method == "GET":
                return {"picks": [enrich_pick(pick) for pick in picks]}
            if method == "POST":
                payload = self.read_json()
                pick = DraftPick(
                    pick_no=int(payload.get("pick_no") or len(picks) + 1),
                    player_id=require(payload, "player_id"),
                    manager=str(payload.get("manager") or "opponent"),
                    source=str(payload.get("source") or "manual"),
                )
                validate_player_id(pick.player_id)
                db.add_draft_pick(conn, pick)
                return {"picks": [enrich_pick(item) for item in db.get_draft_picks(conn)]}
            if method == "DELETE":
                pick_no = first(query, "pick_no")
                if pick_no:
                    db.remove_draft_pick(conn, int(pick_no))
                else:
                    db.clear_draft_picks(conn)
                return {"picks": [enrich_pick(item) for item in db.get_draft_picks(conn)]}

        if method == "GET" and path == "/api/draft/recommendations":
            limit = int(first(query, "limit") or "12")
            manager = first(query, "manager") or "me"
            recs = draft_recommendations(settings_record, keepers, picks, limit=limit, manager=manager)
            return {
                "current_pick": current_pick_number(picks, keepers),
                "recommendations": [rec.to_dict() for rec in recs],
            }

        if method == "GET" and path == "/api/waivers/rising":
            positions_raw = first(query, "positions")
            positions = [item.strip().upper() for item in positions_raw.split(",")] if positions_raw else None
            return {"groups": waiver_risers(keepers, picks, positions=positions)}

        if method == "POST" and path == "/api/chat":
            payload = self.read_json()
            message = str(payload.get("message") or "")
            if not message.strip():
                raise ValueError("message is required")
            return chat_response(message, settings_record, keepers, picks)

        if method == "POST" and path == "/api/integrations/sleeper/import":
            payload = self.read_json()
            league_id = require(payload, "league_id")
            snapshot = SleeperClient().fetch_league_snapshot(league_id)
            imported = import_sleeper_settings(conn, snapshot)
            return {"imported": imported, "snapshot": summarize_sleeper_snapshot(snapshot)}

        if method == "GET" and path == "/api/integrations/sleeper/trending":
            trend_type = first(query, "type") or "add"
            limit = int(first(query, "limit") or "25")
            return {"trending": SleeperClient().trending(trend_type=trend_type, limit=limit)}

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


def enrich_keeper(keeper: Keeper) -> dict[str, Any]:
    player = players_by_id().get(keeper.player_id)
    data = keeper.to_dict()
    data["player"] = player.to_dict() if player else None
    return data


def enrich_pick(pick: DraftPick) -> dict[str, Any]:
    player = players_by_id().get(pick.player_id)
    data = pick.to_dict()
    data["player"] = player.to_dict() if player else None
    return data


def validate_player_id(player_id: str) -> None:
    if player_id not in players_by_id():
        raise ValueError(f"Unknown player_id: {player_id}")


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


def first(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values else None


def require(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if value is None or value == "":
        raise ValueError(f"{name} is required")
    return str(value)


def optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)


def run() -> None:
    with db.connect() as conn:
        db.init_db(conn)
    server = ThreadingHTTPServer((settings.host, settings.port), FantasyHandler)
    print(f"{settings.app_name} running at http://{settings.host}:{settings.port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
