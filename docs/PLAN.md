# PLAN — helsinki-fuel-dash

Replanned 2026-07-08. Original plan (same date) used the unofficial Tankille API;
that source blocked us on day one and this plan replaces it entirely. No workarounds
against Tankille. New source: scraping polttoaine.net.

## What this is

A personal fuel price tracker for the Helsinki area. No existing service shows
long-term price trends or a sorted city-wide list, so this project collects its own
history and visualizes it. Poller collects prices into SQLite, exports JSON, a static
Chart.js dashboard on GH Pages reads the JSON.

## Source: polttoaine.net

Independent crowdsourced fuel price site, ~395 active stations across Finland.
Prices submitted by drivers, each report stays visible 5 days (confirmed from the
site footer, 2026-07-08). Plain server-rendered HTML, no auth, no API key.

Parsing spec derived from reading Pumperly (GPL-3.0). **Spec only: we describe the
page format in our own docs and write our own parser. No code is copied**, keeping
this repo's licensing clean.

Full parsing contract lives in `docs/SCRAPER.md`.

## Scope

**v1**
- Poller on GH Actions cron, every 12 h, scrapes configured polttoaine.net pages
- SQLite DB + exported JSON committed back to the repo
- Dashboard: current prices sorted, colored vs each station's 7-day average;
  per-station trend chart with picker; area median lines for 95E10 / 98E / Diesel

**v2 (deferred until weeks of data exist)**
- Day-of-week / price-cycle heatmap
- "Fill now or wait" signal

No backfill exists in this source (5 days visible, date-only resolution), so history
accumulates from the first poll onward. v2 waits accordingly.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Source | Scrape polttoaine.net | Tankille blocked us; polttoaine is public HTML, no auth, widest crowdsourced coverage (~395 stations) |
| Pumperly usage | Spec only, never code | Pumperly is GPL-3.0; copying code would infect the repo. Page-format facts are not copyrightable |
| Ingest scope | Ingest every row from every configured page, no geographic filter at ingest | More data is strictly better; filtering at ingest throws away history we can never recover |
| Geographic filter | 15 km radius from Helsinki center applied at display time, config value in the dashboard | Keeps the DB complete while the UI stays focused; radius can change later without data loss |
| Old Tankille schema | Dropped, clean DB | Tankille is not coming back soon; its ID space and timestamp semantics don't map to polttoaine anyway |
| Dedupe key | `UNIQUE(station_id, fuel, date)`, same-day re-poll overwrites price | Source has date-only resolution (DD.MM.), no timestamps; latest seen value per day is the best available truth |
| Poll cadence | Every 12 h, 100 ms between page requests, honest User-Agent | Matches Pumperly's observed politeness; with 5-day visibility 12 h loses nothing |
| Coordinates | Cached in a `stations` table, fetched once per new station | Coords are static; refetching per poll is wasted load on their server |
| Coord source | Test `ajax.php?act=map` first (all locations in one call), fallback to per-station map page parse | One request beats N map-page fetches if the endpoint pans out |
| Poller runtime | Plain Python script, no LLM | Deterministic parsing needs no model; decision carried over from the original plan (Claude Code Routine rejected: shouldn't depend on the PC being on) |
| Hosting | GH Actions cron + GH Pages serving `site/`, never `docs/` | Free, no server, already the plan; plan docs live in `docs/` and must not be published |

## Architecture

```
GH Actions cron (12 h)
  └─ poller.py
       ├─ GET configured polttoaine.net pages (100 ms apart)
       ├─ parse rows            → docs/SCRAPER.md is the contract
       ├─ resolve new stations  → stations table (cached coords)
       ├─ upsert prices         → fuel.db (SQLite)
       ├─ export site/data/*.json  (all stations, coords included)
       └─ commit DB + JSON back to repo

GH Pages ── serves site/ ── index.html + Chart.js
                              └─ reads site/data/*.json
                              └─ applies 15 km display radius (config)
```

## Build order

1. Manual robots.txt + terms check on polttoaine.net (open item below, blocks everything)
2. Parser: fetch one city page, parse rows to dicts, unit-test against saved HTML fixtures
3. Coordinate resolution: test `ajax.php?act=map`, else map-page parse; `stations` table
4. SQLite schema + upsert + dedupe
5. JSON export
6. GH Actions workflow: cron, run poller, commit
7. Dashboard v1 views
8. Let data accumulate; revisit v2

## Open items

- `ajax.php?act=map` endpoint unverified: one test fetch decides the coord strategy.
- Exact page list for coverage (Helsinki + PK-Seutu + Kehä I + Kehä III as starting
  set) may grow; it's a config list.
