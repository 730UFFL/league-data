"""Configuration, read from the environment.

Nothing secret lives in source. Copy .env.example to .env and fill it in, or
set these in the shell / CI secret store.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SITE_DATA_DIR = ROOT / "site" / "data"


def _load_dotenv() -> None:
    """Minimal .env reader so there's no python-dotenv dependency."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    league_id: int
    season: int
    espn_s2: str | None
    swid: str | None

    @property
    def is_private(self) -> bool:
        return bool(self.espn_s2 and self.swid)


def load_config(season: int | None = None) -> Config:
    _load_dotenv()
    league_id = os.environ.get("LEAGUE_ID")
    if not league_id:
        raise SystemExit(
            "LEAGUE_ID is not set. Copy .env.example to .env and fill it in, "
            "or export LEAGUE_ID / SEASON / ESPN_S2 / ESPN_SWID."
        )
    return Config(
        league_id=int(league_id),
        season=int(season or os.environ.get("SEASON", 0) or 0),
        espn_s2=os.environ.get("ESPN_S2") or None,
        swid=os.environ.get("ESPN_SWID") or None,
    )
