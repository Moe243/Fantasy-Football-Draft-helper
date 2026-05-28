"""Application configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


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


settings = Settings()
