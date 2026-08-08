# CLAUDE.md — fuel-dash

Personal fuel price tracker for the Helsinki area. Poller scrapes polttoaine.net
into SQLite on a GH Actions cron, exports JSON, static Chart.js dashboard on
GH Pages reads it. Full plan: `docs/PLAN.md`. Scraper contract: `docs/SCRAPER.md`.

Live at https://nickeniklas.github.io/fuel-dash/ · repo at
https://github.com/Nickeniklas/fuel-dash. The repo went through two renames
(`gas-price-dashboard` → `helsinki-fuel-dash` → `fuel-dash`, 2026-07-16) to
land on a name that doesn't bake in a city, since the plan is to broaden past
Helsinki eventually. GitHub Pages URLs follow the current repo name
automatically; local clones need `git remote set-url origin` updated by hand
if they predate a rename — it does not happen on its own.

## Decided stack (do not re-litigate without being asked)

Python + requests + BeautifulSoup-or-similar, SQLite, GH Actions cron (12 h),
GH Pages serving `site/`, Chart.js, vanilla JS. No frameworks, no LLM in the poller.

History note: the project originally targeted the unofficial Tankille API. It
blocked us (2026-07-08) and was dropped entirely, clean DB, no workarounds. Do not
suggest going back to it.

## Hard rules

- **Never commit or push autonomously.** Global rule, no exceptions.
- **Pumperly (GPL-3.0) is spec only.** Never copy, port, or paraphrase its code.
  The page format facts live in `docs/SCRAPER.md`; code against that doc.
- **Politeness is non-negotiable:** 12 h cadence, 100 ms between requests, honest
  User-Agent, respect robots.txt. This is someone else's crowdsourced site.
- Ingest everything from the configured pages. Geographic filtering (15 km radius)
  happens only at display time in the dashboard.
- Dedupe key is `(station_id, fuel, date)`, latest price wins within a day.
- GH Pages serves `site/`, never `docs/`.
- No credentials exist anymore (no auth needed); if any secret ever appears, it
  goes in gitignored `.env` / Actions secrets.

## Build order

robots.txt check (done) → parser with HTML fixtures (done) → coordinate
resolution (done, per-station map page — `ajax.php?act=map` bulk endpoint is
dead) → schema + upsert (done) → first live poll (done, 2026-07-09) → JSON
export (done: `export.py`) → Actions workflow (done and running live:
`.github/workflows/poll.yml` cron has fired every ~12 h without a miss since
2026-07-12) → **dashboard v1** (done, committed, live at
https://nickeniklas.github.io/fuel-dash/) → **dashboard UX pass** (done and
committed 2026-07-19, commit `a1e5e07`: clickable price-table rows and map
popup buttons load a station into the trend chart and scroll to it, keeping
the station `<select>` in sync; starred favorites persist in `localStorage`
and pin to the top of the price table with quick-switch chips above the trend
chart; a live name search filters the price table) → **table/dropdown UX
pass** (done 2026-08-08, verified in Node against live `site/data/*.json`,
not yet committed: click-to-sort table headers — Station, Price, Reported,
vs 7d avg — with `aria-sort` and an arrow indicator, null averages always
sort last; the station picker groups by report frequency
(`MIN_TREND_POINTS = 3`) into "frequently reported" / "rarely reported"
optgroups with per-station point counts in the labels, repopulated on fuel
change, plus a note near the trend chart when the selected station is
sparse; graded staleness replaces the old binary stale flag — fresh / stale
(0.5 dim, unchanged) / abandoned (`SOURCE_WINDOW_DAYS = 5`, stronger dim
plus a marker on the date cell). All in `site/app.js` / `index.html` /
`style.css`, no new dependencies) → **currently: letting data accumulate.**
As of 2026-08-08: 120 stations (all geocoded), 476 price rows, dates
2026-07-05 to 2026-08-08 (35 days of median history — but see the gotcha
below, per-station report volume hasn't grown much with it). v2 (heatmap,
fill-now-or-wait signal) waits until report volume itself grows, not just
wall-clock time — not there yet.

## Gotchas

- `DD.MM.` dates have no year: resolve with the rollover rule in `docs/SCRAPER.md`
- Regional pages omit the `E10` class on rows: parse by 5-td count, not class
- Strip the `*` / `<span class="E99">` V-Power marker from 98E cells
- Skip rows without a map link (~5–8 %, no station ID)
- Sanity bounds: price 0.80–4.00 EUR, Finland bbox lat 59.7–70.1, lon 20.5–31.6
- No backfill is possible: history starts at first poll, 5 days visible at most
- `ajax.php?act=map` (bulk coord endpoint) is dead — always returns HTTP 200
  with an empty body, tested every param/method/header combo. Coords come
  from the per-station map page (`index.php?cmd=map&id=<id>`) instead, one
  request per new station, cached forever. Detail: `docs/SCRAPER.md`.
- GITHUB_TOKEN-authored pushes don't trigger other workflows' `push` triggers
  — `poll.yml`'s commit of `fuel.db`/`site/data/*.json` won't fire `pages.yml`
  even though it touches `site/**`. `poll.yml` has its own deploy job instead,
  sharing the `pages` concurrency group with `pages.yml` so they never race.
- Favorites are stored client-side under the `localStorage` key
  `fuel-dash:favorites` (array of station ids). Ids no longer present in
  `stations.json` are pruned automatically on load, so a stale favorite never
  breaks rendering.
- Report volume is much sparser than wall-clock time suggests: 89 → 120
  stations and only 474 → 476 price rows between 2026-07-16 and 2026-08-08
  (measured live). Most rows are still each station's initial 5-day batch
  from the poll that first found it; ongoing re-reports are rare. This is
  why the station picker groups by report frequency and why a station's
  `history.json` array length overstates useful trend data — always count
  non-null entries for the *active fuel*, not raw array length
  (`computeStationPointCount` in `app.js`).
- `STALE_DAYS` (2) was measured live 2026-08-08 before touching it: only
  ~20% of stations are "fresh" at that threshold. But ~59% of all stations
  are past `SOURCE_WINDOW_DAYS` (5) entirely — genuinely no longer visible
  on the source, not just slow to update. Kept `STALE_DAYS` at 2; the real
  fix was splitting "stale" from "abandoned" into graded dimming, not
  loosening the fresh/stale line.
