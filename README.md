# League data

A self-updating stats site for an ESPN fantasy football league. Pulls the season
from ESPN once a week, computes the metrics, and publishes a static site to
GitHub Pages.

**Live example:** <https://730uffl.github.io/league-data/>

It is built for any league, not one in particular — the league's name, size,
week count and playoff size all come from ESPN, so pointing it at your own is a
matter of setting `LEAGUE_ID`.

## What it shows

| View | |
| --- | --- |
| **Standings** | Record, points, and the all-play and median records alongside them |
| **Expected Wins** | What each team's scoring earned, against what the schedule gave it |
| **Schedule Luck** | Every team's scores replayed against every other schedule in the league |
| **Power Rankings** | Rank by week |
| **Quadrants** | Points for against points against, by week |
| **Forecast** | Monte Carlo of the rest of the season, from any completed week |

Pick a team from the dropdown, or click any dot, bar, line or table row.

## Use it for your own league

### 1. Get the repo

```bash
git clone https://github.com/730UFFL/league-data.git my-league
cd my-league
```

Create a virtual environment and install:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
```

Python 3.10 or newer. The only dependencies are `espn_api`, `pandas` and `numpy`.

### 2. Point it at your league

Create a `.env` in the repo root. It is gitignored, and a CI check fails any push
that commits a live credential.

```
LEAGUE_ID=634388
SEASON=2026
```

`LEAGUE_ID` is the number in your ESPN league URL:
`fantasy.espn.com/football/league?leagueId=`**`634388`**.

**If your league is public, that is all you need.** Check under
Settings → Basic Settings → Visibility in ESPN.

**If it is private,** add two cookies from a signed-in session:

```
ESPN_S2=<the espn_s2 cookie>
ESPN_SWID={<the SWID cookie, braces included>}
```

Get them from a browser signed in to fantasy.espn.com: DevTools → Application →
Cookies → `https://fantasy.espn.com`. `espn_s2` is a long URL-encoded string;
`SWID` is a GUID in curly braces.

> `espn_s2` is a session token for your ESPN account. Treat it like a password —
> it belongs in `.env` or a repo secret, never in a commit. It does expire, and
> signing out does not revoke it; changing your ESPN password does.

### 3. Build

```bash
.venv/bin/python -m pipeline.fetch    --season 2026 --box-scores
.venv/bin/python -m pipeline.compute  --season 2026
.venv/bin/python -m pipeline.validate --season 2026
```

Repeat `fetch` and `compute` for each season you want; the site offers whichever
it finds. Then serve it:

```bash
.venv/bin/python -m http.server 8730 --directory site
```

### 4. Publish

Push to your own GitHub repo, then:

1. **Settings → Pages → Source: GitHub Actions.** `.github/workflows/deploy.yml`
   does the rest.
2. **Settings → Secrets and variables → Actions.** Add `LEAGUE_ID` as a secret,
   and `SEASON` as a *variable* (not a secret). Private leagues also need
   `ESPN_S2` and `ESPN_SWID` as secrets.
3. Run the refresh once by hand to check it: Actions → Refresh league data → Run
   workflow.

After that it refreshes every Tuesday at 12:00 UTC and redeploys itself. Change
`SEASON` when a new season starts.

## How it fits together

```
ESPN  →  pipeline/fetch.py    →  data/raw/{season}/     (gitignored)
         pipeline/compute.py  →  site/data/{season}.json
         site/                →  GitHub Pages
```

The browser computes nothing. Every metric is precomputed, so the front end can
be rewritten without touching the pipeline — and the pipeline runs against a
saved CSV with no network, which is how it is tested.

| File | |
| --- | --- |
| `pipeline/config.py` | Env-only config; no secrets in source |
| `pipeline/fetch.py` | ESPN → canonical CSVs |
| `pipeline/metrics.py` | Every metric, as pure functions on one matchup table |
| `pipeline/compute.py` | Orchestrates, writes the JSON |
| `pipeline/validate.py` | Invariants that must hold for any league |
| `pipeline/schedule_history.py` | Compares schedules across seasons |
| `site/` | The page: one HTML file, one stylesheet, one script, no build step |

Everything derives from one long table, two rows per game:

```
week, team_id, team_name, score, opponent_id, opponent_name, opponent_score
```

Any source producing those columns works.

## Metrics worth knowing about

**Expected wins** is the sum of weekly all-play win percentages — a team's
probability of beating a random opponent, summed over the season. Because every
matchup produces exactly one win, league-wide expected wins must equal
league-wide actual wins; `validate.py` asserts it.

**Luck probability** uses the *Poisson-binomial* standard deviation,
`sqrt(sum p_w(1-p_w))`, not `sqrt(n p(1-p))`. Each week has its own win
probability, so a season is a sum of non-identical Bernoulli trials. The
binomial overstates the spread and makes flukish records look ordinary.

**Strength of schedule** is average opponent points per game minus the league
average. Opponent *win percentage* would inherit those opponents' own luck.

**Forecast** simulates the remaining schedule from any completed week, drawing
each team's score from a normal fit to its own games. No player projections —
only how much a team scores and how erratically.

## Checks

```bash
.venv/bin/python -m pipeline.validate --season 2026
```

Twelve identities that hold for any league in any season — not snapshots. If one
fails, a metric is wrong. A separate CI check fails any push carrying a live
`ESPN_S2` or a real `SWID`.

## Options

| | |
| --- | --- |
| `fetch --box-scores` | Also pull weekly lineups (slower; needed for future bench analysis) |
| `compute --sims N` | Simulations per forecast origin. Default 5000 |
| `compute --playoff-spots N` | Overrides the playoff size ESPN reports |
| `compute --include-owners` | Writes real names into the published JSON. **Off by default** — that file is world-readable once Pages is on |

## Caveats

- Built against a 12-team, 14-week league. Other sizes should work — everything
  reads the league's own settings — but are untested.
- The schedule-swap view assumes every team plays the same number of games.
- `data/raw/` is gitignored. It is reproducible from ESPN, and `site/data/*.json`
  is what the site serves.

## Licence

[MIT](LICENSE) — fork it, change it, use it for your own league.

Not affiliated with ESPN. Uses the unofficial
[espn_api](https://github.com/cwendt94/espn-api) client, which is MIT too.
