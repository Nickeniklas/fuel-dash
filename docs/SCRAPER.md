# SCRAPER contract — polttoaine.net + EU Weekly Oil Bulletin

Parsing spec written from reading Pumperly (GPL-3.0) plus our own checks, 2026-07-08.
Facts only; all code in this repo is written from scratch. If the site changes,
update this doc first, then the parser.

Two sources now: the polttoaine.net scrape (most of this doc) and the EU Weekly
Oil Bulletin workbook (its own section below, added 2026-09-03).

## Pages to crawl (config list)

URL scheme is per page type, verified live 2026-07-09 (an earlier draft of this doc,
derived only from reading Pumperly, assumed `index.php?t=<name>` for everything —
that's wrong for cities and highways, checked in below):

- **City / highway / ring-road pages: path style**, `https://polttoaine.net/<name>`.
  Verified: `/Helsinki`, `/1-tie`, `/Keha_%20I` (space in the name must be URL-encoded
  as `%20` — the site's own option value is literally `Keha_ I`). `?t=<name>` on these
  returns a blank results page (empty center column, ~21 KB), not an error — a silent
  failure mode, don't mistake it for "no stations".
- **Regional "seutu" pages: query style**, `index.php?t=<name>`. Verified: `?t=PK-Seutu`.
  Path style (`/PK-Seutu`) does not work for these.
- Starting set: `/Helsinki`, `index.php?t=PK-Seutu`, `/Keha_%20I`,
  `/Keha_%20III%20(E18)`. All four verified live 2026-07-09 (Kehä III (E18) returns
  25 KB with 7 distinct station IDs — real data, not the blank-page failure mode).
  Dedupe stations across pages by station ID; the same station appears on multiple
  pages.

## Row format

- Price rows are `<tr>` with exactly **5 `<td>`**:
  1. station name + map link
  2. date, `DD.MM.` with **no year**
  3. 95E10
  4. 98E
  5. Diesel
- **5-td count is necessary but not sufficient.** Every page also has two non-price
  rows with 5 tds: the sortable header row (`<tr>` with no class, first td
  `class="Asema"`) and a daily-average "Keskihinnat:" row (`<tr class="bg1">`, first
  td `class="Keskihinnat"`, date cell is a bare `&nbsp;`). Both fail to match the
  `DD.MM.` pattern in td 2 — **require td 2 to match `^\d{2}\.\d{2}\.$` to accept a
  row as a real price row**, that one check clears both cases.
- **Key on the td count + date check, not on class.** Regional pages (`?t=PK-Seutu`
  etc.) omit the `E10` class on `<tr>`, city pages have it — don't rely on it either
  way.
- Station ID comes from the map link: `cmd=map&id=XXXX`. This is the canonical ID.
- ~5–8 % of rows have no map link → **skip** (no ID, can't geocode). Verified 2/23
  (~9 %) on the Helsinki fixture, 3/79 (~4 %) on PK-Seutu — same ballpark.
- 98E cell may carry a `*` V-Power marker: `<span title="Vpower"><span
  class="E99">*</span>2.043</span>` → strip both spans and the `*`, keep the number.
- Empty price cells render as a literal `-`, not empty string → treat both `-` and
  `""` as NULL, never 0.
- Page charset is declared `windows-1252` (`Content-Type` header and meta tag both
  say so) — decode as `cp1252` explicitly, don't trust `requests`' encoding guess
  (it guesses `latin1`, which happens to agree for Finnish `ä`/`ö`/`å` but isn't
  guaranteed to for the full cp1252 range).

## Date resolution

Source gives `DD.MM.` only. Resolve year at parse time:
- Attach the current year; if the resulting date is in the future, subtract one year
  (handles the days around New Year).
- Reports older than 5 days shouldn't appear at all; if one parses to > 7 days old,
  log it, it means the rule or the site changed.

## Sanity checks (drop row + log on failure)

- Price bounds: 0.80–4.00 EUR
- Coordinate bounds (Finland bbox): lat 59.7–70.1, lon 20.5–31.6

## Coordinates

- Static per station → fetch **once**, cache in `stations` table, never refetch.
- `ajax.php?act=map` **tested 2026-07-09, does not work**: returns HTTP 200 with a
  0-byte body for every combination tried (bare `act=map`, `+t=Helsinki`,
  `+kaupunki=Helsinki`, `+ids=`, GET and POST, with/without
  `X-Requested-With: XMLHttpRequest`, with/without a session cookie from first
  loading `/Helsinki`). The homepage's inline/linked JS has no reference to
  `ajax.php` at all — this endpoint doesn't appear to be wired up to anything on
  the pages we crawl. Do not rely on it; use the per-station page.
- **Coordinate source: per-station map page**, `index.php?cmd=map&id=<id>`.
  Confirmed working 2026-07-09 (station 1051 → 25.8 KB page). Parse
  `new google.maps.LatLng(60.156120, 24.883408)` (verified present); secondary
  fallback pattern `lat: '..'` / `lon: '..'` string literals, also present on the
  same page and useful if the LatLng call gets minified/changed later.
- This is N requests (one per new station) instead of one bulk call — same 100 ms
  politeness spacing as page crawling applies here too. Coords are cached forever
  once fetched, so this cost is paid once per station, not once per poll.

## EU Weekly Oil Bulletin (second source)

Official weekly national prices, added 2026-09-03. Not a scrape: one XLSX
workbook, one stable URL, refreshed weekly by the European Commission's
DG Energy. Parsed by `eu_bulletin.py` into its **own database, `eu.db`** --
never `fuel.db`, see the Schema section for why. Layout facts below verified live
2026-09-03 against the real file (4.46 MB) before any parser code was written.

- **URL** (no per-bulletin URL exists, no date arithmetic on filenames):
  `https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx`
- **Licence**: reproduction authorised provided the source is acknowledged.
  The dashboard footer carries the attribution — do not drop it.
- **Sheets**: `Prices with taxes`, `Prices wo taxes` (plus Consumption, VAT,
  Excise duties, Excise duties - components, Other Indirect Taxes, all ignored).
  Both price sheets are in this one workbook with an identical layout, so both
  tax variants are stored from a single download.
- **Orientation**: dates run **down column A, newest first** (2005-01-03 to the
  current week, 1082 rows as of 2026-08-31); country × fuel run across columns.
- **Header rows**: row 1 machine codes (`FI_price_with_tax_euro95`), row 2 human
  fuel names, row 3 units. Data starts at row 4.
- **Country blocks are NOT a fixed width** (7 or 8 columns). Each starts with a
  `CTR` column whose data cells hold `FI_`, `SE_`, … Non-euro countries carry an
  extra `<CC>_exchange_rate` column, which is why columns must be found by their
  row-1 code, never by offset from the `CTR` marker.
- **Non-euro prices are already converted to EUR.** SE's price columns are EUR
  per 1000 l; the exchange-rate column is informational. Do not apply it —
  double-converting would put Sweden at ~0.13 EUR/L.
- **Fuels**: Euro-super 95, automotive gas oil (diesel), heating gas oil, two
  fuel oils, LPG motor fuel. **There is no 98E series** — the dashboard hides
  its national overlay for 98E rather than substituting the 95 series.
- **Units**: `1000 l` for the 95/diesel columns, `t` for the two fuel oils.
  The parser verifies the row-3 unit reads `1000 l` before taking a column, so a
  layout shift onto a per-tonne column is rejected rather than silently stored
  as litres. Prices are divided by 1000 at ingest; the DB holds EUR/L.
- **Trailing rows**: after the data come blank rows and a `Notes:` footer. Row
  acceptance requires a real date in column A — that one check clears the two
  label rows, the blanks and the footer.
- **Sanity bounds**: the with-taxes series uses the shared 0.80–4.00 EUR/L
  bounds and (measured live) has zero violations. The **without-taxes series
  needs a lower floor** — pre-tax petrol was ~0.23–0.45 EUR/L through the
  2000s, and the retail floor rejected 7227 of 8654 real rows. See
  `EU_PRETAX_PRICE_MIN` in `db.py`. The shared 4.00 ceiling is what catches a
  missed per-1000-litre conversion, in both variants.
- **Self-gate**: `eu_bulletin.py` queries `eu.db`'s newest stored `week_date`
  first and exits 0 without downloading if it is within `GATE_DAYS` (8) of today.
  The file is multi-megabyte and the source updates weekly, so the 12 h cron
  would otherwise refetch it ~14 times per new bulletin. Politeness applies
  here too: same honest User-Agent as the scraper.
- **Countries stored**: FI, SE, DE, IT. Only FI is displayed; the others are
  stored so adding one later is a display change, not a re-ingest.
- **Fixture**: `tests/fixtures/eu_bulletin_slice.xlsx` is a committed slice of
  the real workbook (regenerate with `tests/fixtures/make_eu_fixture.py`); the
  full file is far too big to commit.

## Schema

Two SQLite files, deliberately separate. `fuel.db` holds the scraper's tables
and is committed on every 12 h poll; `eu.db` holds the bulletin series and only
changes weekly. Putting `eu_weekly` in `fuel.db` grew it from ~192 KB to
~1.34 MB (measured 2026-09-03), which git would then rewrite twice a day for
data that hadn't changed. `db.connect()` opens the first, `db.connect_eu()` the
second; nothing joins across them.

### fuel.db

```sql
CREATE TABLE stations (
  station_id INTEGER PRIMARY KEY,   -- polttoaine.net id from cmd=map&id=
  name       TEXT NOT NULL,
  lat        REAL,
  lon        REAL,
  first_seen TEXT NOT NULL          -- ISO date
);

CREATE TABLE prices (
  station_id INTEGER NOT NULL REFERENCES stations(station_id),
  fuel       TEXT NOT NULL,         -- '95' | '98' | 'dsl'
  date       TEXT NOT NULL,         -- ISO date, resolved from DD.MM.
  price      REAL NOT NULL,
  UNIQUE(station_id, fuel, date)    -- ON CONFLICT: overwrite price (latest wins)
);
```

### eu.db

```sql
CREATE TABLE eu_weekly (            -- EU Weekly Oil Bulletin, see above
  country    TEXT NOT NULL,         -- 'FI' | 'SE' | 'DE' | 'IT'
  fuel       TEXT NOT NULL,         -- '95' | 'dsl' (no 98E in this source)
  week_date  TEXT NOT NULL,         -- ISO date of the bulletin week
  price      REAL NOT NULL,         -- EUR/L, converted from EUR/1000 l
  with_taxes INTEGER NOT NULL DEFAULT 1,
  UNIQUE(country, fuel, week_date, with_taxes)
);
```

Date-only resolution is a source limitation: no timestamps exist, so one row per
station/fuel/day, same-day changes overwrite to the latest seen value.

## Politeness rules (hard)

- Poll every 12 h, never faster (Pumperly's cadence; 5-day price visibility makes
  more frequent polling pointless anyway)
- 100 ms sleep between page requests
- Honest User-Agent naming the project and a contact/repo URL
- Respect robots.txt: checked manually before first crawl AND the poller re-checks
  and aborts if crawling becomes disallowed

## Export

`export.py` (run after `poll.py` and `eu_bulletin.py`, all invoked by
`.github/workflows/poll.yml`) reads `fuel.db` for the first three files and
`eu.db` for the fourth, and writes `site/data/stations.json` (all stations, coords,
latest price per fuel), `site/data/history.json` (per-station price history),
`site/data/medians.json` (daily area median per fuel), and
`site/data/eu_weekly.json` (official national weekly prices per country and
fuel, with-taxes rows only). Exact shapes are documented in
`site/data/README.md`, written by the same script. No
geographic filtering here; the dashboard applies the 15 km display radius
client-side (config).
