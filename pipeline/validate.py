"""Invariant checks on the computed metrics.

These are identities that must hold for any league in any season, not
regression snapshots -- if one fails, a metric is wrong.

    python -m pipeline.validate --legacy
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import metrics as M
from .compute import load_season

TOL = 1e-6
_results: list[tuple[bool, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((bool(condition), name, detail))


def run_checks(mu: pd.DataFrame, schedule: pd.DataFrame) -> None:
    mu = M.validate(mu)
    n_teams = mu["team_id"].nunique()

    ap = M.all_play_by_week(mu)
    ew = M.expected_wins(mu)
    st = M.standings(mu)
    swap = M.schedule_swap(mu)

    # Every all-play week is a full round robin against the other teams.
    total = ap["ap_wins"] + ap["ap_losses"] + ap["ap_ties"]
    check(
        "all-play games per team-week == teams - 1",
        bool((total == ap["teams_that_week"] - 1).all()),
        f"expected {n_teams - 1}",
    )

    # Each matchup produces exactly one win, so league expected wins must equal
    # league actual wins. This is the check that would have caught the old
    # expected-wins bug immediately.
    actual_total = float(ew["wins"].sum() + 0.5 * ew["ties"].sum())
    expected_total = float(ew["expected_wins"].sum())
    check(
        "sum(expected wins) == sum(actual wins)",
        abs(actual_total - expected_total) < 1e-6,
        f"actual {actual_total:.4f} vs expected {expected_total:.4f}",
    )

    check(
        "sum(wins above expected) == 0",
        abs(float(ew["wins_above_expected"].sum())) < 1e-6,
        f"{float(ew['wins_above_expected'].sum()):.6f}",
    )

    check(
        "luck probability in [0, 1]",
        bool(((ew["luck_probability"] >= 0) & (ew["luck_probability"] <= 1)).all()),
    )

    # A team replayed against its own schedule must reproduce its real record.
    own = swap[swap["is_own_schedule"]].set_index("team_id")
    real = st.set_index("team_id")
    mismatches = [
        f"{real.loc[t, 'team_name']}: swap {int(own.loc[t, 'wins'])} vs real {int(real.loc[t, 'wins'])}"
        for t in own.index
        if int(own.loc[t, "wins"]) != int(real.loc[t, "wins"])
    ]
    check("schedule swap reproduces the real record", not mismatches, "; ".join(mismatches))

    # Every replay is the same number of games.
    lengths = (swap["wins"] + swap["losses"] + swap["ties"]).unique()
    check(
        "every schedule replay is the same length",
        len(lengths) == 1,
        f"lengths {sorted(lengths.tolist())}",
    )

    # League-wide, points for and points against are the same pile of points.
    check(
        "sum(PF) == sum(PA)",
        abs(float(st["points_for"].sum() - st["points_against"].sum())) < 1e-6,
    )

    # All-play record and median record should point the same direction as
    # expected wins; a disagreement in ordering means one of them is inverted.
    corr = float(np.corrcoef(ew["expected_wins"], ew["ap_wins"])[0, 1])
    check("expected wins tracks all-play wins", corr > 0.99, f"r = {corr:.4f}")

    # Poisson-binomial pmf is a distribution and has the right mean.
    probs = ap[ap["team_id"] == ap["team_id"].iloc[0]]["ap_win_pct"].to_numpy()
    pmf = M.poisson_binomial_pmf(probs)
    check("poisson-binomial pmf sums to 1", abs(pmf.sum() - 1.0) < 1e-9, f"{pmf.sum():.12f}")
    mean = float((np.arange(len(pmf)) * pmf).sum())
    check(
        "poisson-binomial mean == sum(p)",
        abs(mean - probs.sum()) < 1e-9,
        f"{mean:.6f} vs {probs.sum():.6f}",
    )
    # ...and its sd must be below the naive binomial sd we started with.
    p_bar = probs.mean()
    naive = float(np.sqrt(len(probs) * p_bar * (1 - p_bar)))
    check(
        "poisson-binomial sd < naive binomial sd",
        M.expected_wins_sd(probs) <= naive + TOL,
        f"{M.expected_wins_sd(probs):.4f} vs naive {naive:.4f}",
    )

    # Forecasting from week 1 must still land on the real number of games.
    weeks = sorted(mu["week"].unique())
    sim = M.simulate_season(mu, schedule, through_week=weeks[0], n_sims=400)
    games = len(sorted(schedule["week"].unique()))
    over = [t for t in sim["teams"] if t["avg_wins"] > games + TOL]
    check("simulated wins never exceed games played", not over)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()

    mu, schedule, _ = load_season(args.season, legacy=args.legacy)
    run_checks(mu, schedule)

    failed = 0
    for ok, name, detail in _results:
        mark = "PASS" if ok else "FAIL"
        suffix = f"  ({detail})" if detail and not ok else (f"  {detail}" if detail else "")
        print(f"{mark}  {name}{suffix}")
        failed += not ok
    print(f"\n{len(_results) - failed}/{len(_results)} checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
