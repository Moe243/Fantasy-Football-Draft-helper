"""Shared dataclasses and serialization helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    position: str
    team: str
    projected_points: float
    adp: float
    rank: int
    bye: int
    injury_status: str = "Healthy"
    depth_chart: str = "Starter"
    snap_share: float = 0.0
    target_share: float = 0.0
    carry_share: float = 0.0
    trend_score: float = 0.0
    rostered_pct: float = 0.0
    odds_signal: str = "Neutral"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Keeper:
    player_id: str
    team_name: str
    round: int | None = None
    pick_no: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DraftPick:
    pick_no: int
    player_id: str
    manager: str
    source: str = "manual"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LeagueSettings:
    teams: int = 10
    scoring: str = "PPR"
    draft_slot: int = 6
    roster_slots: dict[str, int] = field(
        default_factory=lambda: {
            "QB": 1,
            "RB": 2,
            "WR": 2,
            "TE": 1,
            "FLEX": 1,
            "DEF": 1,
            "K": 1,
            "BENCH": 6,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Recommendation:
    player: Player
    score: float
    reasons: list[str]
    fit: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player.to_dict(),
            "score": round(self.score, 2),
            "reasons": self.reasons,
            "fit": self.fit,
        }
