# STATUS_LOG — fuel-dash

Dated status history moved out of `CLAUDE.md`, newest first. Text under each
date is verbatim from `CLAUDE.md` as it stood before the 2026-11-09 cleanup
(the `→` fragments come from its single run-on "Build order" paragraph).
Current state lives in `CLAUDE.md`; the longer dated build narrative lives in
the "Build order" and "Resolved" sections of `docs/PLAN.md`.

## 2026-11-09

CLAUDE.md cleanup: dated status text moved here; current sections re-verified
against the code, `fuel.db` / `eu.db` (local checkout at the 2026-10-16 03:42 UTC
poll commit) and git history. Corrections made to the current sections:

- The claim that the poll cron "has fired every ~12 h without a miss since
  2026-07-12" conflicted with the 12-day outage (2026-09-04 → 2026-09-15)
  recorded in the same file. Current text now names the outage.
- The table/dropdown UX pass was recorded as "committed 2026-09-03 as part of
  `06dcc4e`"; git history shows it landed in `8ac781b` on 2026-08-08. The
  verbatim 2026-08-08 entry below is left as written.
- "`db.connect()` opens `fuel.db`, `db.connect_eu()` opens `eu.db`": both take a
  path argument; the file names come from the callers' `DB_PATH` / `EU_DB_PATH`.
- The weekly commentary routine was recorded as reading the exports from
  raw.githubusercontent.com, but `site/data/*.json` has been untracked since
  `49a49e1` (2026-09-07), so that path no longer carries current data.
- Data counts refreshed (stations, rows, date range, per-station depth, EU rows).
- Map basemap (Esri World Dark Gray Canvas, replacing CARTO on 2026-10-16,
  commit `754c575`) was missing from CLAUDE.md; added.

## 2026-09-20

→ **currently: letting data accumulate.**
As of 2026-09-20: 127 stations (all geocoded), 3123 price rows, dates
2026-07-05 to 2026-09-19. `medians.json` holds **65 days of data across a
77-day span, with a 12-day hole at 2026-09-04 → 2026-09-15**. The hole is a
polling outage: the GitHub account was suspended, the cron could not run, and
the source only exposes ~5 days of history, so everything older than that was
unrecoverable when polling resumed on 2026-09-20. **No backfill exists and
none ever will** — do not treat the gap as a bug to be repaired. The median
series is still the deepest thing here, just no longer unbroken. Per-station
history remains thin: 1086 dated rows across 127 stations, **median 7 points
per station, only 9 stations with 20+** (see the gotcha below). That asymmetry
is exactly why the dashboard was reframed around the area median plus official
long-range context, and why per-station trend is
now a secondary lookup rather than the headline. v2 (heatmap,
fill-now-or-wait signal) still waits on per-station report volume, not
wall-clock time — not there yet.

From the `medians.json` null-medians gotcha:

Since 2026-09-20 `build_medians` emits one entry per calendar date
from the first observed date to the last, so a date nobody reported on is
present with `"95"`, `"98"` and `"dsl"` all `null` rather than missing from
the array.

From the per-station sparseness gotcha:

The area median is the opposite story and is genuinely deep (65 days over a
77-day span), which is why the reframe leans on it plus the EU bulletin.

## 2026-09-03

**Two data sources** since 2026-09-03: the polttoaine.net scrape (per-station,
Helsinki area, history starts at our first poll) and the EU Weekly Oil Bulletin
(one official national figure per week per country, back to 2005). They live in
separate SQLite files and are never joined.

`openpyxl` was added 2026-09-03 for the EU bulletin's XLSX workbook — the only
dependency added since the original three.

→
**EU Weekly Oil Bulletin ingest +
dashboard reframe** (done 2026-09-03, committed as `06dcc4e` (code) and
`49655ae` (`eu.db` + `eu_weekly.json`), both pushed to `origin/main`:
`eu_bulletin.py` fetches one stable XLSX URL and upserts FI/SE/DE/IT ×
95/diesel × both tax variants into `eu.db` (17,308 rows, 1082 weekly dates,
2005-01-03 to 2026-08-31), self-gated so the 12 h cron only downloads when our
newest week is more than `GATE_DAYS` (8) old; `export.py` adds
`site/data/eu_weekly.json`; the dashboard was reordered to Prices → Map → Area
median → Long-term context → Station trend, with an FI national weekly overlay
plus cents-per-litre gap readout on the median chart, a new 2005-onwards
context chart with a 1/3/5/all year range selector, a computed coverage line,
the EU + polttoaine footer credits, and the rarely-reported station group
collapsed behind a checkbox) →

From the per-station sparseness gotcha:

Measured live 2026-09-03: 2775 price rows sounds healthy, but they spread
across 124 stations as 967 dated station-days — **median 6 points per
station, only 7 stations with 20+**. Most rows are still each station's
initial 5-day batch from the poll that first found it; ongoing re-reports on
already-known stations are rare.

From the EU bulletin workbook layout gotcha:

**EU bulletin workbook layout** (all verified live 2026-09-03 before any
parser code was written — full detail in `docs/SCRAPER.md`):

## 2026-08-08

→ **table/dropdown UX
pass** (done 2026-08-08, verified in Node against live `site/data/*.json`:
click-to-sort table headers — Station, Price, Reported,
vs 7d avg — with `aria-sort` and an arrow indicator, null averages always
sort last; the station picker groups by report frequency
(`MIN_TREND_POINTS = 3`) into "frequently reported" / "rarely reported"
optgroups with per-station point counts in the labels, repopulated on fuel
change, plus a note near the trend chart when the selected station is
sparse; graded staleness replaces the old binary stale flag — fresh / stale
(0.5 dim, unchanged) / abandoned (`SOURCE_WINDOW_DAYS = 5`, stronger dim
plus a marker on the date cell). All in `site/app.js` / `index.html` /
`style.css`, no new dependencies; committed 2026-09-03 as part of `06dcc4e`) →

`STALE_DAYS` (2) was measured live 2026-08-08 before touching it: only
~20% of stations are "fresh" at that threshold. But ~59% of all stations
are past `SOURCE_WINDOW_DAYS` (5) entirely — genuinely no longer visible
on the source, not just slow to update.

From the per-station sparseness gotcha:

(Earlier readings of the same pattern:
89 → 120 stations against 474 → 476 rows between 2026-07-16 and 2026-08-08.)

## 2026-07-19

→ **dashboard UX pass** (done and
committed 2026-07-19, commit `a1e5e07`: clickable price-table rows and map
popup buttons load a station into the trend chart and scroll to it, keeping
the station `<select>` in sync; starred favorites persist in `localStorage`
and pin to the top of the price table with quick-switch chips above the trend
chart; a live name search filters the price table) →

## 2026-07-16

The repo went through two renames
(`gas-price-dashboard` → `helsinki-fuel-dash` → `fuel-dash`, 2026-07-16) to
land on a name that doesn't bake in a city, since the plan is to broaden past
Helsinki eventually. GitHub Pages URLs follow the current repo name
automatically; local clones need `git remote set-url origin` updated by hand
if they predate a rename — it does not happen on its own.

## 2026-07-12

→ JSON
export (done: `export.py`) → Actions workflow (done and running live:
`.github/workflows/poll.yml` cron has fired every ~12 h without a miss since
2026-07-12; the workflow now runs `poll.py` → `eu_bulletin.py` → `export.py`, then
commits `fuel.db`/`eu.db` and deploys Pages from the same job) →
**dashboard v1** (done, committed, live at
https://nickeniklas.github.io/fuel-dash/)

## 2026-07-09

robots.txt check (done) → parser with HTML fixtures (done) → coordinate
resolution (done, per-station map page — `ajax.php?act=map` bulk endpoint is
dead) → schema + upsert (done) → first live poll (done, 2026-07-09)

## 2026-07-08

History note: the project originally targeted the unofficial Tankille API. It
blocked us (2026-07-08) and was dropped entirely, clean DB, no workarounds. Do not
suggest going back to it.
