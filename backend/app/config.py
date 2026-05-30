"""Application configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def _default_nfl_stats_season() -> str:
    year = datetime.now().year
    if datetime.now().month < 3:
        return str(year - 1)
    return str(year)


@dataclass(frozen=True)
class Settings:
    app_name: str = "Fantasy Football Chatbot"
    host: str = "127.0.0.1"
    port: int = int(os.getenv("PORT", "8787"))
    sleeper_base_url: str = os.getenv("SLEEPER_BASE_URL", "https://api.sleeper.app/v1")
    odds_base_url: str = os.getenv("ODDS_BASE_URL", "https://api.the-odds-api.com/v4")
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")
    db_path: Path = Path(os.getenv("FANTASY_DB_PATH", str(ROOT_DIR / ".data" / "fantasy.db")))
    frontend_dir: Path = ROOT_DIR / "frontend"
    nfl_stats_source_url: str = os.getenv("NFL_STATS_SOURCE_URL", "")
    nfl_stats_season: str = os.getenv("NFL_STATS_SEASON", "") or _default_nfl_stats_season()
    nfl_stats_cache_path: Path = Path(
        os.getenv("NFL_STATS_CACHE_PATH", str(ROOT_DIR / ".data" / "nfl_stats_cache.json"))
    )
    nflverse_stats_url: str = os.getenv(
        "NFLVERSE_STATS_URL",
        "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_season.json",
    )


settings = Settings()
