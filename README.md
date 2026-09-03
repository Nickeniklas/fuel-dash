# fuel-dash

Personal fuel price tracker for the Helsinki area. Scrapes the crowdsourced site
polttoaine.net on a 12 h GitHub Actions cron, accumulates price history in SQLite,
and publishes a static Chart.js + Leaflet dashboard: current prices sorted
cheapest-first, a map, area median trends for 95E10 / 98E / diesel against the
official Finnish national average, a 2005-onwards long-term context chart, and
per-station price history.

Two sources: the polttoaine.net scrape for per-station Helsinki-area prices, and
the EU Weekly Oil Bulletin (European Commission, DG Energy) for official national
weekly prices back to 2005. They live in separate SQLite files — `fuel.db` and
`eu.db` — and are never joined.

No auth, no API key, no credentials needed anywhere in this project.

Live: https://nickeniklas.github.io/fuel-dash/
Full design: [docs/PLAN.md](docs/PLAN.md) · Source contracts: [docs/SCRAPER.md](docs/SCRAPER.md)

## Status

Build order (see `docs/PLAN.md`) is done through the EU bulletin ingest and
dashboard reframe, and running live: the poll+export+deploy workflow
(`.github/workflows/poll.yml`) has fired every ~12 h without a miss since
2026-07-12. As of 2026-09-03 `fuel.db` holds 124 stations (all geocoded) and
2775 price rows, dates 2026-07-05 through 2026-09-02, and `eu.db` holds 17,308
bulletin rows over 1082 weekly dates, 2005-01-03 through 2026-08-31.

The two series have very different depth, and the dashboard is built around
that fact. The **area median** is solid: 60 unbroken days. **Per-station**
history is not: 967 dated rows across 124 stations, median 6 points per
station, only 7 stations with 20+. Most rows are still each station's initial
5-day batch from the poll that first found it; ongoing re-reports on
already-known stations are rare. So per-station trend is presented as a
secondary lookup, not a headline. `ajax.php?act=map` (the hoped-for bulk
coordinate endpoint) doesn't work — confirmed dead 2026-07-09, see
`docs/SCRAPER.md` — so coords come from one request per new station's map page
instead.

The dashboard lives in `site/`: `index.html`, `style.css`, `app.js`, no
framework or build step, Chart.js + Leaflet from CDN. Sticky fuel/radius
controls drive, in page order, a price table, a Leaflet map (dark CartoDB
tiles), an area median chart, a long-term context chart, and a per-station
trend chart.

Accumulated UX and feature passes:

- **2026-07-19** (`a1e5e07`) — clicking a table row or a map popup's "View
  trend" button loads that station into the trend chart and scrolls to it;
  stations can be starred as favorites, persisted in `localStorage`, pinning
  them to the top of the price table with quick-switch chips above the trend
  chart; a live name search filters the price table.
- **2026-08-08** (committed 2026-09-03 in `06dcc4e`) — click-to-sort table
  headers (null averages always sort last); a station picker grouped into
  "frequently reported" / "rarely reported" optgroups by per-fuel report count,
  with a note near the trend chart for sparse stations; graded staleness
  (fresh / stale / abandoned, replacing the old binary flag) so a station
  that's dropped off the source entirely reads differently from one that's
  merely a day or two behind.
- **2026-09-03** (`06dcc4e` + `49655ae`) — EU bulletin ingest, plus the
  dashboard reframe: the area median chart gained a dashed FI national weekly
  overlay and a cents-per-litre gap readout ("Helsinki area is 0.3 snt/l above
  the national average"); a new long-term context chart carries the
  2005-onwards series with a 1/3/5/all year range selector; the page was
  reordered so per-station trend comes last under a subheading stating its
  limits; the rarely-reported station group is collapsed behind a checkbox; a
  coverage line computed from the loaded JSON reports station count, report
  count and median span; and the footer credits both sources. On 98E the
  national overlay is hidden with a note — the bulletin publishes no 98E
  series and substituting the 95 series would be quietly wrong.

Currently just letting per-station report volume, not wall-clock time,
accumulate — v2 (heatmap, fill-now-or-wait signal) waits until it does. Serve
locally with `python -m http.server` from `site/` (fetch needs `http://`, not
`file://`).

## Local setup

```
pip install -r requirements.txt
python -m unittest discover -s tests -t .    # 92 tests, no network
python poll.py           # live poll: fetches configured pages, upserts fuel.db
python eu_bulletin.py    # EU bulletin: self-gated, upserts eu.db
python export.py         # writes site/data/*.json from fuel.db + eu.db
```

`poll.py` runs the scrape pipeline (fetch configured pages → parse → upsert into
`fuel.db` → backfill coords for new stations) and has been run live successfully.

`eu_bulletin.py` downloads one DG Energy XLSX workbook (~4.5 MB) holding the
whole 2005-onwards series and upserts FI/SE/DE/IT × 95/diesel × both tax
variants into `eu.db`. It is **self-gated**: if the newest week already stored is
less than `GATE_DAYS` (8) old it logs and exits 0 without downloading, so the
12 h cron costs one download per weekly bulletin rather than ~14. Pass
`--file <path>` to parse a local copy instead, which also bypasses the gate.

`export.py` reads `fuel.db` for `stations.json` / `history.json` /
`medians.json` and `eu.db` for `eu_weekly.json` — shapes documented in
`site/data/README.md`. A missing or empty `eu.db` is not an error: it writes the
other three and logs that it skipped `eu_weekly.json`.

`parser.py` exposes `parse_page()` and `fetch_page()`; `db.py` exposes the
storage layer for both databases (`connect()` for `fuel.db`, `connect_eu()` for
`eu.db`); `coords.py` fetches and caches per-station coordinates.
`probe_coords.py` is a standalone script to re-check the coordinate endpoints
against reality if the site changes. `tests/fixtures/make_eu_fixture.py`
regenerates the committed workbook slice the bulletin tests run against, if the
source layout ever changes.

`.github/workflows/poll.yml` runs the cron (every 12 h): `poll.py` →
`eu_bulletin.py` → `export.py` → commit `fuel.db` + `eu.db` + `site/data/*.json`
back to `main` (skipped if nothing changed) → deploy `site/` to GH Pages in the
same run. It shares the `pages` concurrency group with `pages.yml` since
GITHUB_TOKEN-authored pushes don't trigger other workflows' push triggers —
`poll.yml` has to do its own deploy.

## Politeness

12 h poll cadence, 100 ms between page requests, honest User-Agent, robots.txt
respected — see `docs/SCRAPER.md` for the full contract. This is someone else's
crowdsourced site; don't shorten the cadence. The same honest User-Agent is used
for the EU bulletin, and its self-gate exists so we fetch that 4.5 MB workbook
once per publication rather than on every poll.

## Attribution

Station prices are crowdsourced from [polttoaine.net](https://polttoaine.net).

National weekly prices come from the
[EU Weekly Oil Bulletin](https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en),
European Commission, Directorate-General for Energy. Reproduction is authorised
provided the source is acknowledged — the dashboard footer carries this credit,
and it must stay there.
