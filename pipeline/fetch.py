"""Pull a season from ESPN and write it to data/raw/{season}/.

Writes the canonical shapes the rest of the pipeline expects, so compute.py
never has to know that ESPN exists:

    teams.csv      team_id, team_name, owner, division_id, ...
    matchups.csv   two rows per completed matchup, one per team's viewpoint
    schedule.csv   every scheduled week including future ones
    box_scores.json (optional) per-week lineups, for bench/optimal-lineup work

Run:  python -m pipeline.fetch --season 2026
"""
from __future__ import annotations

import argparse
import json

import pandas as pd
from espn_api.football import League
from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague

from .config import RAW_DIR, load_config


def connect(cfg) -> League:
    """Open the league, public or private.

    A public league needs nothing but its id; cookies are only sent when both
    are set. ESPN's own errors are terse, so they are translated here into the
    thing that is actually wrong.
    """
    kwargs = {"league_id": cfg.league_id, "year": cfg.season}
    if cfg.is_private:
        kwargs.update(espn_s2=cfg.espn_s2, swid=cfg.swid)
    try:
        return League(**kwargs)
    except ESPNInvalidLeague as exc:
        raise SystemExit(
            f"League {cfg.league_id} does not exist for {cfg.season}. Check LEAGUE_ID "
            f"(the number in your ESPN league URL) and that the league ran that season."
        ) from exc
    except ESPNAccessDenied as exc:
        if cfg.is_private:
            raise SystemExit(
                f"ESPN rejected the credentials for league {cfg.league_id}. ESPN_S2 "
                "expires: sign in at fantasy.espn.com and copy the espn_s2 and SWID "
                "cookies again."
            ) from exc
        # ESPN answers 401 for a league that is private *and* for one that does
        # not exist, so this cannot tell them apart. Name both.
        raise SystemExit(
            f"ESPN refused league {cfg.league_id} for {cfg.season} without credentials. "
            "Either the league is private - set ESPN_S2 and ESPN_SWID in .env, see the "
            "README - or LEAGUE_ID is wrong. It is the number in your ESPN league URL, "
            "and it must be a season the league actually played."
        ) from exc


def owner_name(team) -> str:
    """A person's name, not a stringified settings object.

    The old script wrote `str(team.owners)` into the CSV, which dragged every
    owner's ESPN id and notification preferences into a public data file.
    """
    owners = getattr(team, "owners", None) or []
    if not owners:
        return ""
    first = owners[0]
    if isinstance(first, dict):
        full = " ".join(
            part for part in (first.get("firstName"), first.get("lastName")) if part
        ).strip()
        return full or str(first.get("displayName", ""))
    return str(first)


def teams_frame(league: League) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team_id": int(t.team_id),
                "team_name": str(t.team_name).strip(),
                "owner": owner_name(t),
                "abbrev": getattr(t, "team_abbrev", ""),
                "division_id": getattr(t, "division_id", 0),
                "wins": getattr(t, "wins", 0),
                "losses": getattr(t, "losses", 0),
                "ties": getattr(t, "ties", 0),
                "points_for": round(float(getattr(t, "points_for", 0.0)), 2),
                "points_against": round(float(getattr(t, "points_against", 0.0)), 2),
                "acquisitions": getattr(t, "acquisitions", 0),
                "trades": getattr(t, "trades", 0),
                "standing": getattr(t, "standing", 0),
            }
            for t in league.teams
        ]
    )


def _sides(matchup, week: int) -> list[dict]:
    home, away = matchup.home_team, matchup.away_team
    if not home or not away or isinstance(home, int) or isinstance(away, int):
        return []  # bye week
    hs, as_ = float(matchup.home_score), float(matchup.away_score)
    common = {"week": int(week), "home_score": hs, "away_score": as_}
    return [
        {
            **common,
            "team_id": int(home.team_id),
            "team_name": str(home.team_name).strip(),
            "score": hs,
            "opponent_id": int(away.team_id),
            "opponent_name": str(away.team_name).strip(),
            "opponent_score": as_,
            "is_home": True,
        },
        {
            **common,
            "team_id": int(away.team_id),
            "team_name": str(away.team_name).strip(),
            "score": as_,
            "opponent_id": int(home.team_id),
            "opponent_name": str(home.team_name).strip(),
            "opponent_score": hs,
            "is_home": False,
        },
    ]


def schedule_frame(league: League) -> pd.DataFrame:
    """Every regular-season week, played or not."""
    last_week = int(getattr(league.settings, "reg_season_count", 14))
    rows = []
    for week in range(1, last_week + 1):
        try:
            board = league.scoreboard(week)
        except Exception as exc:  # noqa: BLE001 - week may not exist yet
            print(f"  week {week}: unavailable ({exc})")
            continue
        for matchup in board:
            rows.extend(_sides(matchup, week))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # A week counts as played only if somebody actually scored.
    played_weeks = (
        df.groupby("week")["score"].max().pipe(lambda s: set(s[s > 0].index))
    )
    df["played"] = df["week"].isin(played_weeks)
    return df.drop(columns=["home_score", "away_score"])


def box_scores(league: League, weeks: list[int]) -> dict:
    """Per-week lineups: needed for bench points and optimal-lineup awards."""
    out: dict[str, list] = {}
    for week in weeks:
        try:
            games = league.box_scores(week)
        except Exception as exc:  # noqa: BLE001
            print(f"  box scores week {week}: unavailable ({exc})")
            continue
        entries = []
        for game in games:
            for side, lineup, team in (
                ("home", game.home_lineup, game.home_team),
                ("away", game.away_lineup, game.away_team),
            ):
                if not team or isinstance(team, int):
                    continue
                entries.append(
                    {
                        "side": side,
                        "team_id": int(team.team_id),
                        "players": [
                            {
                                "name": p.name,
                                "position": p.position,
                                "slot": p.slot_position,
                                "points": float(p.points),
                                "projected": float(getattr(p, "projected_points", 0.0)),
                            }
                            for p in lineup
                        ],
                    }
                )
        out[str(week)] = entries
        print(f"  box scores week {week}: {len(entries)} lineups")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull an ESPN season to data/raw/")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument(
        "--box-scores",
        action="store_true",
        help="also pull per-week lineups (slower; needed for bench/optimal analysis)",
    )
    args = parser.parse_args()

    cfg = load_config(args.season)
    print(f"league {cfg.league_id}, season {cfg.season}, private={cfg.is_private}")

    league = connect(cfg)
    out_dir = RAW_DIR / str(cfg.season)
    out_dir.mkdir(parents=True, exist_ok=True)

    # The league names itself and declares its own playoff size, so nothing
    # downstream has to be hardcoded for one league.
    settings = league.settings
    meta = {
        "name": str(getattr(settings, "name", "") or ""),
        "reg_season_count": int(getattr(settings, "reg_season_count", 14) or 14),
        "playoff_team_count": int(getattr(settings, "playoff_team_count", 6) or 6),
        "team_count": int(getattr(settings, "team_count", len(league.teams)) or len(league.teams)),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  league: {meta['name']!r}, {meta['team_count']} teams, "
          f"{meta['reg_season_count']} weeks, {meta['playoff_team_count']} playoff spots")

    teams = teams_frame(league)
    teams.to_csv(out_dir / "teams.csv", index=False)
    print(f"  teams: {len(teams)}")

    schedule = schedule_frame(league)
    if schedule.empty:
        raise SystemExit("no schedule returned - check league id, season, and cookies")
    schedule.to_csv(out_dir / "schedule.csv", index=False)

    matchups = schedule[schedule["played"]].drop(columns=["played"])
    matchups.to_csv(out_dir / "matchups.csv", index=False)
    weeks = sorted(matchups["week"].unique().tolist())
    print(f"  schedule: {schedule['week'].nunique()} weeks, {len(weeks)} played {weeks}")

    if args.box_scores:
        data = box_scores(league, weeks)
        (out_dir / "box_scores.json").write_text(json.dumps(data), encoding="utf-8")

    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
