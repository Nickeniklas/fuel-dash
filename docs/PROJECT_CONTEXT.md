PROJECT CONTEXT — fuel-dash

Paste-ready summary for the Claude project. Written by the design chat after a
project-knowledge sync, from live repo state. Condensed from docs/PLAN.md
(replanned 2026-07-08); if the plan changes, update both.

Status (2026-09-20)

Both data pipelines are built and running. Build order is done through step 8
of 9: parser, coordinate resolution, SQLite schema/upsert, poller (poll.py),
EU bulletin ingest (eu_bulletin.py), JSON export (export.py), the GH Actions
poll+deploy workflow (.github/workflows/poll.yml), and the dashboard
(site/index.html, style.css, app.js). 99 unit tests pass, no network in any of
them. The suite is unittest, not pytest; pytest is not installed and is not in
requirements.txt, which CI pip installs on every poll. Run it with
python -m unittest discover -s tests -t .

Live at https://nickeniklas.github.io/fuel-dash/. The cron fired every ~12 h
without a miss from 2026-07-12 until the outage below, and is back on cadence
since 2026-09-20. Currently in step 9: letting per-station report volume (not
wall-clock time) accumulate toward the bar for v2.

Data as of 2026-09-20: fuel.db has 127 stations (all geocoded) and 3123 price
rows over dates 2026-07-05 to 2026-09-19. eu.db has 17,340 bulletin rows over
1084 weekly dates, 2005-01-03 to 2026-09-14.

The polling outage (2026-09-04 to 2026-09-15)

The GitHub account was suspended, so the cron could not fire for 12 days. When
polling resumed on 2026-09-20 it recovered 2026-09-16 onward, which is all the
source's ~5-day visibility window still held. Everything older is permanently
lost. No backfill exists and none ever will. Do not treat the gap as a bug to
be repaired, and do not spend a session trying to reconstruct it.

The area median series is therefore 65 days of data across a 77-day span, with
a 12-day hole. It is still the deepest per-station-area thing in the project,
just no longer unbroken. The "60 unbroken days" phrasing in older docs was true
when written and is kept in docs/PLAN.md as the record of why the 2026-09-03
reframe happened.

Nulls in medians.json (read this before touching any consumer)

Since 2026-09-20, build_medians emits one entry per calendar date from the
first observed date to the last. A date nobody reported on is present with
"95", "98" and "dsl" all null, rather than missing from the array. Nothing is
padded outside the observed range, so the first and last entries always hold
real data.

This exists because the dashboard plots medians on a categorical x-axis, where
an absent date is an absent label. Before the fix the line closed over the
outage and read as an unbroken 77-day series, which was the misleading failure
rather than the ugly one.

Consequences for anything reading the file:

- last-entry lookups must scan back to the last non-null entry
  (computeReferenceDate does this)
- deltas and reduces must skip nulls
- medians.length is now a calendar span, not a count of days with data
- this applies outside the repo too. The weekly Claude commentary routine reads
  these exports straight from raw.githubusercontent.com and gets no other
  warning

Chart behaviour is opt-in per chart, not global. fuelDatasets takes a spanGaps
option defaulting to true, and only the median chart passes false. The station
trend chart still spans deliberately, because per-station reports are sparse by
nature (median 7 points) and breaking those lines leaves mostly dots. The EU
overlay sets its own spanGaps at dataset level: it is a weekly series on a daily
axis, null six days in seven by design.

The coverage line reports days-with-data, calendar span and missing days
separately, all computed from the loaded JSON. Neither the gap nor its size is
hardcoded anywhere in the codebase.

The project

Niklas (GitHub: Nickeniklas) is building a personal fuel price tracker for the
Helsinki area. No service provides long-term price trends or a sorted area-wide
list, so this project collects its own history and visualizes it.

History: the original plan used the unofficial Tankille API. It blocked us on
day one (2026-07-08) and was dropped completely, clean DB, no workarounds.
Don't suggest returning to it.

Repo renamed 2026-07-16 (gas-price-dashboard, then helsinki-fuel-dash, then
fuel-dash) to drop the city name ahead of possible international expansion. The
Helsinki-area scope itself hasn't changed, only the name.

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
The gate was verified live on 2026-09-20: 20 days stale, so it downloaded and
picked up the two missed weeks, exactly +32 rows (2 weeks × 4 countries × 2
fuels × 2 tax variants).

Export: export.py reads fuel.db for site/data/stations.json (all stations,
coords, latest price per fuel), history.json (per-station history) and
medians.json (daily area median per fuel, gap-filled as described above), and
eu.db for eu_weekly.json (FI/SE/DE/IT, 95/dsl, with-taxes only, EUR/L). Exact
shapes in site/data/README.md, which export.py writes. A missing or empty eu.db
is a logged skip, not an error; the dashboard degrades to no national context.

Workflow: .github/workflows/poll.yml runs poll.py, then eu_bulletin.py, then
export.py, commits fuel.db + eu.db back to main (skipped if nothing changed),
then deploys site/ to GH Pages, all in one job. site/data/*.json is gitignored
(a pure derivative of the two DBs, and committing it grew the repo on every
poll), so the JSON exists only in the runner workspace and the artifact upload
has to sit in the same job as the export; a separate deploy job checking out
main would find no data. The commit step adds only fuel.db eu.db, verified live
on 2026-09-20 (the bot commit contained those two files and no JSON). The
commit step does git pull --rebase origin main before pushing, because the job
checks out main at the start: a manual push landing mid-run used to make the
push non-fast-forward, failing the run and losing that poll's data. It shares
the "pages" concurrency group with pages.yml, because GITHUB_TOKEN-authored
pushes don't trigger other workflows' push triggers, so poll.yml has to do its
own deploy. pages.yml, which covers manual pushes touching site/**, likewise
runs export.py against the committed fuel.db + eu.db before uploading, or it
would deploy a dataless site.

Dashboard: static HTML + Chart.js 4.4.1 + Leaflet 1.9.4 in site/, no framework
and no build step, served by GH Pages, reading only site/data/*.json. Dark
theme, CartoDB dark_matter tiles. Sticky fuel (95/98/dsl) and radius (15 km /
all) controls. Page order since the 2026-09-03 reframe:

- Coverage line, computed from the loaded JSON (station count, report count,
  median days-with-data, span and missing days), never hardcoded
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
all: stronger dimming plus a marker on the date cell). Reference date comes from
the newest non-null date in medians.json, never the browser clock.

Config constants at the top of app.js: HELSINKI_CENTER, RADIUS_KM,
AVG_WINDOW_DAYS, STALE_DAYS, SOURCE_WINDOW_DAYS, COLOR_EPSILON,
MIN_TREND_POINTS, EU_COUNTRY, EU_RANGE_YEARS_DEFAULT, EU_RANGE_OPTIONS,
EU_CONTEXT_FUELS.

v2, deferred until per-station report volume grows: day-of-week / price-cycle
heatmap, "fill now or wait" signal. The outage set the timeline back but did not
change the bar.

Key decisions and rules

Ingest every row from every configured page; the 15 km Helsinki radius is a
display-time filter in the dashboard (config), never an ingest filter.

Pumperly (GPL-3.0) is spec only. Never copy, port or paraphrase its code. Page
format facts live in docs/SCRAPER.md; code against that doc.

Politeness is non-negotiable: 12 h cadence, 100 ms between requests, honest
User-Agent, respect robots.txt. This is someone else's crowdsourced site.

eu_weekly lives in eu.db, never in fuel.db. fuel.db is committed on every 12 h
poll; merging the bulletin in grew it from 192 KB to 1.34 MB and would have git
rewrite that blob twice a day for data that changes weekly. db.connect() opens
fuel.db, db.connect_eu() opens eu.db.

The EU bulletin attribution in the dashboard footer is a licence condition.
Do not remove it.

The bulletin has no 98E series. When 98E is selected the dashboard hides the
national overlay and says so; never substitute the 95 series.

site/data/*.json is gitignored and generated at deploy time. site/data/README.md
stays tracked: it is documentation, even though export.py rewrites it each run.

GITHUB_TOKEN-authored pushes don't trigger other workflows' push triggers, so
poll.yml can't rely on pages.yml firing after its commit. It has its own deploy
job instead, sharing the "pages" concurrency group.

Report-volume reality check

Measured repeatedly: 2026-07-16 to 2026-08-08 the station count grew 89 to 120
while price rows barely moved, 474 to 476. By 2026-09-03 the total row count had
grown to 2775, but per-station depth had not: median 6 points per station, only
7 stations with 20+. As of 2026-09-20 it is 1086 dated rows across 127 stations,
median 7 points per station, only 9 with 20+. Most of the count is still each
station's initial 5-day batch from the poll that discovered it. This is why the
v2 bar is report volume rather than elapsed time, why the staleness and picker
UI treat "reported once, long ago" as materially different from "reported
recently", and why the 2026-09-03 reframe demoted per-station trend to a
secondary lookup.

Documentation layout and the rules governing it

- docs/PROJECT_CONTEXT.md (this file): condensed entry point. Written by the
  design chat after a project-knowledge sync, not by the Claude Code session,
  and rewritten wholesale rather than patched.
- docs/PLAN.md: architecture, the decisions table, and the dated build log.
  Append-only. Entries record what was true when written; a superseded entry
  gets a new entry after it, never an edit in place. The 2026-09-20 outage entry
  is the most recent.
- CLAUDE.md: operating brief for Claude Code sessions. Describes now, and is
  corrected in place when it goes stale.
- README.md: outside view only, after the readme-standard pass on 2026-09-20.
  What it is, requirements, install, verified commands, architecture at reader
  level, limitations, attribution. Stale-by-design figures (row counts, station
  counts, date ranges, test counts) and version history are deliberately banned
  from it and live in CLAUDE.md and PLAN.md instead. Do not put statistics back.
- docs/SCRAPER.md: source contracts for both sources, page format, parse rules,
  EU workbook layout, politeness.
- site/data/README.md: export JSON shapes, generated by export.py, tracked.

Open items

- The out-of-repo weekly commentary routine reads medians.json from
  raw.githubusercontent.com. If it derives "days of data" from array length it
  is now silently wrong, since that length is a calendar span. CLAUDE.md warns
  about it; the routine itself is unfixed.
- SE/DE/IT bulletin rows are stored and exported but not displayed. Showing one
  is a display-only change (EU_COUNTRY in app.js).
- Without-taxes rows are stored but never exported. A tax-share view would only
  need export.py plus dashboard changes, no re-ingest.
- The exact page list for coverage may grow; it's a config list.
- The 117-check jsdom front-end harness used to verify the 2026-09-03 reframe is
  scratchpad-only and not committed. Worth deciding whether to bring a version of
  it in as a real dev dependency if front-end regressions become recurring.
- Gap filling stops at the last observed date, so an ongoing outage reads as a
  series that ends early rather than one with a hole. Acceptable for now; worth
  revisiting if a second outage happens.

Niklas's working context

Builds with Claude Code on Windows. Comfortable with Python, SQLite, Git, GH
Actions, Chart.js. Prefers minimal direct answers, no em dashes, English
responses. Planning and implementation are kept in separate conversations: he
plans and scopes in a chat, then runs the resulting kickoff prompt in a Claude
Code session. Global rule: Claude Code never commits or pushes autonomously, all
commits and pushes are manual. Browser verification of front-end changes is his,
not the agent's; the agent verifies data shape, syntax and logic replay and says
plainly what it could not check.
