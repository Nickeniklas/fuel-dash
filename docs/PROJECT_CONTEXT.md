PROJECT CONTEXT — fuel-dash

Paste-ready summary for the Claude project. Condensed from docs/PLAN.md
(replanned 2026-07-08); if the plan changes, update both.

Status (2026-09-03)

Both data pipelines are built and running. Build order is done through step 8
of 9: parser, coordinate resolution, SQLite schema/upsert, poller (poll.py),
EU bulletin ingest (eu_bulletin.py), JSON export (export.py), the GH Actions
poll+deploy workflow (.github/workflows/poll.yml), and the dashboard
(site/index.html, style.css, app.js). 92 Python unit tests pass, no network in
any of them. Live at https://nickeniklas.github.io/fuel-dash/. The cron has
fired every ~12 h without a miss since 2026-07-12; production is stable.
Currently in step 9: letting per-station report volume (not wall-clock time)
accumulate toward the bar for v2.

Data as of 2026-09-03: fuel.db has 124 stations (all geocoded) and 2775 price
rows over dates 2026-07-05 to 2026-09-02. eu.db has 17,308 bulletin rows over
1082 weekly dates, 2005-01-03 to 2026-08-31.

The two series have very different depth and the dashboard is built around
that. The area median is solid: 60 unbroken days. Per-station history is not:
967 dated rows across 124 stations, median 6 points per station, only 7
stations with 20+. Most rows are still each station's initial 5-day batch from
the poll that first found it; ongoing re-reports on already-known stations are
rare. See the report-volume note below.

Uncommitted or unpushed: the 2026-09-03 work is committed as 06dcc4e (code)
and 49655ae (eu.db + eu_weekly.json) but not yet pushed. main is ahead of
origin/main by 2. The first push puts a ~1.15 MB blob in history permanently.
That is intended but deliberate.

The project

Niklas (GitHub: Nickeniklas) is building a personal fuel price tracker for the
Helsinki area. No service provides long-term price trends or a sorted area-wide
list, so this project collects its own history and visualizes it.

History: the original plan used the unofficial Tankille API. It blocked us on
day one (2026-07-08) and was dropped completely, clean DB, no workarounds.
Don't suggest returning to it.

Repo renamed 2026-07-16 (gas-price-dashboard, then helsinki-fuel-dash, then
fuel-dash) to drop the city name from the project's identity ahead of possible
international expansion. The Helsinki-area scope itself hasn't changed, only
the name.

Two sources since 2026-09-03

1. polttoaine.net scrape, per-station Helsinki-area prices. Independent
   crowdsourced price site (~395 active stations, reports visible 5 days, plain
   HTML, no auth). Parsing spec derived from Pumperly (GPL-3.0), spec only, no
   code copied, documented in docs/SCRAPER.md.
2. EU Weekly Oil Bulletin (European Commission, DG Energy), official national
   weekly prices back to 2005. Not a scrape: one stable XLSX URL (~4.5 MB)
   holding the whole history, refreshed weekly. Exists because source 1 has no
   history before our first poll and its per-station volume is thin.

They live in separate SQLite files (fuel.db and eu.db) and are never joined.

How it works

Poller: Python + requests + SQLite (poll.py), GH Actions cron every 12 h.
Crawls a config list of pages (Helsinki, PK-Seutu, Kehä I, Kehä III), dedupes
stations across pages by the cmd=map&id= station ID, backfills coords for new
stations. No backfill exists in this source, so history accumulates from the
first poll.

EU ingest: eu_bulletin.py mirrors poll.py's shape (fetch, parse, upsert,
idempotent). Stores FI/SE/DE/IT × 95/diesel × both tax variants. Self-gated on
GATE_DAYS (8): if the newest stored week is fresher than that it logs and exits
0 without downloading, so the 12 h cron costs one download per weekly bulletin
rather than ~14. Pass --file <path> to parse a local copy and bypass the gate.

Export: export.py reads fuel.db for site/data/stations.json (all stations,
coords, latest price per fuel), history.json (per-station history) and
medians.json (daily area median per fuel), and eu.db for eu_weekly.json
(FI/SE/DE/IT, 95/dsl, with-taxes only, EUR/L). Exact shapes in
site/data/README.md. A missing or empty eu.db is a logged skip, not an error;
the dashboard degrades to no national context.

Workflow: .github/workflows/poll.yml runs poll.py, then eu_bulletin.py, then
export.py, commits fuel.db + eu.db back to main (skipped if nothing changed),
then deploys site/ to GH Pages — all in one job. site/data/*.json is gitignored
(it is a pure derivative of the two DBs, and committing it grew the repo on
every poll), so the JSON exists only in the runner workspace and the artifact
upload has to sit in the same job as the export; a separate deploy job checking
out main would find no data. The commit step does git pull --rebase origin main
before pushing, because the job checks out main at the start: a manual push
landing mid-run used to make the push non-fast-forward, failing the run and
losing that poll's data until the next cron. It shares the "pages" concurrency
group with pages.yml, because GITHUB_TOKEN-authored pushes don't trigger other
workflows' push triggers, so poll.yml has to do its own deploy. pages.yml, which
covers manual pushes touching site/**, likewise runs export.py against the
committed fuel.db + eu.db before uploading, or it would deploy a dataless site.

Dashboard: static HTML + Chart.js 4.4.1 + Leaflet 1.9.4 in site/, no framework
and no build step, served by GH Pages, reading only site/data/*.json. Dark
theme, CartoDB dark_matter tiles. Sticky fuel (95/98/dsl) and radius (15 km /
all) controls. Page order since the 2026-09-03 reframe:

- Coverage line, computed from the loaded JSON (station count, report count,
  median span), never hardcoded
- Prices table: cheapest-first, colored vs each station's own 7-day average,
  click-to-sort headers (Station/Price/Reported/vs 7d avg, aria-sort, null
  averages always last in both directions), starred favorites pinned above a
  divider, live name search
- Map: Leaflet, marker color showing spatial cheapness vs the displayed set's
  median, popups with a "View trend" button
- Area median: lines for 95/98/dsl, plus a dashed muted FI national weekly
  overlay on the same y axis and a cents-per-litre gap readout using the most
  recent week present in both series. On 98E the overlay is hidden with a note
  (the bulletin has no 98E series; substituting 95 would be quietly wrong)
- Long-term context: the 2005-onwards national series, 95 and dsl only, with a
  1/3/5/all year range selector windowed from the newest bulletin week
- Station trend: last, under a subheading stating its limits. Picker grouped
  into "frequently reported" / "rarely reported" optgroups by per-fuel point
  count (MIN_TREND_POINTS = 3); the rarely-reported group is collapsed behind a
  fuel-dash:show-sparse checkbox, and row-click / map-popup paths
  reveal-and-select so the picker always shows what the chart is showing
- Footer credits both polttoaine.net and the EU bulletin (the latter is a
  licence condition, don't drop it)

Staleness is graded, not binary: fresh, stale (STALE_DAYS = 2, 0.5 opacity), or
abandoned (past SOURCE_WINDOW_DAYS = 5, i.e. no longer visible on the source at
all: stronger dimming plus a marker on the date cell). Reference date comes
from the newest date in medians.json, never the browser clock.

Config constants at the top of app.js: HELSINKI_CENTER, RADIUS_KM,
AVG_WINDOW_DAYS, STALE_DAYS, SOURCE_WINDOW_DAYS, COLOR_EPSILON,
MIN_TREND_POINTS, EU_COUNTRY, EU_RANGE_YEARS_DEFAULT, EU_RANGE_OPTIONS,
EU_CONTEXT_FUELS.

v2, deferred until per-station report volume grows: day-of-week / price-cycle
heatmap, "fill now or wait" signal.

Key decisions and rules

Ingest every row from every configured page; the 15 km Helsinki radius is a
display-time filter in the dashboard (config), never an ingest filter.
Dedupe on UNIQUE(station_id, fuel, date); source has date-only resolution
(DD.MM., no year: rollover rule resolves it), latest price wins within a day.
Coordinates are static: cached in the stations table, fetched once per new
station. The hoped-for ajax.php?act=map bulk endpoint is dead (HTTP 200 with an
empty body under every param/method/header combination tried, 2026-07-09).
Coords come from one request per new station's map page instead, cached forever.
Parse rows by 5-td count, not class (regional pages omit the E10 class); strip
the V-Power */E99 marker from 98E; skip the ~5-8 % of rows without map links;
decode pages as cp1252 explicitly.
Sanity bounds: price 0.80-4.00 EUR, Finland bbox lat 59.7-70.1, lon 20.5-31.6.
EU bulletin specifics: find columns by their row-1 code, never by offset
(country blocks are 7 or 8 columns wide, non-euro countries carry an extra
exchange-rate column); non-euro prices are already in EUR, do not apply the
exchange rate; verify the row-3 unit reads "1000 l" before taking a column;
divide by 1000 at ingest. With-taxes rows use the shared 0.80-4.00 bounds;
without-taxes rows use EU_PRETAX_PRICE_MIN (0.10), because the retail floor
rejected 84 % of real pre-tax rows.
Two databases on purpose: putting eu_weekly in fuel.db grew it from 192 KB to
1.34 MB, a blob git would rewrite twice a day for data that changes weekly.
db.connect() opens fuel.db, db.connect_eu() opens eu.db, nothing joins across.
Politeness is hard policy: 12 h cadence, 100 ms between requests, honest
User-Agent (same one for the bulletin), respect robots.txt. This is someone
else's crowdsourced site.
GH Pages serves site/, never docs/ (plan docs live there).
No LLM in the poller (deterministic script; Claude Code Routine rejected).
GITHUB_TOKEN-authored pushes don't trigger other workflows' push triggers, so
poll.yml can't rely on pages.yml firing after its commit. It has its own deploy
job instead, sharing the "pages" concurrency group.

Report-volume reality check

Measured repeatedly: 2026-07-16 to 2026-08-08 the station count grew 89 to 120
while price rows barely moved, 474 to 476. By 2026-09-03 the total row count
had grown to 2775, but per-station depth had not: median 6 points per station,
only 7 stations with 20+. Most of the count is still each station's initial
5-day batch from the poll that discovered it. This is why the v2 bar is report
volume rather than elapsed time, why the staleness and picker UI treat
"reported once, long ago" as materially different from "reported recently", and
why the 2026-09-03 reframe demoted per-station trend to a secondary lookup.

Open items

- eu.db and eu_weekly.json committed locally but not pushed (main ahead of
  origin/main by 2)
- SE/DE/IT bulletin rows are stored and exported but not displayed. Showing one
  is a display-only change (EU_COUNTRY in app.js)
- Without-taxes rows are stored but never exported. A tax-share view would only
  need export.py plus dashboard changes, no re-ingest
- The exact page list for coverage may grow; it's a config list
- The 117-check jsdom front-end harness used to verify the reframe is
  scratchpad-only and not committed. Worth deciding whether to bring a version
  of it in as a real dev dependency if front-end regressions become recurring

Niklas's working context

Builds with Claude Code on Windows. Comfortable with Python, SQLite, Git, GH
Actions, Chart.js (used in his tech-digest and news-summarizer projects).
Prefers minimal direct answers, no em dashes, English responses. Planning and
implementation are kept in separate conversations: he plans and scopes in a
chat, then runs the resulting kickoff prompt in a Claude Code session. Global
rule: Claude Code never commits or pushes autonomously, all commits and pushes
are manual.

Documentation files: docs/PROJECT_CONTEXT.md (this file, condensed entry
point), docs/PLAN.md (architecture and decisions), docs/SCRAPER.md (source
contracts for both sources), CLAUDE.md (operating brief for Claude Code
sessions), README.md, site/data/README.md (export shapes).
