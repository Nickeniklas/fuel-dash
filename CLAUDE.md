# CLAUDE.md

Helsinki fuel price tracker. Polls the unofficial Tankille API on a GH Actions cron,
accumulates history in SQLite, publishes a static Chart.js dashboard on GH Pages.
Full plan: `docs/PLAN.md`. API contract: `docs/API.md`. Read both before coding.

## Stack (decided — do not re-litigate without being asked)

Python + `requests` + SQLite for the poller. Static HTML + Chart.js in `site/` for
the dashboard. GH Actions cron (3 h) runs poller + export + commit. GH Pages serves
`site/` via the official Pages actions.

## Hard rules

- Credentials live in `.env` (gitignored) locally and Actions secrets in CI.
  Never in code, never committed, never printed in logs.
- Drop the API's `reporter` field at ingest. No reporter column exists. Do not add one.
- Ingest ALL fuel tags. Filtering to 95/98/dsl happens only in export/display.
- Be polite to the API: one location request per poll, 3 h cadence, honest User-Agent,
  no retry storms. This is an unofficial API — don't get it killed.
- The dashboard reads only `site/data/*.json`. It never touches the DB.
- Plan docs stay in `docs/`, site in `site/` — `docs/` must never be published by Pages.
- No autonomous git commits or pushes during development sessions. The Actions
  workflow bot commits on schedule; that is the only automated committer.

## Build order

1. `tankille_client.py` (auth + two GET endpoints, see docs/API.md)
2. `poller.py` + schema init + `INSERT OR IGNORE` dedupe
3. First-run backfill (14-day per-station history)
4. `export.py` → JSON contract in docs/PLAN.md
5. Dashboard v1: current table w/ 7d-avg coloring, per-station trend, area medians
6. Workflows: cron poll+commit, Pages deploy
7. v2 (heatmap, fill-now signal) is deferred — needs weeks of data. Do not build.

## Gotchas

- Access token: 12 h lifetime, cache ~10 h, refresh via `/auth/refresh`
- Login `device` string can get blacklisted — use the one in docs/API.md
- `location=` query param is **lon,lat**, not lat,lon
- GH cron schedules die after ~60 days of repo inactivity; self-commits keep it alive
