# PLAN — fuel-dash

Replanned 2026-07-08. Original plan (same date) used the unofficial Tankille API;
that source blocked us on day one and this plan replaces it entirely. No workarounds
against Tankille. New source: scraping polttoaine.net.

## What this is

A personal fuel price tracker for the Helsinki area. No existing service shows
long-term price trends or a sorted city-wide list, so this project collects its own
history and visualizes it. Poller collects prices into SQLite, exports JSON, a static
Chart.js dashboard on GH Pages reads the JSON.

Since 2026-09-03 there are two sources: the polttoaine.net scrape for per-station
Helsinki-area prices, and the EU Weekly Oil Bulletin for official national weekly
prices back to 2005. The second exists because the first has no history before our
first poll and its per-station volume is thin — see the Resolved entry for that
session. They are stored in separate SQLite files and never joined.

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

**v1.5 — official long-range context (done 2026-09-03)**
- EU Weekly Oil Bulletin ingest into its own `eu.db`, FI/SE/DE/IT, 95 + diesel,
  both tax variants, 2005 onwards
- FI national weekly overlay + cents-per-litre gap readout on the area median chart
- Separate 2005-onwards context chart with a 1/3/5/all year range selector
- Page reframed so per-station trend is a secondary lookup, not the headline

**v2 (deferred until per-station report volume exists)**
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
| Coord source | Per-station map page parse | `ajax.php?act=map` bulk endpoint tested 2026-07-09, returns empty under every param/method/header combo tried — not usable. N map-page fetches it is, cached forever per station |
| Poller runtime | Plain Python script, no LLM | Deterministic parsing needs no model; decision carried over from the original plan (Claude Code Routine rejected: shouldn't depend on the PC being on) |
| Hosting | GH Actions cron + GH Pages serving `site/`, never `docs/` | Free, no server, already the plan; plan docs live in `docs/` and must not be published |
| Second source | EU Weekly Oil Bulletin (DG Energy XLSX) | The scrape can never be backfilled and its per-station volume is thin; the bulletin gives official weekly national prices back to 2005 from one stable URL. Licence allows reproduction with acknowledgement |
| Bulletin storage | Own file, `eu.db`, not `fuel.db` | `fuel.db` is committed on every 12 h poll. Merging them grew it 192 KB → 1.34 MB, so git would rewrite that blob twice a day for data that only changes weekly |
| Bulletin cadence | Self-gate in `eu_bulletin.py`, no extra cron | The workbook is ~4.5 MB and updates weekly; the gate skips the download while our newest stored week is under `GATE_DAYS` (8) old, so the existing 12 h cron costs one download per bulletin instead of ~14 |
| Countries stored | FI, SE, DE, IT — only FI displayed | Storing all four now makes adding one later a display change, not a re-ingest |
| 98E national average | Not shown; overlay hidden with a note | The bulletin publishes no 98E series. Substituting the 95 series would be a quietly wrong number |
| Without-taxes floor | Separate `EU_PRETAX_PRICE_MIN` (0.10) | The scraper's 0.80 EUR/L floor assumes tax is included; applied to pre-tax rows it rejected 84% of real data (measured live). The shared 4.00 ceiling still catches unit errors |
| Per-station trend | Demoted to a secondary lookup under an honest subheading | 967 dated rows over 124 stations, median 6 points each, only 7 with 20+ — the data does not support presenting it as a headline feature |

## Architecture

```
GH Actions cron (12 h)          .github/workflows/poll.yml
  ├─ poll.py
  │    ├─ GET configured polttoaine.net pages (100 ms apart)
  │    ├─ parse rows            → docs/SCRAPER.md is the contract
  │    ├─ resolve new stations  → stations table (cached coords)
  │    └─ upsert prices         → fuel.db (SQLite)
  ├─ eu_bulletin.py
  │    ├─ self-gate: newest eu.db week < GATE_DAYS old? exit 0, no download
  │    ├─ GET one stable DG Energy XLSX URL (~4.5 MB)
  │    └─ upsert FI/SE/DE/IT × 95/dsl × both tax variants → eu.db (SQLite)
  ├─ export.py
  │    ├─ fuel.db → site/data/{stations,history,medians}.json
  │    └─ eu.db   → site/data/eu_weekly.json  (skipped + logged if eu.db absent)
  └─ commit fuel.db + eu.db back to repo, then deploy Pages from the runner
       workspace, all in one job (site/data/*.json is gitignored and exists only
       in the workspace, so the artifact upload must share the job that exported
       it; and GITHUB_TOKEN pushes don't trigger pages.yml's push trigger anyway)

GH Pages ── serves site/ ── index.html + Chart.js + Leaflet
                              └─ reads site/data/*.json (eu_weekly.json optional)
                              └─ applies 15 km display radius (config)
```

Two SQLite files on purpose: `fuel.db` changes twice a day, `eu.db` weekly.
`db.connect()` opens the first, `db.connect_eu()` the second.

## Build order

1. Manual robots.txt + terms check on polttoaine.net (done, 2026-07-09: `ajax.php`
   isn't disallowed; nothing else in the crawl path is either)
2. Parser: fetch one city page, parse rows to dicts, unit-test against saved HTML fixtures (done)
3. Coordinate resolution: test `ajax.php?act=map`, else map-page parse; `stations` table (done)
4. SQLite schema + upsert + dedupe (done)
5. JSON export (done, 2026-07-10: `export.py`, 14 unit tests)
6. GH Actions workflow: cron, run poller, commit (done, committed and
   running live: `.github/workflows/poll.yml` has fired every ~12 h without
   a miss since 2026-07-12)
7. Dashboard v1 views (done, committed, live at
   https://nickeniklas.github.io/fuel-dash/: `site/index.html`,
   `style.css`, `app.js`)
8. EU Weekly Oil Bulletin ingest + dashboard reframe (done 2026-09-03,
   committed `06dcc4e` + `49655ae`, not yet pushed: `eu_bulletin.py`,
   `eu.db`, `site/data/eu_weekly.json`, reordered dashboard — see Resolved)
9. Let per-station report volume accumulate (not just elapsed time — see
   Resolved below); revisit v2 (in progress)

## Open items

- Exact page list for coverage (Helsinki + PK-Seutu + Kehä I + Kehä III as starting
  set) may grow; it's a config list.
- `eu.db` and the initial `eu_weekly.json` are committed locally but **not pushed**
  (`main` is ahead of `origin/main` by 2). First push puts a ~1.15 MB blob in
  history permanently — intended, but deliberate.
- SE/DE/IT bulletin rows are stored and exported but not displayed. Showing them is
  a display-only change (`EU_COUNTRY` in `app.js`) whenever a country comparison is
  wanted.
- The without-taxes rows are stored but never exported. If a tax-share view is ever
  wanted, the data is already there — only `export.py` and the dashboard change.
- The 117-check jsdom front-end harness used to verify the reframe lives outside the
  repo (scratchpad only) and is not committed. If front-end regressions become a
  recurring worry, it's worth deciding whether to bring a version of it in as a real
  dev dependency.

## Resolved

- `ajax.php?act=map` tested 2026-07-09: doesn't work (empty body under every param
  combination tried). Coord strategy is the per-station map-page fallback instead.
  Detail in `docs/SCRAPER.md`.
- First live poll run 2026-07-09: succeeded end to end. `fuel.db` has 76 stations
  (coords backfilled for all of them) and 224 price rows spanning all 5 dates in
  the source's visibility window.
- JSON export + GH Actions workflow built 2026-07-10: `export.py` writes
  `site/data/{stations,history,medians}.json` (shapes in `site/data/README.md`,
  14 new unit tests, 52 total passing). `.github/workflows/poll.yml` runs
  poll → export → commit → deploy Pages, sharing the `pages` concurrency group
  with `pages.yml` (GITHUB_TOKEN pushes don't trigger `pages.yml`'s own push
  trigger, so `poll.yml` needs its own deploy job). Neither file is committed
  yet — awaiting manual commit and one `workflow_dispatch` run to verify live
  before trusting the cron. Build order is at step 6 of 8; dashboard v1 is next.
- Dashboard v1 built 2026-07-11: vanilla HTML/CSS/JS in `site/` (no build
  step), Chart.js + Leaflet from CDN, dark theme, CartoDB dark tiles for the
  map. Sticky fuel/radius controls drive a cheapest-first price table
  (colored vs each station's own 7-day average), a Leaflet map (marker color
  = spatial cheapness vs the displayed set's median), a per-station Chart.js
  trend line, and an area median chart. All tunables (`HELSINKI_CENTER`,
  `RADIUS_KM`, `AVG_WINDOW_DAYS`, `STALE_DAYS`, `COLOR_EPSILON`) live as
  constants at the top of `app.js`. Logic verified in Node against live
  `site/data/*.json` (no crashes, sane output) and then confirmed working in
  a real browser by the user. Not yet committed or pushed.
- Manual poll+export refresh 2026-07-11 08:xx UTC (~19.3 h after the
  2026-07-10 12:57 UTC poll, comfortably past the 12 h cadence floor):
  `fuel.db` now has 76 stations and 233 price rows (up from 224), dates
  2026-07-05..2026-07-10 — the source still hasn't produced a 2026-07-11
  report for any station yet, expected given date-only crowdsourced
  resolution. `site/data/*.json` regenerated to match. Still uncommitted.
- `poll.yml` and dashboard v1 committed and pushed; a `workflow_dispatch`
  verification run succeeded, and the cron has since fired every ~12 h
  without a miss from 2026-07-12 through 2026-07-16 — production is stable.
  As of 2026-07-16: `fuel.db` has 89 stations (all geocoded) and 474 price
  rows, dates 2026-07-05 through 2026-07-16 (~11 days of accumulated
  history; the source itself only shows 5 days per poll, but the DB keeps
  everything). Still short of the "weeks of data" bar for v2.
- Repo renamed 2026-07-16: `gas-price-dashboard` → `helsinki-fuel-dash` →
  `fuel-dash`, to drop the city name from the project's identity now that
  international expansion is planned (the Helsinki-area scope itself is
  unchanged — only the name). Live at
  https://nickeniklas.github.io/fuel-dash/. All docs, the tab title, and
  the scraper's `User-Agent` string updated to match; geographic mentions
  ("Helsinki area", `HELSINKI_CENTER`, fixture/test names) were left alone
  since they describe real current scope, not branding. Local git remote
  had drifted through both renames (still pointed at
  `gas-price-dashboard.git`) and was updated by hand — GitHub does not
  update a local clone's remote URL automatically when a repo is renamed.
- Dashboard UX pass 2026-07-19: three additions to dashboard v1, all in
  `site/` (`app.js`, `index.html`, `style.css`), no new dependencies. (1)
  Clicking a price-table row or a "View trend" button added to each Leaflet
  map popup loads that station into the trend chart and smooth-scrolls to
  it, keeping the station `<select>` in sync either direction. (2) Stations
  can be starred as favorites, persisted in the browser's `localStorage`
  (`fuel-dash:favorites`); favorited stations pin to the top of the price
  table under a thin divider (still cheapest-first within the pinned group,
  still colored vs their 7-day average), show an "outside area" hint instead
  of being hidden when the 15 km filter would otherwise exclude them, and
  get one quick-switch chip each above the trend chart. Stale ids (a
  favorited station no longer in `stations.json`) are pruned automatically.
  (3) A live, case-insensitive name search filters the price table; pinned
  favorites always stay visible regardless of the search text. `renderTable`
  / `renderMap` / `renderTrendChart` remain the single render paths.
  Browser-verified locally against live `site/data/*.json`; committed same
  day as commit `a1e5e07`.
- EU Weekly Oil Bulletin ingest + dashboard reframe 2026-09-03, committed as
  `06dcc4e` (code) and `49655ae` (data), not yet pushed. **Why now:** the area
  median series had reached 60 unbroken days (2026-07-05 to 2026-09-02) and was
  solid, but per-station history had not kept pace — 967 dated rows over 124
  stations, median 6 points per station, only 7 stations with 20+. The dashboard
  was presenting per-station trend as its headline feature on data that doesn't
  support it, and no amount of waiting fixes the missing pre-poll history. So:
  add an official long-range series, and reframe the page around what the data
  actually supports.
  (1) **Ingest.** `eu_bulletin.py` mirrors `poll.py`'s shape: fetch, parse,
  upsert, idempotent. One stable DG Energy XLSX URL (no per-bulletin URL, no
  date arithmetic on filenames), the whole 2005-onwards history in one file.
  The workbook was downloaded and inspected before any parser code was written,
  which caught three things an assumed layout would have got wrong: country
  blocks are 7 *or* 8 columns wide (non-euro countries carry an extra
  exchange-rate column, so columns must be found by their row-1 code, never by
  offset); non-euro prices are already converted to EUR (applying SE's exchange
  rate would have put Sweden at ~0.13 EUR/L); and there is no 98E series at all.
  Stores FI/SE/DE/IT × 95/diesel × both tax variants = 17,308 rows over 1082
  weekly dates, 2005-01-03 to 2026-08-31. Self-gated on `GATE_DAYS` (8) so the
  12 h cron downloads once per bulletin rather than ~14 times.
  (2) **Storage split.** `eu_weekly` initially went into `fuel.db` and grew it
  from 192 KB to 1.34 MB — a blob git would rewrite on every 12 h poll commit
  for data that changes weekly. Moved to its own `eu.db` before the first commit
  (once in history it couldn't be removed without a rewrite): `db.connect()` /
  `db.connect_eu()`, `export.py` opens both, and a missing or empty `eu.db` is a
  logged skip rather than a crash. `fuel.db` is back to 192,512 bytes and
  byte-identical to what it was; `eu.db` is 1,150,976 bytes.
  (3) **Sanity bounds.** The shared 0.80–4.00 EUR/L bounds rejected zero
  with-taxes rows but 7227 of 8654 without-taxes rows (84%) — pre-tax petrol
  really was ~0.23–0.45 EUR/L in the 2000s. With-taxes keeps the shared bounds;
  without-taxes got `EU_PRETAX_PRICE_MIN` (0.10). The 4.00 ceiling, which is
  what actually catches a missed per-1000-litre conversion, is unchanged for both.
  (4) **Dashboard reframe.** Order is now Prices → Map → Area median →
  Long-term context → Station trend. The median chart gained an FI national
  weekly overlay (dashed, muted, deliberately subordinate, same y axis since
  both are EUR/L) plus a gap readout in cents per litre using the most recent
  week present in both series; on 98E the overlay is hidden with a one-line note
  instead of falling back to 95. A new context chart carries the 2005-onwards
  depth with a 1/3/5/all year range selector windowed from the newest bulletin
  week, never the browser clock. Per-station trend sits last under a one-sentence
  subheading stating its limits, and the ~39-station "rarely reported" group is
  collapsed behind a `fuel-dash:show-sparse` checkbox — with the row-click and
  map-popup paths reveal-and-select so the picker always shows what the chart is
  showing. A coverage line computed from the loaded JSON reports station count,
  report count and median span. Footer now credits both polttoaine.net and the
  EU bulletin (the latter is a licence condition).
  (5) **Verification.** 92 Python unit tests, up from 52, including a committed
  slice of the real workbook as a fixture (`tests/fixtures/eu_bulletin_slice.xlsx`,
  regenerable via `make_eu_fixture.py`) covering the parse, the conversion, the
  unit guard, both sanity floors, the gate, and export with `eu.db` absent or
  empty. Front-end verified by 117 checks executing the real `index.html` +
  `app.js` under jsdom against the live JSON, run both off the filesystem and
  against `site/` served over `http://` — all passing, including the gap readout
  against a hand calculation and the sparse-station row-click path. That harness
  is scratchpad-only and not committed.
- Table/dropdown UX pass 2026-08-08: two UX problems and a threshold
  decision, all in `site/` (`app.js`, `index.html`, `style.css`), no new
  dependencies. (1) Price-table headers (Station, Price, Reported, vs 7d
  avg) are click-to-sort — click toggles direction, switching columns
  resets to ascending, `aria-sort` plus an arrow indicator show the active
  column, headers are real `<button>`s inside the `<th>` for keyboard
  access. The `vs 7d avg` sort always puts null-average stations last in
  both directions (verified in Node: 79 null stations, all tail-positioned,
  both sort directions). Pinned favorites sort by the same key/direction as
  the main list. (2) The station `<select>` was listing ~66 stations with
  fewer than 3 data points for a given fuel — mostly stations whose only
  history is the initial 5-day batch the poller captured when it first
  found them — next to ~28 stations with real trend data, with no way to
  tell them apart. Added `MIN_TREND_POINTS = 3`, a per-fuel point count
  (`computeStationPointCount`, counts non-null entries for the active fuel,
  not raw history length), "frequently reported" / "rarely reported"
  optgroups with counts in the option labels, repopulation on fuel change
  that preserves the current selection, and a note near the trend chart
  when the selected station is sparse. (3) Measured `STALE_DAYS` (2) live
  before touching it, per fuel: only ~19–20 stations (≈20%) were "fresh",
  ~74–80 (≈80%) dimmed. But of the dimmed stations, most (≈55 of ~74 for
  95E10) were past a new `SOURCE_WINDOW_DAYS = 5` constant entirely — i.e.
  genuinely no longer visible on the source, not just briefly stale. Kept
  `STALE_DAYS` at 2 and instead graded the dimming: fresh / stale (0.5
  opacity, unchanged) / abandoned (past `SOURCE_WINDOW_DAYS`, stronger
  dimming plus a small marker on the date cell). All three verified in Node
  against live `site/data/*.json` (sort ordering, null placement, dropdown
  counts vs. `history.json`, staleness counts); browser-checked by the user and
  committed 2026-09-03 as part of `06dcc4e`.
