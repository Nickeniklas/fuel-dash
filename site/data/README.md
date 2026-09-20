# site/data — JSON export shapes

Written by export.py from fuel.db (stations, history, medians) and eu.db
(eu_weekly). No geographic filtering: every station in the DB is included,
the dashboard applies the 15 km display radius itself.

`eu_weekly.json` is skipped entirely if `eu.db` is absent or empty; the
dashboard treats a missing file as "no national context" and degrades.

## stations.json

Array of every known station, its coords, and its latest seen price per
fuel (independently -- a fuel's latest price can be from an earlier date
than another fuel's if it wasn't reported on the most recent day). `lat`/
`lon` are `null` until a station's coords have been backfilled. A fuel is
`null` under `latest` if that station has never reported it.

```json
[
  {
    "station_id": 1051,
    "name": "St1, Lauttasaari Heikkilantie 12",
    "lat": 60.156120,
    "lon": 24.883408,
    "latest": {
      "95": {"date": "2026-07-09", "price": 2.099},
      "98": {"date": "2026-07-09", "price": 2.199},
      "dsl": null
    }
  }
]
```

## history.json

Object keyed by station_id (as a string, JSON object keys are always
strings). Each value is that station's full price history, one entry per
date it has any price, sorted oldest to newest. A fuel key is only present
on a date if that fuel was reported that day.

```json
{
  "1051": [
    {"date": "2026-07-08", "95": 2.089, "98": 2.189},
    {"date": "2026-07-09", "95": 2.099, "98": 2.199, "dsl": 2.129}
  ]
}
```

## medians.json

Array of daily area-wide medians per fuel, sorted oldest to newest. One
entry per calendar date from the first observed date to the last, with no
padding outside that range -- dates in the middle that nobody reported on
are present with every fuel `null`, so a polling outage shows as a gap
rather than disappearing. A fuel is `null` on a date if no station
reported it that day, so **consumers must handle null medians.**

```json
[
  {"date": "2026-07-08", "95": 2.089, "98": 2.189, "dsl": null},
  {"date": "2026-07-09", "95": 2.079, "98": 2.199, "dsl": 2.129}
]
```

## eu_weekly.json

Official national weekly prices from the EU Weekly Oil Bulletin (European
Commission, DG Energy), ingested by `eu_bulletin.py` into its own `eu.db`
(kept out of `fuel.db`, which is committed twice a day). Object keyed by
country code, then by fuel, each holding an array sorted oldest to newest.
Prices are EUR/L (the bulletin quotes EUR per 1000 litres; the conversion
happens at ingest).

Only `with_taxes = 1` rows are exported. The bulletin publishes no 98E
series, so the only fuel keys are `95` and `dsl` — the dashboard hides its
national overlay when 98E is selected rather than substituting 95.

A country key is present only if that country has at least one stored row;
`FI` drives the dashboard, the rest are stored and exported ready for a
later display change.

```json
{
  "FI": {
    "95": [{"date": "2026-08-24", "price": 2.177}, {"date": "2026-08-31", "price": 2.203}],
    "dsl": [{"date": "2026-08-24", "price": 2.346}, {"date": "2026-08-31", "price": 2.334}]
  },
  "SE": {"95": [], "dsl": []},
  "DE": {"95": [], "dsl": []},
  "IT": {"95": [], "dsl": []}
}
```
