"""Metric computations.

Every function here takes the canonical long-format matchup frame and returns a
frame or dict. Nothing in this module talks to ESPN, so it can be run against a
saved CSV and unit-checked without network access.

Canonical matchup frame columns:
    week, team_id, team_name, score, opponent_id, opponent_name,
    opponent_score, won

Two rows per matchup, one from each team's point of view.
"""
from __future__ import annotations

from math import erf, sqrt

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "week",
    "team_id",
    "team_name",
    "score",
    "opponent_id",
    "opponent_score",
]


# --------------------------------------------------------------------------
# shared building blocks
# --------------------------------------------------------------------------

def validate(mu: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in mu.columns]
    if missing:
        raise ValueError(f"matchup frame is missing columns: {missing}")
    mu = mu.copy()
    mu["won"] = mu["score"] > mu["opponent_score"]
    mu["tied"] = mu["score"] == mu["opponent_score"]
    mu["margin"] = mu["score"] - mu["opponent_score"]
    return mu


def team_names(mu: pd.DataFrame) -> dict[int, str]:
    """team_id -> most recent team name."""
    latest = mu.sort_values("week").groupby("team_id")["team_name"].last()
    return {int(k): str(v) for k, v in latest.items()}


def score_matrix(mu: pd.DataFrame) -> pd.DataFrame:
    """weeks (rows) x team_id (cols) of scores. NaN where a team didn't play."""
    return mu.pivot_table(
        index="week", columns="team_id", values="score", aggfunc="first"
    ).sort_index()


def opponent_matrix(mu: pd.DataFrame) -> pd.DataFrame:
    """weeks (rows) x team_id (cols) of that team's opponent_id."""
    return mu.pivot_table(
        index="week", columns="team_id", values="opponent_id", aggfunc="first"
    ).sort_index()


# --------------------------------------------------------------------------
# all-play / expected wins
# --------------------------------------------------------------------------

def all_play_by_week(mu: pd.DataFrame) -> pd.DataFrame:
    """Per team per week: record against every other team that week.

    This is the backbone metric. A team's all-play win percentage in a week is
    exactly its probability of beating a uniformly random opponent, so summing
    it over the season gives expected wins.
    """
    scores = score_matrix(mu)
    rows = []
    for week, series in scores.iterrows():
        present = series.dropna()
        ids = present.index.to_numpy()
        vals = present.to_numpy(dtype=float)
        n = len(vals)
        if n < 2:
            continue
        wins = (vals[:, None] > vals[None, :]).sum(axis=1)
        ties = (vals[:, None] == vals[None, :]).sum(axis=1) - 1
        losses = n - 1 - wins - ties
        median = float(np.median(vals))
        for i, team_id in enumerate(ids):
            rows.append(
                {
                    "week": int(week),
                    "team_id": int(team_id),
                    "score": float(vals[i]),
                    "ap_wins": int(wins[i]),
                    "ap_losses": int(losses[i]),
                    "ap_ties": int(ties[i]),
                    "ap_win_pct": (wins[i] + 0.5 * ties[i]) / (n - 1),
                    "weekly_rank": int(1 + (vals > vals[i]).sum()),
                    "teams_that_week": n,
                    "beat_median": bool(vals[i] > median),
                    "tied_median": bool(vals[i] == median),
                    "league_mean": float(vals.mean()),
                    "league_median": median,
                }
            )
    return pd.DataFrame(rows)


def expected_wins(mu: pd.DataFrame) -> pd.DataFrame:
    """Season expected wins, wins above expected, and the luck probability."""
    ap = all_play_by_week(mu)
    mu = validate(mu)

    actual = mu.groupby("team_id").agg(
        games=("week", "count"),
        wins=("won", "sum"),
        ties=("tied", "sum"),
    )
    actual["losses"] = actual["games"] - actual["wins"] - actual["ties"]

    agg = ap.groupby("team_id").agg(
        expected_wins=("ap_win_pct", "sum"),
        ap_wins=("ap_wins", "sum"),
        ap_losses=("ap_losses", "sum"),
        ap_ties=("ap_ties", "sum"),
        median_wins=("beat_median", "sum"),
    )
    agg["median_losses"] = actual["games"] - agg["median_wins"]

    out = actual.join(agg)
    out["wins_above_expected"] = out["wins"] - out["expected_wins"]
    out["all_play_pct"] = out["ap_wins"] / (out["ap_wins"] + out["ap_losses"] + out["ap_ties"])
    weekly_p = {tid: g["ap_win_pct"].to_numpy() for tid, g in ap.groupby("team_id")}
    out["expected_wins_sd"] = [
        expected_wins_sd(weekly_p[int(tid)]) for tid in out.index
    ]
    out["luck_probability"] = [
        luck_probability(int(r.wins), weekly_p[int(r.Index)]) for r in out.itertuples()
    ]
    return out.reset_index()


# --------------------------------------------------------------------------
# how surprising is a record?
# --------------------------------------------------------------------------

def poisson_binomial_pmf(probs) -> np.ndarray:
    """Exact distribution of total wins when each week has its own win prob.

    A season is a sum of independent, *non-identically* distributed Bernoulli
    trials -- week 4's all-play percentage is not week 5's. Convolving them
    week by week gives the exact win-total distribution.
    """
    probs = np.asarray(probs, dtype=float)
    pmf = np.zeros(len(probs) + 1)
    pmf[0] = 1.0
    for i, p in enumerate(probs):
        pmf[: i + 2] = pmf[: i + 2] * (1 - p) + np.concatenate(([0.0], pmf[: i + 1] * p))
    return pmf


def expected_wins_sd(probs) -> float:
    """sqrt(sum p(1-p)) -- the Poisson-binomial standard deviation.

    Always smaller than the naive Binomial(n, p_bar) sd, and the gap widens for
    volatile teams (weeks near 0 or 1 contribute almost no variance). Using the
    binomial sd here overstates how ordinary an extreme record is; that is the
    difference between our numbers and a naive implementation.
    """
    probs = np.asarray(probs, dtype=float)
    return float(np.sqrt(np.sum(probs * (1.0 - probs))))


def _phi(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def luck_probability(actual_wins: int, probs) -> float:
    """P(a record at least this far from expectation), two-sided.

    Near 1.0 means the record matches the scoring; near 0 means the schedule,
    not the roster, produced it. Uses the normal tail with the Poisson-binomial
    sd rather than the exact pmf, because the exact version is lumpy -- a team
    sitting 0.11 wins off expectation would score exactly 1.0.
    """
    probs = np.asarray(probs, dtype=float)
    sd = expected_wins_sd(probs)
    if sd <= 0:
        return 1.0
    distance = abs(actual_wins - float(probs.sum()))
    return float(min(1.0, 2.0 * _phi(-distance / sd)))


# --------------------------------------------------------------------------
# standings
# --------------------------------------------------------------------------

def standings(mu: pd.DataFrame) -> pd.DataFrame:
    """Season standings with the all-play and median columns alongside the real one."""
    mu = validate(mu)
    ew = expected_wins(mu).set_index("team_id")

    base = mu.groupby("team_id").agg(
        points_for=("score", "sum"),
        points_against=("opponent_score", "sum"),
        avg_score=("score", "mean"),
        score_sd=("score", "std"),
        high_score=("score", "max"),
        low_score=("score", "min"),
    )

    out = base.join(ew)
    out["win_pct"] = (out["wins"] + 0.5 * out["ties"]) / out["games"]
    out["median_win_pct"] = out["median_wins"] / out["games"]
    out["team_name"] = pd.Series(team_names(mu))
    out = out.sort_values(
        ["wins", "points_for"], ascending=[False, False]
    ).reset_index()
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def strength_of_schedule(mu: pd.DataFrame) -> pd.DataFrame:
    """Average opponent points per game, relative to the league average.

    Points rather than opponent win percentage: a schedule is hard because the
    teams on it score, not because those teams happened to win their other
    games. Opponent PPG is their full-season average, head-to-head included.
    """
    mu = validate(mu)
    ppg = mu.groupby("team_id")["score"].mean()
    league_ppg = float(mu["score"].mean())

    mu = mu.assign(opponent_ppg=mu["opponent_id"].map(ppg))
    out = mu.groupby("team_id").agg(
        opponent_ppg=("opponent_ppg", "mean"),
        opponent_actual_ppg=("opponent_score", "mean"),
    )
    out["sos"] = out["opponent_ppg"] - league_ppg
    out["opponent_performance_vs_own_avg"] = out["opponent_actual_ppg"] - out["opponent_ppg"]
    out["league_ppg"] = league_ppg
    return out.reset_index()


# --------------------------------------------------------------------------
# power rankings
# --------------------------------------------------------------------------

def power_rankings(mu: pd.DataFrame) -> pd.DataFrame:
    """Cumulative power ranking after each week.

    score = ((avg score * 6) + ((high + low) * 2) + (win pct * 400)) / 10
    """
    mu = validate(mu)
    rows = []
    for week in sorted(mu["week"].unique()):
        through = mu[mu["week"] <= week]
        agg = through.groupby("team_id").agg(
            avg_score=("score", "mean"),
            high=("score", "max"),
            low=("score", "min"),
            wins=("won", "sum"),
            ties=("tied", "sum"),
            games=("week", "count"),
        )
        agg["win_pct"] = (agg["wins"] + 0.5 * agg["ties"]) / agg["games"]
        agg["power_score"] = (
            agg["avg_score"] * 6 + (agg["high"] + agg["low"]) * 2 + agg["win_pct"] * 400
        ) / 10
        agg["power_rank"] = agg["power_score"].rank(ascending=False, method="min").astype(int)
        agg["week"] = int(week)
        rows.append(agg.reset_index())
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------------------
# luck: which specific weeks did it happen
# --------------------------------------------------------------------------

def key_matchups(mu: pd.DataFrame) -> pd.DataFrame:
    """Games where the result disagreed with how the team actually scored.

    Unlucky: a loss while scoring in the top half of the league that week.
    Lucky:   a win while scoring in the bottom half.
    """
    mu = validate(mu)
    ap = all_play_by_week(mu)[["week", "team_id", "weekly_rank", "teams_that_week", "ap_win_pct"]]
    joined = mu.merge(ap, on=["week", "team_id"], how="left")

    half = joined["teams_that_week"] / 2
    joined["kind"] = np.where(
        (~joined["won"]) & (joined["weekly_rank"] <= half),
        "unlucky",
        np.where((joined["won"]) & (joined["weekly_rank"] > half), "lucky", None),
    )
    out = joined[joined["kind"].notna()].copy()
    out["would_have_beaten"] = (out["ap_win_pct"] * (out["teams_that_week"] - 1)).round().astype(int)
    return out[
        [
            "week", "team_id", "team_name", "kind", "score", "weekly_rank",
            "teams_that_week", "opponent_id", "opponent_name", "opponent_score",
            "margin", "would_have_beaten",
        ]
    ].sort_values(["team_id", "week"]).reset_index(drop=True)


def close_game_flips(mu: pd.DataFrame, threshold: float = 10.0) -> pd.DataFrame:
    """Record if every game decided by < threshold points had gone the other way."""
    mu = validate(mu)
    close = mu["margin"].abs() < threshold
    agg = mu.assign(is_close=close).groupby("team_id").agg(
        wins=("won", "sum"),
        games=("week", "count"),
        close_games=("is_close", "sum"),
    )
    close_wins = mu[close & mu["won"]].groupby("team_id").size()
    close_losses = mu[close & ~mu["won"] & ~mu["tied"]].groupby("team_id").size()
    agg["close_wins"] = close_wins.reindex(agg.index, fill_value=0)
    agg["close_losses"] = close_losses.reindex(agg.index, fill_value=0)
    agg["wins_if_close_wins_flipped"] = agg["wins"] - agg["close_wins"]
    agg["wins_if_close_losses_flipped"] = agg["wins"] + agg["close_losses"]
    agg["threshold"] = threshold
    return agg.reset_index()


# --------------------------------------------------------------------------
# schedule swap: how much of the record is the schedule?
# --------------------------------------------------------------------------

def schedule_swap(mu: pd.DataFrame) -> pd.DataFrame:
    """Replay every team's scores against every other team's schedule.

    Row per (team, schedule owner). When a schedule would have a team play
    itself in some week, it plays the schedule's owner instead -- the standard
    convention, and it keeps every replay the same length.
    """
    mu = validate(mu)
    scores = score_matrix(mu)
    opps = opponent_matrix(mu)
    teams = [int(t) for t in scores.columns]

    rows = []
    for team in teams:
        team_scores = scores[team]
        for owner in teams:
            wins = losses = ties = 0
            for week in scores.index:
                own_score = team_scores.get(week)
                opponent = opps.loc[week, owner]
                if pd.isna(own_score) or pd.isna(opponent):
                    continue
                opponent = int(opponent)
                if opponent == team:
                    opponent = owner
                if opponent not in scores.columns:
                    continue
                opp_score = scores.loc[week, opponent]
                if pd.isna(opp_score):
                    continue
                if own_score > opp_score:
                    wins += 1
                elif own_score < opp_score:
                    losses += 1
                else:
                    ties += 1
            rows.append(
                {
                    "team_id": team,
                    "schedule_owner_id": owner,
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                    "is_own_schedule": team == owner,
                }
            )
    return pd.DataFrame(rows)


def schedule_swap_summary(mu: pd.DataFrame) -> pd.DataFrame:
    """Actual record vs. the best and worst schedules that existed in the league."""
    swap = schedule_swap(mu)
    names = team_names(mu)
    rows = []
    for team, group in swap.groupby("team_id"):
        actual = group[group["is_own_schedule"]].iloc[0]
        best = group.loc[group["wins"].idxmax()]
        worst = group.loc[group["wins"].idxmin()]
        rows.append(
            {
                "team_id": int(team),
                "team_name": names.get(int(team), str(team)),
                "actual_wins": int(actual["wins"]),
                "actual_losses": int(actual["losses"]),
                "best_wins": int(best["wins"]),
                "best_losses": int(best["losses"]),
                "best_schedule_owner_id": int(best["schedule_owner_id"]),
                "best_schedule_owner": names.get(int(best["schedule_owner_id"]), ""),
                "worst_wins": int(worst["wins"]),
                "worst_losses": int(worst["losses"]),
                "worst_schedule_owner_id": int(worst["schedule_owner_id"]),
                "worst_schedule_owner": names.get(int(worst["schedule_owner_id"]), ""),
                "mean_wins_all_schedules": float(group["wins"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("actual_wins", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# quad plot (cumulative PF / PA by week)
# --------------------------------------------------------------------------

def cumulative_by_week(mu: pd.DataFrame) -> pd.DataFrame:
    """Running PF/PA/record after each week -- the series behind the quad plot."""
    mu = validate(mu).sort_values(["team_id", "week"])
    g = mu.groupby("team_id")
    out = mu.assign(
        cum_pf=g["score"].cumsum(),
        cum_pa=g["opponent_score"].cumsum(),
        cum_wins=g["won"].cumsum(),
        games=g.cumcount() + 1,
    )
    out["cum_losses"] = out["games"] - out["cum_wins"]
    # Per-game averages, so weeks are on the same scale and comparable. Totals
    # only ever grow, which makes a week-to-week comparison meaningless.
    out["avg_pf"] = out["cum_pf"] / out["games"]
    out["avg_pa"] = out["cum_pa"] / out["games"]
    week_means = out.groupby("week")[["cum_pf", "cum_pa", "avg_pf", "avg_pa"]].transform("mean")
    out["league_avg_pf"] = week_means["cum_pf"]
    out["league_avg_pa"] = week_means["cum_pa"]
    # League PF and PA are the same pile of points, so these two are equal by
    # construction; both are kept so each axis can name its own reference.
    out["league_avg_ppg_for"] = week_means["avg_pf"]
    out["league_avg_ppg_against"] = week_means["avg_pa"]
    # Quadrant, stated in plain terms. High PF is good; high PA is bad.
    out["quadrant"] = np.select(
        [
            (out["cum_pf"] > out["league_avg_pf"]) & (out["cum_pa"] <= out["league_avg_pa"]),
            (out["cum_pf"] > out["league_avg_pf"]) & (out["cum_pa"] > out["league_avg_pa"]),
            (out["cum_pf"] <= out["league_avg_pf"]) & (out["cum_pa"] <= out["league_avg_pa"]),
        ],
        ["good", "shootout", "grinder"],
        default="ass",
    )
    return out[
        ["week", "team_id", "team_name", "cum_pf", "cum_pa", "avg_pf", "avg_pa",
         "cum_wins", "cum_losses", "games", "league_avg_pf", "league_avg_pa",
         "league_avg_ppg_for", "league_avg_ppg_against", "quadrant"]
    ].reset_index(drop=True)


# --------------------------------------------------------------------------
# season forecast
# --------------------------------------------------------------------------

def simulate_season(
    mu: pd.DataFrame,
    schedule: pd.DataFrame,
    through_week: int,
    n_sims: int = 5000,
    playoff_spots: int = 6,
    seed: int = 730,
) -> dict:
    """Monte Carlo the rest of the season from the state after `through_week`.

    Results through `through_week` are taken as played. Later weeks use the
    real schedule with scores drawn from each team's own scoring distribution
    (normal, fit on its completed games). No player projections involved -- the
    only inputs are how much a team scores and how erratically.

    `schedule` needs week / team_id / opponent_id for the whole season,
    completed weeks included.
    """
    mu = validate(mu)
    rng = np.random.default_rng(seed)

    played = mu[mu["week"] <= through_week]
    if played.empty:
        raise ValueError("no completed weeks at or before through_week")

    teams = sorted(mu["team_id"].unique().tolist())
    idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    fit = played.groupby("team_id")["score"].agg(["mean", "std", "count"])
    league_sd = float(played["score"].std())
    means = np.array([float(fit.loc[t, "mean"]) for t in teams])
    sds = np.array(
        [
            float(fit.loc[t, "std"]) if fit.loc[t, "count"] >= 3 and pd.notna(fit.loc[t, "std"])
            else league_sd
            for t in teams
        ]
    )

    base_wins = np.zeros(n_teams)
    base_points = np.zeros(n_teams)
    for row in played.itertuples():
        i = idx[int(row.team_id)]
        base_points[i] += float(row.score)
        if row.won:
            base_wins[i] += 1
        elif row.tied:
            base_wins[i] += 0.5

    future = schedule[schedule["week"] > through_week]
    future = future[future["team_id"] < future["opponent_id"]]  # one row per matchup
    pairs = [
        (idx[int(r.team_id)], idx[int(r.opponent_id)], int(r.week))
        for r in future.itertuples()
        if int(r.team_id) in idx and int(r.opponent_id) in idx
    ]
    future_weeks = sorted({w for _, _, w in pairs})

    wins = np.tile(base_wins, (n_sims, 1))
    points = np.tile(base_points, (n_sims, 1))
    # average cumulative wins by week, for the season-race chart
    race = {int(w): np.zeros(n_teams) for w in sorted(mu["week"].unique())}
    for w in race:
        if w <= through_week:
            wk = mu[mu["week"] <= w]
            race[w] = np.array(
                [
                    float(
                        wk[(wk["team_id"] == t) & wk["won"]].shape[0]
                        + 0.5 * wk[(wk["team_id"] == t) & wk["tied"]].shape[0]
                    )
                    for t in teams
                ]
            )

    running = wins.copy()
    for week in future_weeks:
        draws = rng.normal(means, sds, size=(n_sims, n_teams))
        for a, b, w in pairs:
            if w != week:
                continue
            a_wins = draws[:, a] > draws[:, b]
            running[:, a] += a_wins
            running[:, b] += ~a_wins
            points[:, a] += draws[:, a]
            points[:, b] += draws[:, b]
        race[week] = running.mean(axis=0)
    wins = running

    # seed by wins, points for as tiebreak
    order = np.lexsort((-points, -wins), axis=1)
    seeds = np.empty_like(order)
    np.put_along_axis(seeds, order, np.arange(1, n_teams + 1)[None, :].repeat(n_sims, 0), axis=1)

    final = standings(mu).set_index("team_id")
    actual_seed = {int(t): int(final.loc[t, "rank"]) for t in teams}

    results = []
    for t in teams:
        i = idx[t]
        results.append(
            {
                "team_id": int(t),
                "avg_wins": float(wins[:, i].mean()),
                "win_p10": float(np.percentile(wins[:, i], 10)),
                "win_p90": float(np.percentile(wins[:, i], 90)),
                "playoff_pct": float((seeds[:, i] <= playoff_spots).mean()),
                "avg_seed": float(seeds[:, i].mean()),
                "top_seed_pct": float((seeds[:, i] == 1).mean()),
                "same_finish_pct": float((seeds[:, i] == actual_seed[t]).mean()),
                "actual_seed": actual_seed[t],
                "actual_wins": float(final.loc[t, "wins"]),
            }
        )

    return {
        "through_week": through_week,
        "n_sims": n_sims,
        "playoff_spots": playoff_spots,
        "teams": results,
        "race": [
            {"week": int(w), "avg_cumulative_wins": {int(t): float(v[idx[t]]) for t in teams}}
            for w, v in sorted(race.items())
        ],
    }
