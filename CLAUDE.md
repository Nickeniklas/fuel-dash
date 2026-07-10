# CLAUDE.md — helsinki-fuel-dash

Personal fuel price tracker for the Helsinki area. Poller scrapes polttoaine.net
into SQLite on a GH Actions cron, exports JSON, static Chart.js dashboard on
GH Pages reads it. Full plan: `docs/PLAN.md`. Scraper contract: `docs/SCRAPER.md`.

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
dead) → schema + upsert (done) → first live poll (done, 2026-07-09: 76
stations, 224 prices) → **JSON export → Actions workflow → dashboard v1**
(next). v2 (heatmap, fill-now-or-wait signal) waits until weeks of data exist.

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
