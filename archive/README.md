# Archive

The first pass at this project, kept for reference. Nothing here runs as part
of the current pipeline and nothing in `pipeline/` imports it.

| path | what it was |
| --- | --- |
| `730uffl.py` | Original ESPN pull + luck metrics, wrote CSVs to the repo root |
| `R/espn_api.R` | A second, independent ESPN fetcher in R (duplicated the Python one) |
| `R/analysis.R`, `R/quad_plot_functions.R` | The quad plot |
| `R/luck_analysis.R` | Luck scatter, SOS, opponent performance, luck scorecard, future SOS |
| `R/generate_weekly_plots.R` | Rendered `plots/week_N.png` |
| `dashboard.qmd` / `dashboard.html` | Quarto page; an OJS dropdown swapping static PNGs |
| `plots/`, `images/` | Rendered output |
| `data/` | Derived CSVs, all recomputable from `data/matchup_history.csv` |

## Changed on the way in

- **ESPN credentials redacted** from `730uffl.py` and `R/espn_api.R`. The
  `ESPN_S2` cookie that was in both is a live auth token; it now lives in `.env`
  only. Rotate it (log out of espn.com and back in) if it was ever shared.
- **`data/espn_standings.csv` cleaned.** The `Team` column held
  `str(team.owners)` — every league member's ESPN id and notification
  preferences, 27 KB of it. Reduced to `Team Name (Person Name)`.

## Known-wrong, do not copy forward

- `quad_plot_functions.R` negates PA for the y-axis but writes the quadrant
  `case_when` as if PA were still positive, so all four colour labels are
  inverted on the defence axis. The best team in the league gets the
  "bad defence" colour.
- `get_weekly_historical_data` compares a single week's score to
  `league_avg_pf * w` — a per-game average multiplied by the week number. Only
  week 1 is meaningful, which is why `win_luck` is 0 for everyone in
  `data/weekly_historical_data.csv`.
- `luck_analysis.R` reads its CSVs from the repo root; they were in `data/`.

## Still worth keeping

`data/matchup_history.csv` (now in the live `data/`) is the only file here that
isn't reproducible from something else. Every current metric derives from it.
