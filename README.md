# fuel-dash

Personal fuel price tracker for the Helsinki area. Scrapes the crowdsourced site
polttoaine.net on a 12 h GitHub Actions cron, accumulates price history in SQLite,
and publishes a static Chart.js + Leaflet dashboard: current prices sorted
cheapest-first, a map, per-station price history, and area median trends for
95E10 / 98E / diesel.

No auth, no API key, no credentials needed anywhere in this project.

Live: https://nickeniklas.github.io/fuel-dash/
Full design: [docs/PLAN.md](docs/PLAN.md) · Scraper contract: [docs/SCRAPER.md](docs/SCRAPER.md)

## Status

Build order (see `docs/PLAN.md`) is done through dashboard v1 and running
live: the poll+export+deploy workflow (`.github/workflows/poll.yml`) has
fired every ~12 h without a miss since 2026-07-12. `fuel.db` holds 120
stations (all geocoded) and 476 price rows as of 2026-08-08, dates
2026-07-05 through 2026-08-08. Station count and elapsed time have grown a
lot more than the row count has (89 → 120 stations vs. 474 → 476 rows since
2026-07-16) — most rows are still each station's initial 5-day batch;
ongoing re-reports on already-known stations are rare. `ajax.php?act=map`
(the hoped-for bulk coordinate endpoint) doesn't work — confirmed dead
2026-07-09, see `docs/SCRAPER.md` — so coords come from one request per new
station's map page instead.

Dashboard v1 is live in `site/`: `index.html`, `style.css`, `app.js`, no
framework or build step, Chart.js + Leaflet from CDN. Sticky fuel/radius
controls drive a price table, a Leaflet map (dark CartoDB tiles), a
per-station trend chart, and an area median chart. A 2026-07-19 UX pass
(committed, commit `a1e5e07`) added: clicking a table row or a map popup's
"View trend" button loads that station into the trend chart and scrolls to
it; stations can be starred as favorites, persisted in the browser's
`localStorage`, which pins them to the top of the price table and adds
quick-switch chips above the trend chart; and a live name search filters the
price table. A 2026-08-08 table/dropdown UX pass (verified in Node against
live `site/data/*.json`, not yet committed) added: click-to-sort table
headers (null averages always sort last); a station picker grouped into
"frequently reported" / "rarely reported" optgroups by per-fuel report
count, with a note near the trend chart for sparse stations; and graded
staleness (fresh / stale / abandoned, replacing the old binary flag) so a
station that's dropped off the source entirely reads differently from one
that's merely a day or two behind. Currently just letting report volume,
not just wall-clock time, accumulate — v2 (heatmap, fill-now-or-wait signal)
waits until it does. Serve locally with `python -m http.server` from
`site/` (fetch needs `http://`, not `file://`).

## Local setup

```
pip install -r requirements.txt
python -m unittest discover -s tests -t .
python poll.py           # live poll: fetches configured pages, upserts fuel.db
python export.py         # writes site/data/{stations,history,medians}.json from fuel.db
```

`poll.py` runs the full pipeline (fetch configured pages → parse → upsert into
`fuel.db` → backfill coords for new stations) and has been run live successfully.
`export.py` reads `fuel.db` and writes `site/data/*.json` for the dashboard —
shapes documented in `site/data/README.md`. `parser.py` exposes `parse_page()`
and `fetch_page()`; `db.py` exposes the SQLite storage layer; `coords.py`
fetches and caches per-station coordinates. `probe_coords.py` is a standalone
script to re-check the coordinate endpoints against reality if the site changes.

`.github/workflows/poll.yml` runs the cron (every 12 h): `poll.py` →
`export.py` → commit `fuel.db` + `site/data/*.json` back to `main` (skipped if
nothing changed) → deploy `site/` to GH Pages in the same run. It shares the
`pages` concurrency group with `pages.yml` since GITHUB_TOKEN-authored pushes
don't trigger other workflows' push triggers — `poll.yml` has to do its own
deploy.

## Politeness

12 h poll cadence, 100 ms between page requests, honest User-Agent, robots.txt
respected — see `docs/SCRAPER.md` for the full contract. This is someone else's
crowdsourced site; don't shorten the cadence.
