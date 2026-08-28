# Data pipeline

ESPN → `data/raw/{season}/` → `site/data/{season}.json`. The front end reads the
JSON and computes nothing, so the site can be rewritten without touching this.

## Setup

```
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env      # then fill it in
```

## Run

```
python -m pipeline.fetch    --season 2026 --box-scores
python -m pipeline.compute  --season 2026
python -m pipeline.validate --season 2026
```

`--legacy` runs compute/validate against the 2025 CSVs already in `data/`,
with no network access.

## Modules

| file | does |
| --- | --- |
| `config.py` | env-only config; a minimal `.env` reader, no secrets in source |
| `fetch.py` | ESPN → canonical CSVs |
| `metrics.py` | every metric, as pure functions on a matchup frame |
| `compute.py` | orchestrates, writes the JSON |
| `validate.py` | invariant checks that must hold for any league |

## The matchup frame

Everything derives from one long-format table, two rows per game:

```
week, team_id, team_name, score, opponent_id, opponent_name, opponent_score
```

Any source that produces those columns works. That is why `--legacy` can run
the whole thing off a CSV exported months ago.

## Metric notes

**Expected wins** is the sum of weekly all-play win percentages — a team's
probability of beating a uniformly random opponent, summed over the season.
Because every matchup produces exactly one win, league-wide expected wins must
equal league-wide actual wins; `validate.py` asserts it.

**Luck probability** is the two-sided normal tail using the *Poisson-binomial*
standard deviation `sqrt(sum p_w(1-p_w))`, not `sqrt(n p(1-p))`. Each week has
its own win probability, so the season total is a sum of non-identical
Bernoulli trials. The binomial sd overstates the spread — for this league it is
1.79 where the true figure is 1.40 — which makes flukish records look ordinary.
Near 1.0 means a record matches the scoring behind it; near 0 means the
schedule produced it.

**Strength of schedule** is average opponent points per game minus the league
average, in points. Opponent *win percentage* inherits those opponents' own
luck; points do not.

**Schedule swap** replays every team's weekly scores against every other team's
schedule. Where a schedule would have a team face itself, it faces the
schedule's owner instead. `validate.py` asserts that replaying a team against
its own schedule reproduces its real record.

**Forecast** simulates the remaining schedule 5,000 times, drawing each team's
score from a normal fit to its own completed games. No player projections — the
only inputs are how much a team scores and how erratically.
