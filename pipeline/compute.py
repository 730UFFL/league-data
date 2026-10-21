"""Turn raw ESPN data into one JSON file the site reads.

    python -m pipeline.compute --season 2026
    python -m pipeline.compute --legacy          # use the 2025 CSVs already in data/

Everything the front end needs lives in site/data/{season}.json. No metric is
computed in the browser, so swapping the front end later changes nothing here.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import metrics as M
from .config import RAW_DIR, ROOT, SITE_DATA_DIR


def _clean(obj):
    """JSON-safe: numpy scalars out, NaN to None, floats to 4 dp."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        value = float(obj)
        return None if np.isnan(value) else round(value, 4)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return [_clean(v) for v in obj.tolist()]
    if obj is None or isinstance(obj, (str, int)):
        return obj
    if pd.isna(obj):
        return None
    return str(obj)


def _records(df: pd.DataFrame) -> list[dict]:
    return _clean(df.to_dict(orient="records"))


def load_meta(season: int) -> dict:
    """The league's own name and settings, if a fetch has recorded them."""
    path = RAW_DIR / str(season) / "meta.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def load_season(season: int, legacy: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Return (completed matchups, full schedule, teams or None)."""
    if legacy:
        mu = pd.read_csv(ROOT / "data" / "matchup_history.csv")
        future = ROOT / "data" / "future_schedule.csv"
        parts = [mu[["week", "team_id", "opponent_id"]]]
        if future.exists():
            parts.append(pd.read_csv(future)[["week", "team_id", "opponent_id"]])
        return mu, pd.concat(parts, ignore_index=True), None

    raw = RAW_DIR / str(season)
    if not (raw / "matchups.csv").exists():
        raise SystemExit(
            f"no data at {raw}. Run:  python -m pipeline.fetch --season {season}"
        )
    mu = pd.read_csv(raw / "matchups.csv")
    schedule = pd.read_csv(raw / "schedule.csv")
    teams_path = raw / "teams.csv"
    teams = pd.read_csv(teams_path) if teams_path.exists() else None
    return mu, schedule[["week", "team_id", "opponent_id"]], teams


def build(
    mu: pd.DataFrame,
    schedule: pd.DataFrame,
    teams: pd.DataFrame | None,
    season: int,
    playoff_spots: int,
    n_sims: int,
    include_owners: bool = False,
    meta: dict | None = None,
) -> dict:
    mu = M.validate(mu)
    meta = meta or {}
    weeks = sorted(int(w) for w in mu["week"].unique())
    if not weeks:
        # Every metric below needs at least one played week. Without this the
        # failure is a KeyError from an empty groupby, which says nothing about
        # the real cause: a season whose schedule exists but whose first week
        # has not finished.
        raise SystemExit(
            f"No completed weeks yet for {season}. Nothing to compute until the "
            f"first week's games have finished."
        )
    names = M.team_names(mu)

    standings = M.standings(mu)
    sos = M.strength_of_schedule(mu)
    standings = standings.merge(sos, on="team_id", how="left")

    swap = M.schedule_swap(mu)

    payload = {
        "season": season,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "league": {
            "name": meta.get("name", ""),
            "team_count": int(mu["team_id"].nunique()),
            "weeks_played": weeks,
            "scheduled_weeks": sorted(int(w) for w in schedule["week"].unique()),
            "playoff_spots": playoff_spots,
        },
        "teams": [
            {
                "team_id": int(tid),
                "name": name,
                # Real names of league members, off by default: the published
                # JSON is world-readable once the site deploys, and team_id is
                # already stable across seasons for cross-season identity.
                "owner": (
                    str(teams.loc[teams.team_id == tid, "owner"].iloc[0])
                    if include_owners and teams is not None and (teams.team_id == tid).any()
                    else ""
                ),
            }
            for tid, name in sorted(names.items())
        ],
        "standings": _records(standings),
        "all_play_by_week": _records(M.all_play_by_week(mu)),
        "power_rankings": _records(M.power_rankings(mu)),
        "key_matchups": _records(M.key_matchups(mu)),
        "close_games": _records(M.close_game_flips(mu)),
        "quad": _records(M.cumulative_by_week(mu)),
        "schedule_swap": {
            "summary": _records(M.schedule_swap_summary(mu)),
            "matrix": _records(swap),
        },
        "matchups": _records(
            mu[["week", "team_id", "team_name", "score", "opponent_id",
                "opponent_name", "opponent_score", "won", "margin"]]
        ),
    }

    # One forecast per origin week rather than one from the season midpoint.
    # The midpoint was a hindsight framing; on a season in progress it threw
    # away every result after it. The site defaults to the latest origin, which
    # is the actual forecast, and lets the reader wind it back.
    last_origin = weeks[-1] if len(weeks) < len(payload["league"]["scheduled_weeks"]) else weeks[-2]
    origins = [w for w in weeks if w <= last_origin]
    by_origin = {}
    for week in origins:
        sim = M.simulate_season(
            mu,
            schedule,
            through_week=week,
            n_sims=n_sims,
            playoff_spots=playoff_spots,
        )
        by_origin[str(week)] = _clean({"teams": sim["teams"], "race": sim["race"]})

    payload["forecast"] = {
        "n_sims": n_sims,
        "playoff_spots": playoff_spots,
        "total_weeks": len(payload["league"]["scheduled_weeks"]),
        "season_complete": len(weeks) >= len(payload["league"]["scheduled_weeks"]),
        "origins": [int(w) for w in origins],
        "latest": int(origins[-1]) if origins else None,
        "by_origin": by_origin,
    }
    return payload


def write_manifest(data_dir: Path) -> None:
    """List the seasons the site can offer, newest first."""
    seasons = []
    for path in sorted(data_dir.glob("*.json")):
        if path.name == "seasons.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if "season" not in payload:
            continue
        seasons.append(
            {
                "season": payload["season"],
                "teams": payload["league"]["team_count"],
                "weeks": len(payload["league"]["weeks_played"]),
                "generated_at": payload.get("generated_at"),
            }
        )
    seasons.sort(key=lambda s: s["season"], reverse=True)
    (data_dir / "seasons.json").write_text(
        json.dumps({"seasons": seasons}, separators=(",", ":")), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build site/data/{season}.json")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--legacy", action="store_true", help="use the 2025 CSVs in data/")
    parser.add_argument(
        "--playoff-spots",
        type=int,
        default=None,
        help="overrides the playoff size the league itself reports",
    )
    parser.add_argument("--sims", type=int, default=5000)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--include-owners",
        action="store_true",
        help="write league members' real names into the published JSON (off by default)",
    )
    args = parser.parse_args()

    season = args.season or (2025 if args.legacy else None)
    if season is None:
        from .config import load_config

        season = load_config().season

    mu, schedule, teams = load_season(season, legacy=args.legacy)
    meta = {} if args.legacy else load_meta(season)
    playoff_spots = args.playoff_spots or meta.get("playoff_team_count") or 6
    payload = build(mu, schedule, teams, season, playoff_spots, args.sims,
                    include_owners=args.include_owners, meta=meta)

    out = args.out or (SITE_DATA_DIR / f"{season}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=None, separators=(",", ":")), encoding="utf-8")

    write_manifest(out.parent)

    size_kb = out.stat().st_size / 1024
    print(f"wrote {out} ({size_kb:.0f} KB)")
    for key, value in payload.items():
        if isinstance(value, list):
            print(f"  {key}: {len(value)} rows")
        elif isinstance(value, dict) and key not in {"league"}:
            print(f"  {key}: {', '.join(value.keys())}")


if __name__ == "__main__":
    main()
