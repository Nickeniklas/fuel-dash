# helsinki-fuel-dash — Master Plan

*(Repo name is a suggestion — rename freely, nothing depends on it.)*

## What this is

A self-hosted fuel price tracker for the Helsinki area. Polls the Tankille API on a
schedule, accumulates price history in SQLite, and publishes a static trend dashboard.
Exists because the Tankille app only shows a map view with ~1 week of per-station
history — no "all of Helsinki sorted by price" and no long-term trends. This project
builds the historical dataset nobody serves for free.

Planned 2026-07-08. API details verified from source that day (see docs/API.md).

## Scope

**v1**
- Poller: fetch all stations within radius of Helsinki center, store price reports in SQLite
- One-time backfill: 14 days of per-station history on first run (dashboard is useful on day one)
- Export: SQLite → JSON files for the dashboard
- Dashboard (static HTML + Chart.js):
  1. Current price table, sorted by price, colored vs each station's 7-day average
  2. Per-station price trend chart with station picker
  3. Area median trend lines for 95 / 98 / dsl
- GH Actions cron running poller + export + commit, GH Pages serving the dashboard

**v2 (needs weeks of accumulated data — do not build yet)**
- Day-of-week / time-of-day price pattern heatmap
- "Fill now or wait" indicator based on recent trend direction

## Decisions and rationale

| Decision | Choice | Why |
|---|---|---|
| Data source | Tankille reverse-engineered API (`api.tankille.fi`) | Structured JSON, best coverage, user already has an account. polttoaine.net rejected: HTML scraping, 5-day retention, no station IDs. |
| Client language | Python, sync `requests`, ~100 lines | Adapted from the existing Python client in `aarooh/ha-tankille-deprecated` (aiohttp, 442 lines) — simplify, don't reinvent. Matches user's stack. |
| Fuels | Ingest ALL fuel tags, display 95/98/dsl | Storage is free (same API response). Never filter at ingest; filter at export/display. |
| Area | 15 km radius from Helsinki center, config value | Covers Helsinki + edges of Espoo/Vantaa. Changeable without schema changes. |
| Storage | SQLite, committed to the repo | Few MB/year. Committing doubles as backup. See schema below. |
| Dedupe | `UNIQUE(station_id, fuel, updated)` | API price entries carry their report timestamp, so identical reports insert-or-ignore cleanly. |
| Privacy | Drop the API's `reporter` field at ingest | Public repo must not republish Tankille user IDs. |
| Runner | GH Actions cron, every 3 hours | Free, runs with PC off, deterministic script needs no LLM. Claude Code Routine rejected: spends agent usage on a dumb cron job and requires the machine awake. Local Task Scheduler rejected: PC-dependent. |
| Politeness | 3 h interval, one location request per poll, identifiable User-Agent | Unofficial API, tolerated not blessed. Be chill; don't get it killed for everyone. |
| Hosting | GH Pages via official Pages actions, site in `site/` | Same repo as the Action, zero extra services. Cloudflare Pages works identically but adds nothing. `site/` not `docs/` because plan docs live in `docs/` and must not be published. |
| Secrets | `.env` locally (gitignored), Actions secrets in CI | Same pattern as market-advisor's gitignored portfolio. Credentials never touch git. |
| Charts | Chart.js | User's existing pattern (tech-digest, news-summarizer). |

## Architecture

```
                 every 3 h (GH Actions cron)
                 ┌─────────────────────────────────────┐
 api.tankille.fi │  poller.py ──► tankille.db (SQLite) │
   (1 request)   │                     │               │
                 │  export.py ◄────────┘               │
                 │      │                              │
                 │      ▼                              │
                 │  site/data/*.json                   │
                 │      │                              │
                 │  git commit db + json               │
                 └──────┼──────────────────────────────┘
                        ▼
                 GH Pages deploy (site/ → static dashboard)
```

Only `poller.py` talks to the API. Only `export.py` reads the DB for output. The
dashboard reads only `site/data/*.json` — it never sees the DB.

## SQLite schema

```sql
CREATE TABLE stations (
  id      TEXT PRIMARY KEY,   -- Tankille _id
  name    TEXT NOT NULL,
  chain   TEXT,
  brand   TEXT,
  street  TEXT,
  city    TEXT,
  lat     REAL,
  lon     REAL
);

CREATE TABLE prices (
  station_id TEXT NOT NULL REFERENCES stations(id),
  fuel       TEXT NOT NULL,     -- API tag: 95, 98, dsl, hvo, ngas, ...
  price      REAL NOT NULL,
  updated    TEXT NOT NULL,     -- report timestamp from API
  fetched_at TEXT NOT NULL,     -- when the poller saw it
  UNIQUE (station_id, fuel, updated)
);
-- No reporter column. Deliberate. Do not add it.
```

## Export contract (site/data/)

- `current.json` — latest price per station per fuel, plus each station's 7-day
  average for the color coding, plus station metadata
- `stations/<id>.json` — full price series per station (or one combined file if
  size allows; decide at build time, keep the dashboard code agnostic via a tiny
  fetch helper)
- `median.json` — daily area median per fuel (95/98/dsl) over full history
- `meta.json` — last poll time, station count, radius

## Build order

1. `tankille_client.py` — login/refresh/get_stations_by_location/get_station_prices
2. `poller.py` + schema init + dedupe insert
3. Backfill path (empty DB → per-station 14-day history, ~100–150 requests, once)
4. `export.py` → JSON contract above
5. Dashboard v1 (three views)
6. `.github/workflows/poll.yml` (cron + commit) and Pages deploy workflow
7. Run locally once to seed the DB, push, verify cron and Pages

## Known gotchas

- Access token lives 12 h; refresh via `/auth/refresh`, cache ~10 h (upstream clients do this)
- GH disables cron schedules after ~60 days of repo inactivity; the workflow's own
  commits count as activity, so a working poller keeps itself alive — but if it ever
  breaks silently, the schedule can die with it. `meta.json`'s last-poll timestamp on
  the dashboard is the freshness check.
- Login `device` string matters — upstream reported "Device blacklisted" errors on
  some strings; reuse the one from the HA client
- Cron drift of 5–15 min is normal and irrelevant here

## Open items

- Repo name (suggestion: `helsinki-fuel-dash`)
- Exact Helsinki center coordinates for the radius (pick at build time)
- Single vs per-station JSON split for series data (decide by file size at build time)
