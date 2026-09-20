# CLAUDE.md — fuel-dash

Personal fuel price tracker for the Helsinki area. Poller scrapes polttoaine.net
into SQLite on a GH Actions cron, exports JSON, static Chart.js dashboard on
GH Pages reads it. Full plan: `docs/PLAN.md`. Source contracts: `docs/SCRAPER.md`.

**Two data sources** since 2026-09-03: the polttoaine.net scrape (per-station,
Helsinki area, history starts at our first poll) and the EU Weekly Oil Bulletin
(one official national figure per week per country, back to 2005). They live in
separate SQLite files and are never joined.

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
`openpyxl` was added 2026-09-03 for the EU bulletin's XLSX workbook — the only
dependency added since the original three. The "no new dependencies" rule for
the dashboard still stands and is scoped to `site/`: Chart.js and Leaflet from
their existing pinned CDN URLs, nothing else.

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
- **`eu_weekly` lives in `eu.db`, never in `fuel.db`.** `fuel.db` is committed on
  every 12 h poll; the bulletin is ~1.15 MB and only changes weekly. Merging them
  grew `fuel.db` from 192 KB to 1.34 MB and would have had git rewrite that blob
  twice a day for unchanged data. `db.connect()` opens `fuel.db`,
  `db.connect_eu()` opens `eu.db`.
- **The EU bulletin attribution in the dashboard footer is a licence condition**
  (reproduction authorised provided the source is acknowledged). Do not remove it.
- **The bulletin has no 98E series.** When 98E is the selected fuel the dashboard
  hides the national overlay and says so; never substitute the 95 series for it.
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
2026-07-12; the workflow now runs `poll.py` → `eu_bulletin.py` → `export.py`, then
commits `fuel.db`/`eu.db` and deploys Pages from the same job) →
**dashboard v1** (done, committed, live at
https://nickeniklas.github.io/fuel-dash/) → **dashboard UX pass** (done and
committed 2026-07-19, commit `a1e5e07`: clickable price-table rows and map
popup buttons load a station into the trend chart and scroll to it, keeping
the station `<select>` in sync; starred favorites persist in `localStorage`
and pin to the top of the price table with quick-switch chips above the trend
chart; a live name search filters the price table) → **table/dropdown UX
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
**currently: letting data accumulate.**
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
  — `poll.yml`'s commit of `fuel.db`/`eu.db` won't fire `pages.yml`. `poll.yml`
  deploys for itself, sharing the `pages` concurrency group with `pages.yml` so
  they never race.
- **`site/data/*.json` is gitignored and generated at deploy time.** The four
  export files are pure derivatives of `fuel.db` + `eu.db`; committing them on
  every 12 h poll grew the repo forever (`history.json` worst) for data the
  Pages artifact already carries. Two consequences: `poll.yml` runs the export
  *and* the Pages upload in **one job** — a separate deploy job checking out
  `main` would find no JSON — and `pages.yml` has to run `setup-python` +
  `pip install` + `export.py` before its upload for the same reason. The commit
  step adds only `fuel.db eu.db`. `site/data/README.md` stays tracked (it is
  documentation, though `export.py` rewrites it on each run).
- **`medians.json` can contain null medians, and any consumer must handle
  them.** Since 2026-09-20 `build_medians` emits one entry per calendar date
  from the first observed date to the last, so a date nobody reported on is
  present with `"95"`, `"98"` and `"dsl"` all `null` rather than missing from
  the array. This is deliberate: the dashboard plots medians on a *categorical*
  x-axis, where an absent date is an absent label, so the line closed over the
  2026-09-04 → 2026-09-15 outage and read as an unbroken series. Nothing is
  padded outside the observed range, so the first and last entries always hold
  real data. Consequences for anything reading this file: last-entry lookups
  must scan back to the last non-null entry (`computeReferenceDate` does),
  deltas and reduces must skip nulls, and `medians.length` is now a *calendar
  span*, not a count of days with data. **This applies outside the repo too:**
  the weekly Claude commentary routine reads these exports straight from
  raw.githubusercontent.com and will see nulls with no other warning.
- Favorites are stored client-side under the `localStorage` key
  `fuel-dash:favorites` (array of station ids). Ids no longer present in
  `stations.json` are pruned automatically on load, so a stale favorite never
  breaks rendering.
- **Per-station report volume is much sparser than the row total or wall-clock
  time suggests, and this is the single most load-bearing fact about the data.**
  Measured live 2026-09-03: 2775 price rows sounds healthy, but they spread
  across 124 stations as 967 dated station-days — **median 6 points per
  station, only 7 stations with 20+**. Most rows are still each station's
  initial 5-day batch from the poll that first found it; ongoing re-reports on
  already-known stations are rare. (Earlier readings of the same pattern:
  89 → 120 stations against 474 → 476 rows between 2026-07-16 and 2026-08-08.)
  Three consequences, all deliberate: the station picker groups by report
  frequency and collapses the sparse group; per-station trend is the last
  section on the page, not the headline; and a station's `history.json` array
  length overstates useful trend data — always count non-null entries for the
  *active fuel*, not raw array length (`computeStationPointCount` in `app.js`).
  The area median is the opposite story and is genuinely deep (65 days over a
  77-day span), which is why the reframe leans on it plus the EU bulletin.
- **EU bulletin workbook layout** (all verified live 2026-09-03 before any
  parser code was written — full detail in `docs/SCRAPER.md`):
  - Country blocks are **7 or 8 columns wide, not fixed**: non-euro countries
    carry an extra `<CC>_exchange_rate` column. Find columns by their row-1
    code (`FI_price_with_tax_euro95`), never by offset from the `CTR` marker.
  - **Non-euro prices are already in EUR.** SE's exchange-rate column is
    informational; applying it would put Sweden at ~0.13 EUR/L.
  - Dates run **down column A, newest first**; header rows are 1 (codes),
    2 (names), 3 (units); data starts at row 4 and ends in blank rows plus a
    `Notes:` footer. Accept a row only if column A holds a real date — that one
    check clears the label rows, the blanks and the footer.
  - Units are `1000 l` for 95/diesel and `t` for the fuel oils. The parser
    verifies the row-3 unit before taking a column, so a layout shift onto a
    per-tonne column is rejected rather than silently stored as litres.
  - Both tax variants are in the same workbook with identical layout, so both
    are stored from one download. Only `with_taxes = 1` is exported.
- **The scraper's 0.80 EUR/L price floor does not apply to the bulletin's
  without-taxes series.** Pre-tax petrol was ~0.23–0.45 EUR/L through the 2000s;
  measured live, the retail floor rejected 7227 of 8654 real without-taxes rows
  (84%) while rejecting zero with-taxes rows. Hence `EU_PRETAX_PRICE_MIN` (0.10)
  in `db.py`. The shared 4.00 ceiling is what actually catches a missed
  per-1000-litre conversion, and applies to both variants.
- `export.py` must survive a missing or empty `eu.db`: it checks the path
  *before* calling `connect_eu()` (which would otherwise create an empty file as
  a side effect of exporting), writes the other three JSON files, and logs a skip
  line. The dashboard likewise treats a failed `eu_weekly.json` fetch as "no
  national context" and degrades to its previous behaviour.
- Dashboard `localStorage` keys are now two: `fuel-dash:favorites` (array of
  station ids) and `fuel-dash:show-sparse` (`'true'`/`'false'`). The sparse group
  is collapsed by default, but a price-table row click or a map popup's "View
  trend" on a rarely reported station reveals the group and ticks the checkbox —
  the picker must always show what the trend chart is showing.
- The long-term context chart's range window is measured from the **newest
  bulletin week**, not the browser clock — same rule as the reference date
  coming from the newest date in `medians.json`.
- `STALE_DAYS` (2) was measured live 2026-08-08 before touching it: only
  ~20% of stations are "fresh" at that threshold. But ~59% of all stations
  are past `SOURCE_WINDOW_DAYS` (5) entirely — genuinely no longer visible
  on the source, not just slow to update. Kept `STALE_DAYS` at 2; the real
  fix was splitting "stale" from "abandoned" into graded dimming, not
  loosening the fresh/stale line.
