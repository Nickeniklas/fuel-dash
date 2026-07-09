# SCRAPER contract — polttoaine.net

Parsing spec written from reading Pumperly (GPL-3.0) plus our own checks, 2026-07-08.
Facts only; all code in this repo is written from scratch. If the site changes,
update this doc first, then the parser.

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
- Starting set: `/Helsinki`, `index.php?t=PK-Seutu`, `/Keha_%20I`, `/Keha_%20III%20(E18)`
  (untested, same `Keha_ I` pattern expected — verify before adding to the poller
  config). Dedupe stations across pages by station ID; the same station appears on
  multiple pages.

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
- Preferred (unverified, test first): `ajax.php` with `act=map` returns all station
  locations without prices in one call.
- Fallback: per-station map page, parse `new google.maps.LatLng(lat, lon)`;
  secondary fallback `lat:'..'` / `lon:'..'` patterns.

## Schema

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

Poller writes `site/data/*.json`: all stations with coords, current prices,
per-station history, area medians. No geographic filtering here; the dashboard
applies the 15 km display radius client-side (config).
