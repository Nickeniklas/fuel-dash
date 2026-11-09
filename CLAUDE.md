# CLAUDE.md — fuel-dash

Personal fuel price tracker for the Helsinki area. Poller scrapes polttoaine.net
into SQLite on a GH Actions cron, exports JSON, static Chart.js dashboard on
GH Pages reads it. Full plan: `docs/PLAN.md`. Source contracts: `docs/SCRAPER.md`.

**Two data sources:** the polttoaine.net scrape (per-station, Helsinki area,
history starts at our first poll) and the EU Weekly Oil Bulletin (one official
national figure per week per country, back to 2005). They live in separate
SQLite files (`fuel.db`, `eu.db`) and are never joined.

Live at https://nickeniklas.github.io/fuel-dash/ · repo at
https://github.com/Nickeniklas/fuel-dash. The name deliberately doesn't bake in
a city, since the plan is to broaden past Helsinki eventually (current scope is
still the Helsinki area).

## Status

Built and running; currently **letting data accumulate**.

- **Pipeline:** `.github/workflows/poll.yml` (cron `0 */12 * * *` + manual
  dispatch) runs `poll.py` → `eu_bulletin.py` → `export.py`, commits
  `fuel.db`/`eu.db` if changed, and deploys Pages from the same job.
  `pages.yml` redeploys on manual pushes touching `site/**`.
- **Scraper:** `poll.py` polls four pages (Helsinki, PK-Seutu, Kehä I,
  Kehä III); new stations are geocoded from the per-station map page
  (`coords.py`).
- **EU bulletin:** `eu_bulletin.py` upserts FI/SE/DE/IT × 95/diesel × both tax
  variants into `eu.db`, self-gated to download only when the newest stored
  week is more than `GATE_DAYS` (8) old. Only FI with-taxes is shown on the
  dashboard (`EU_COUNTRY` in `app.js`).
- **Dashboard** (`site/`): Prices → Map → Area median → Long-term context →
  Station trend. Price table with click-to-sort headers, name search,
  favorites, graded staleness (fresh / stale / abandoned); Leaflet map; area
  median chart with FI national weekly overlay and cents-per-litre gap readout;
  2005-onwards context chart with 1/3/5/all year range (default 3); station
  picker grouped by report frequency (`MIN_TREND_POINTS = 3`) with the sparse
  group collapsed behind a checkbox; coverage line; polttoaine.net + EU
  bulletin footer credits.
- **Tests:** 99 unit tests, all passing, no network:
  `python -m unittest discover -s tests -t .` (pytest is not installed in `.venv`).
- **Data** (measured from the local checkout's `fuel.db`/`eu.db` at the
  2026-10-16 03:42 UTC poll commit): 133 stations (all geocoded), 4679 price
  rows, dates 2026-07-05 → 2026-10-15; 91 days with data across a 103-day span.
  The 12-day hole 2026-09-04 → 2026-09-15 is a polling outage (GitHub account
  suspended, cron could not run) and is permanent: the source shows only ~5
  days, so **no backfill exists and none ever will** — do not treat the gap as a
  bug. Per-station history is thin: 1631 dated station-days, median 11 points
  per station, 22 stations with 20+. `eu.db`: 17,404 rows, 1088 weekly dates,
  2005-01-03 → 2026-10-12.
- **Next:** v2 (heatmap, fill-now-or-wait signal) waits on per-station report
  volume, not wall-clock time — not there yet.

Session history: docs/STATUS_LOG.md (read when needed)

## Decided stack (do not re-litigate without being asked)

Python + requests + BeautifulSoup-or-similar, SQLite, GH Actions cron (12 h),
GH Pages serving `site/`, Chart.js, vanilla JS. No frameworks, no LLM in the poller.
Python deps (`requirements.txt`): `requests`, `beautifulsoup4`, `openpyxl` (the
last only for the EU bulletin's XLSX workbook). The "no new dependencies" rule
for the dashboard still stands and is scoped to `site/`: Chart.js
(jsdelivr, `chart.js@4.4.1`) and Leaflet (unpkg, `leaflet@1.9.4`) from their
existing pinned CDN URLs, nothing else. Map tiles are Esri World Dark Gray
Canvas base + reference layers (keyless, attribution required); CARTO was
dropped because it began requiring an API key.

The unofficial Tankille API was the original target; it blocked us and was
dropped entirely, clean DB, no workarounds. Do not suggest going back to it.

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
  twice a day for unchanged data. `db.connect(path)` opens/creates the fuel
  schema, `db.connect_eu(path)` the `eu_weekly` schema; callers pass `fuel.db` /
  `eu.db` via their `DB_PATH` / `EU_DB_PATH` constants.
- **The EU bulletin attribution in the dashboard footer is a licence condition**
  (reproduction authorised provided the source is acknowledged). Do not remove it.
- **The bulletin has no 98E series.** When 98E is the selected fuel the dashboard
  hides the national overlay and says so; never substitute the 95 series for it.
- Dedupe key is `(station_id, fuel, date)`, latest price wins within a day.
- GH Pages serves `site/`, never `docs/`.
- No credentials exist anymore (no auth needed); if any secret ever appears, it
  goes in gitignored `.env` / Actions secrets.

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
- After a GitHub repo rename, Pages URLs follow automatically but a local
  clone's remote does not: run `git remote set-url origin` by hand.
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
  them.** `build_medians` emits one entry per calendar date from the first
  observed date to the last, so a date nobody reported on is present with
  `"95"`, `"98"` and `"dsl"` all `null` rather than missing from the array.
  This is deliberate: the dashboard plots medians on a *categorical*
  x-axis, where an absent date is an absent label, so the line closed over the
  2026-09-04 → 2026-09-15 outage and read as an unbroken series. Nothing is
  padded outside the observed range, so the first and last entries always hold
  real data. Consequences for anything reading this file: last-entry lookups
  must scan back to the last non-null entry (`computeReferenceDate` does),
  deltas and reduces must skip nulls, and `medians.length` is now a *calendar
  span*, not a count of days with data. **This applies outside the repo too:**
  the weekly Claude commentary routine (lives outside this repo) will see nulls
  with no other warning. It was documented as reading the exports from
  raw.githubusercontent.com, but the JSON is no longer in git, so current
  copies exist only on Pages (`https://nickeniklas.github.io/fuel-dash/data/*.json`).
- **Per-station report volume is much sparser than the row total or wall-clock
  time suggests, and this is the single most load-bearing fact about the data.**
  Rows spread thinly across stations (see Status for current numbers): most
  rows are each station's initial 5-day batch from the poll that first found
  it; ongoing re-reports on already-known stations are rare.
  Three consequences, all deliberate: the station picker groups by report
  frequency and collapses the sparse group; per-station trend is the last
  section on the page, not the headline; and a station's `history.json` array
  length overstates useful trend data — always count non-null entries for the
  *active fuel*, not raw array length (`computeStationPointCount` in `app.js`).
  The area median is the opposite story and is genuinely deep, which is why
  the dashboard leans on it plus the EU bulletin.
- **EU bulletin workbook layout** (verified live before any parser code was
  written; measure the real file before changing parser assumptions — full
  detail in `docs/SCRAPER.md`):
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
- Dashboard `localStorage` keys: `fuel-dash:favorites` (array of station ids)
  and `fuel-dash:show-sparse` (`'true'`/`'false'`). Favorite ids no longer
  present in `stations.json` are pruned on load, so a stale favorite never
  breaks rendering. The sparse group is collapsed by default, but a price-table
  row click or a map popup's "View trend" on a rarely reported station reveals
  the group and ticks the checkbox — the picker must always show what the trend
  chart is showing.
- The long-term context chart's range window is measured from the **newest
  bulletin week**, not the browser clock — same rule as the reference date
  coming from the newest date in `medians.json`.
- Keep `STALE_DAYS` at 2. Measured live, only a minority of stations are
  "fresh" at that threshold and most are past `SOURCE_WINDOW_DAYS` (5) entirely
  (genuinely gone from the source, not slow). The fix was splitting "stale"
  from "abandoned" into graded dimming, not loosening the fresh/stale line.
  Measure live before touching either threshold.
