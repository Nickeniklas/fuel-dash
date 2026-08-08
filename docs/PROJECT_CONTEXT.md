PROJECT CONTEXT — fuel-dash
Paste-ready summary for the Claude project. Condensed from docs/PLAN.md (replanned
2026-07-08); if the plan changes, update both.

Status (2026-08-08): parser, coordinate resolution, SQLite schema/upsert, the
poller (poll.py), JSON export (export.py), the GH Actions poll+deploy
workflow (.github/workflows/poll.yml), and dashboard v1 (site/index.html,
style.css, app.js) are all built, committed, and live. 52 unit tests pass.
The cron has fired every ~12 h without a miss since 2026-07-12 — production
is stable. fuel.db has 120 stations (all geocoded) and 476 price rows across
dates 2026-07-05 to 2026-08-08 (35 days of median history — but see the
report-volume note below, most rows are still each station's initial batch).
Build order is done through step 7 of 8; currently in step 8, letting report
volume (not just wall-clock time) accumulate toward the bar for v2. Live at
https://nickeniklas.github.io/fuel-dash/. Repo renamed 2026-07-16
(gas-price-dashboard → helsinki-fuel-dash → fuel-dash) to drop the city
name from the project's identity ahead of planned international expansion;
the Helsinki-area scope itself hasn't changed, only the name.

Dashboard UX pass 2026-07-19 (committed, commit a1e5e07): clicking a
price-table row or a map popup's "View trend" button loads that station into
the trend chart and scrolls to it, kept in sync with the station picker;
starred favorites persist in the browser's `localStorage` and pin to the top
of the price table (with an "outside area" hint if a favorite falls outside
the 15 km filter) plus quick-switch chips above the trend chart; and a live
name search filters the price table, with pinned favorites always visible.

Table/dropdown UX pass 2026-08-08 (verified in Node against live
site/data/*.json, not yet committed): price-table headers (Station, Price,
Reported, vs 7d avg) are click-to-sort, with `aria-sort` and an arrow
indicator; averaged-delta sort always puts null-average stations last in
both directions. The station `<select>` now groups stations into
"frequently reported" / "rarely reported" optgroups by a per-fuel point
count (`MIN_TREND_POINTS = 3`), repopulates when the fuel changes, and shows
a note near the trend chart when the selected station is sparse. Staleness
is now graded instead of a single binary flag: fresh, stale (unchanged 0.5
dim, `STALE_DAYS = 2`), or abandoned (`SOURCE_WINDOW_DAYS = 5` — a station
no longer visible on the source at all — stronger dimming plus a marker on
the date cell). A live measurement drove this: at `STALE_DAYS = 2` about 80%
of stations were dimmed, but ~59 percentage points of that 80% were actually
past the 5-day source window entirely, not just briefly stale — so
`STALE_DAYS` itself was left at 2 and the fix was splitting the two cases
visually. All in `site/app.js` / `index.html` / `style.css`, no new
dependencies.

Report-volume reality check (measured 2026-08-08): between 2026-07-16 and
2026-08-08, station count grew 89 → 120 but price rows barely moved,
474 → 476. Most of the row count is still each station's initial 5-day
batch from the poll that first discovered it; ongoing re-reports on
already-known stations are rare. This is the reason the "weeks of data"
bar for v2 is about report volume, not elapsed time, and why the station
picker and staleness UI now treat "reported once, long ago" as materially
different from "reported recently."
The project
Niklas (GitHub: Nickeniklas) is building a personal fuel price tracker for the
Helsinki area. No service provides long-term price trends or a sorted area-wide
list, so this project collects its own history and visualizes it.
History: the original plan used the unofficial Tankille API. It blocked us on day
one (2026-07-08) and was dropped completely, clean DB, no workarounds. Don't
suggest returning to it.
How it works

Source: scraping polttoaine.net, an independent crowdsourced price site
(~395 active stations, reports visible 5 days, plain HTML, no auth). Parsing
spec derived from Pumperly (GPL-3.0), spec only, no code copied, and
documented in docs/SCRAPER.md.
Poller: Python + requests + SQLite (poll.py), GH Actions cron every 12 h.
Crawls a config list of pages (starting: Helsinki, PK-Seutu, Kehä I, Kehä
III), dedupes stations across pages by the cmd=map&id= station ID. No
backfill exists in this source, so history accumulates from the first poll.
Export: export.py reads fuel.db and writes site/data/stations.json (all
stations, coords, latest price per fuel), site/data/history.json
(per-station history), and site/data/medians.json (daily area median per
fuel) — exact shapes in site/data/README.md.
Workflow: .github/workflows/poll.yml runs poll.py, then export.py, commits
fuel.db + site/data/*.json back to main (skipped if nothing changed), then
deploys site/ to GH Pages in the same run. It shares the "pages" concurrency
group with pages.yml, because GITHUB_TOKEN-authored pushes don't trigger
other workflows' push triggers — poll.yml has to do its own deploy.
Dashboard: static HTML + Chart.js + Leaflet in site/, served by GH Pages,
reading only site/data/*.json. Sticky fuel (95/98/dsl) and radius (15 km /
all) controls; a price table colored vs each station's 7-day average, with
click-to-sort headers (Station/Price/Reported/vs 7d avg, null averages
always last) and starred favorites pinned above a divider; a dark Leaflet
map (CartoDB dark tiles) with marker color showing spatial cheapness; a
per-station trend chart with a picker grouped into "frequently reported" /
"rarely reported" optgroups by per-fuel point count, plus a sparse-station
note when relevant; area median lines for 95/98/dsl. Config constants
(HELSINKI_CENTER, RADIUS_KM, AVG_WINDOW_DAYS, STALE_DAYS,
SOURCE_WINDOW_DAYS, COLOR_EPSILON, MIN_TREND_POINTS) live at the top of
app.js. v2 (deferred until report volume, not just elapsed time, grows):
day-of-week heatmap, "fill now or wait" signal.

Key decisions and rules

Ingest every row from every configured page; the 15 km Helsinki radius is a
display-time filter in the dashboard (config), never an ingest filter
Dedupe on UNIQUE(station_id, fuel, date); source has date-only resolution
(DD.MM., no year: rollover rule resolves it), latest price wins within a day
Coordinates are static: cached in a stations table, fetched once per new station.
The hoped-for ajax.php?act=map bulk endpoint turned out dead (always returns an
empty body, tested 2026-07-09) — coords come from one request per new station's
map page instead, cached forever
Parse rows by 5-td count, not class (regional pages omit the E10 class); strip
the V-Power */E99 marker from 98E; skip the ~5-8 % of rows without map links
Sanity bounds: price 0.80–4.00 EUR, Finland bbox lat 59.7–70.1, lon 20.5–31.6
Politeness is hard policy: 12 h cadence, 100 ms between requests, honest
User-Agent, respect robots.txt (someone else's crowdsourced site)
GH Pages serves site/, never docs/ (plan docs live there)
No LLM in the poller (deterministic script; Claude Code Routine rejected)
GITHUB_TOKEN-authored pushes don't trigger other workflows' push triggers, so
poll.yml can't rely on pages.yml firing after its commit — it has its own
deploy job instead, sharing the "pages" concurrency group

Niklas's working context
Builds with Claude Code on Windows. Comfortable with Python, SQLite, Git, GH
Actions, Chart.js (used in his tech-digest and news-summarizer projects). Prefers
minimal direct answers, no em dashes, English responses. Global rule: Claude Code
never commits or pushes autonomously.