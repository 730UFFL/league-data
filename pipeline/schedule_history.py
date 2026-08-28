"""Compare the schedule across seasons: does it rotate, or repeat?

    python -m pipeline.schedule_history --from 2019 --to 2026

Team ids get reassigned between seasons, so everything here is keyed on the
*owner* id, which is stable. Seasons are compared only over the owners they
share, since leagues gain and lose members.

Reads credentials from .env like the rest of the pipeline. Results are cached
under data/raw/schedules/ so repeat runs do not re-hit ESPN.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations

from espn_api.football import League

from .config import RAW_DIR, load_config

CACHE = RAW_DIR / "schedules"


def owner_key(team) -> str:
    """A stable cross-season identity for a team."""
    owners = getattr(team, "owners", None) or []
    if owners:
        first = owners[0]
        if isinstance(first, dict):
            ident = first.get("id") or first.get("displayName")
            if ident:
                return str(ident)
        else:
            return str(first)
    return "team:" + str(team.team_id)


def owner_label(team) -> str:
    owners = getattr(team, "owners", None) or []
    if owners and isinstance(owners[0], dict):
        name = " ".join(
            p for p in (owners[0].get("firstName"), owners[0].get("lastName")) if p
        ).strip()
        if name:
            return name
    return str(team.team_name)


def pull_season(cfg, year: int) -> dict | None:
    """{'weeks': {week: {owner: opponent_owner}}, 'labels': {owner: name}}"""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{year}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))

    kwargs = {"league_id": cfg.league_id, "year": year}
    if cfg.is_private:
        kwargs.update(espn_s2=cfg.espn_s2, swid=cfg.swid)
    try:
        league = League(**kwargs)
    except Exception as exc:  # noqa: BLE001 - season may predate the league
        print(f"  {year}: unavailable ({type(exc).__name__}: {str(exc)[:90]})")
        return None

    by_id = {int(t.team_id): t for t in league.teams}
    labels = {owner_key(t): owner_label(t) for t in league.teams}
    id_to_owner = {tid: owner_key(t) for tid, t in by_id.items()}

    last_week = int(getattr(league.settings, "reg_season_count", 14))
    weeks: dict[str, dict[str, str]] = {}
    for week in range(1, last_week + 1):
        try:
            board = league.scoreboard(week)
        except Exception:  # noqa: BLE001
            continue
        pairing = {}
        for m in board:
            home, away = m.home_team, m.away_team
            if not home or not away or isinstance(home, int) or isinstance(away, int):
                continue
            ho, ao = id_to_owner.get(int(home.team_id)), id_to_owner.get(int(away.team_id))
            if ho and ao:
                pairing[ho] = ao
                pairing[ao] = ho
        if pairing:
            weeks[str(week)] = pairing

    data = {"year": year, "weeks": weeks, "labels": labels}
    cached.write_text(json.dumps(data), encoding="utf-8")
    print(f"  {year}: {len(labels)} teams, {len(weeks)} weeks")
    return data


def pair_counts(season: dict) -> Counter:
    c = Counter()
    for pairing in season["weeks"].values():
        for a, b in pairing.items():
            if a < b:
                c[(a, b)] += 1
    return c


def describe(season: dict) -> str:
    counts = pair_counts(season)
    dist = Counter(counts.values())
    owners = set(season["labels"])
    possible = len(owners) * (len(owners) - 1) // 2
    repeats = [p for p, c in counts.items() if c >= 2]
    adj = defaultdict(set)
    for a, b in repeats:
        adj[a].add(b)
        adj[b].add(a)
    degrees = sorted({len(adj[o]) for o in owners})
    return (
        f"{len(owners)} teams, {len(season['weeks'])} weeks, "
        f"{len(counts)}/{possible} pairs meet, "
        f"meetings {dict(sorted(dist.items()))}, repeat-degree {degrees}"
    )


def compare(a: dict, b: dict) -> dict:
    """How much of season a's week-by-week pairing survives into season b."""
    shared = set(a["labels"]) & set(b["labels"])
    weeks = sorted(set(a["weeks"]) & set(b["weeks"]), key=int)
    same = total = 0
    per_week = []
    for w in weeks:
        pa, pb = a["weeks"][w], b["weeks"][w]
        hits = tot = 0
        for o in shared:
            if o in pa and o in pb and pa[o] in shared and pb[o] in shared:
                tot += 1
                hits += pa[o] == pb[o]
        if tot:
            per_week.append((int(w), hits, tot))
            same += hits
            total += tot

    # Ignoring weeks: is the multiset of opponents per team the same?
    def opp_multiset(season):
        out = defaultdict(Counter)
        for pairing in season["weeks"].values():
            for x, y in pairing.items():
                if x in shared and y in shared:
                    out[x][y] += 1
        return out

    ma, mb = opp_multiset(a), opp_multiset(b)
    same_opponent_sets = sum(1 for o in shared if ma[o] == mb[o])

    return {
        "shared_teams": len(shared),
        "week_slot_match": (same / total) if total else None,
        "identical_weeks": [w for w, hi, to in per_week if hi == to],
        "same_opponent_multiset": same_opponent_sets,
        "of_teams": len(shared),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Does the league schedule rotate or repeat?")
    ap.add_argument("--from", dest="start", type=int, required=True)
    ap.add_argument("--to", dest="end", type=int, required=True)
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    args = ap.parse_args()

    cfg = load_config()
    if args.refresh and CACHE.exists():
        for f in CACHE.glob("*.json"):
            f.unlink()

    print(f"league {cfg.league_id}, seasons {args.start}-{args.end}\n")
    seasons = {}
    for year in range(args.start, args.end + 1):
        data = pull_season(cfg, year)
        if data and data["weeks"]:
            seasons[year] = data

    if len(seasons) < 2:
        raise SystemExit("\nNeed at least two seasons to compare.")

    print("\nPer season")
    for year, s in sorted(seasons.items()):
        print(f"  {year}: {describe(s)}")

    print("\nSeason vs season (over shared owners)")
    print(f"  {'pair':<12}{'teams':>6}{'same wk slot':>14}{'identical wks':>14}{'same opp set':>14}  verdict")
    for y1, y2 in combinations(sorted(seasons), 2):
        r = compare(seasons[y1], seasons[y2])
        slot = "n/a" if r["week_slot_match"] is None else f"{r['week_slot_match']*100:.1f}%"
        same_set = f"{r['same_opponent_multiset']}/{r['of_teams']}"
        pct = r["week_slot_match"] or 0.0
        set_all = r["same_opponent_multiset"] == r["of_teams"]
        verdict = (
            "IDENTICAL" if pct > 0.999
            else "rotated" if set_all
            else "regenerated"
        )
        print(
            f"  {y1}-{y2:<7}{r['shared_teams']:>6}{slot:>14}"
            f"{len(r['identical_weeks']):>14}{same_set:>14}  {verdict}"
        )

    print(
        "\nReading it: 'same wk slot' near 100% means the schedule is reused"
        " verbatim.\n  Near chance (~1/(n-1), about 9% for 12 teams) means it is"
        " regenerated.\n  A high 'same opp set' with a low 'same wk slot' means the"
        " same matchups\n  in a different order - a rotation."
    )


if __name__ == "__main__":
    main()
