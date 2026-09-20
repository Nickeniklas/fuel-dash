"""JSON export: fuel.db + eu.db -> site/data/*.json for the static dashboard.

File shapes are documented in site/data/README.md (written by this module).
No geographic filtering here -- the dashboard applies the 15 km display
radius client-side, per docs/PLAN.md.
"""

from __future__ import annotations

import json
import logging
from datetime import date as _date, timedelta
from pathlib import Path
from statistics import median

from db import connect, connect_eu

logger = logging.getLogger(__name__)

FUELS = ("95", "98", "dsl")

# The EU Weekly Oil Bulletin has no 98E series, so its export covers 95/dsl
# only; the dashboard hides the overlay when 98 is selected.
EU_FUELS = ("95", "dsl")
EU_COUNTRIES = ("FI", "SE", "DE", "IT")

DB_PATH = Path(__file__).resolve().parent / "fuel.db"
# The bulletin series lives in its own database -- see db.py's module docstring.
EU_DB_PATH = Path(__file__).resolve().parent / "eu.db"
OUT_DIR = Path(__file__).resolve().parent / "site" / "data"

DATA_README = """# site/data — JSON export shapes

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
"""


def build_stations(conn) -> list[dict]:
    """All stations with coords and each fuel's latest seen price, independently."""
    price_rows = conn.execute(
        "SELECT station_id, fuel, date, price FROM prices ORDER BY date"
    ).fetchall()
    latest: dict[int, dict[str, dict]] = {}
    for station_id, fuel, price_date, price in price_rows:
        # ORDER BY date ascending -> the last write per (station, fuel) is the latest;
        # UNIQUE(station_id, fuel, date) means no same-date tie is possible.
        latest.setdefault(station_id, {})[fuel] = {"date": price_date, "price": price}

    station_rows = conn.execute(
        "SELECT station_id, name, lat, lon FROM stations ORDER BY station_id"
    ).fetchall()
    return [
        {
            "station_id": station_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "latest": {fuel: latest.get(station_id, {}).get(fuel) for fuel in FUELS},
        }
        for station_id, name, lat, lon in station_rows
    ]


def build_history(conn) -> dict[str, list[dict]]:
    """Per-station price history, one entry per date, oldest to newest."""
    rows = conn.execute(
        "SELECT station_id, fuel, date, price FROM prices ORDER BY station_id, date"
    ).fetchall()
    by_station: dict[int, dict[str, dict]] = {}
    for station_id, fuel, price_date, price in rows:
        day = by_station.setdefault(station_id, {}).setdefault(price_date, {"date": price_date})
        day[fuel] = price
    return {
        str(station_id): sorted(days.values(), key=lambda d: d["date"])
        for station_id, days in by_station.items()
    }


def _date_range(first: str, last: str) -> list[str]:
    """Every ISO date from first to last inclusive."""
    start, end = _date.fromisoformat(first), _date.fromisoformat(last)
    return [(start + timedelta(days=n)).isoformat() for n in range((end - start).days + 1)]


def build_medians(conn) -> list[dict]:
    """Daily area-wide median price per fuel, oldest to newest.

    Emits one entry per calendar date between the first and last observed
    date, not one per date that happens to have data. A date nobody reported
    on gets an entry with every fuel null, so a polling outage reads as a
    break in the series instead of silently vanishing: the dashboard plots
    these on a categorical axis, where a missing date is a missing label and
    the line would close over the hole as if the days never existed.

    Nothing is padded outside the observed range -- the first and last
    entries are always real data. Null is the same "nobody reported this"
    marker the per-fuel nulls already use; 0 would be a plottable price that
    drags medians, minima and averages toward zero.
    """
    rows = conn.execute("SELECT date, fuel, price FROM prices ORDER BY date").fetchall()
    by_date: dict[str, dict[str, list[float]]] = {}
    for price_date, fuel, price in rows:
        by_date.setdefault(price_date, {}).setdefault(fuel, []).append(price)
    if not by_date:
        return []
    observed = sorted(by_date)
    return [
        {
            "date": price_date,
            **{
                fuel: round(median(by_date[price_date][fuel]), 3)
                if fuel in by_date.get(price_date, {})
                else None
                for fuel in FUELS
            },
        }
        for price_date in _date_range(observed[0], observed[-1])
    ]


def build_eu_weekly(conn) -> dict[str, dict[str, list[dict]]]:
    """Official weekly national prices per country and fuel, oldest to newest.

    Reads an eu.db connection, not fuel.db. With-taxes rows only -- the
    without-taxes variant is stored but not exported; nothing in the dashboard
    reads it yet.
    """
    rows = conn.execute(
        "SELECT country, fuel, week_date, price FROM eu_weekly "
        "WHERE with_taxes = 1 ORDER BY country, fuel, week_date"
    ).fetchall()
    by_country: dict[str, dict[str, list[dict]]] = {}
    for country, fuel, week_date, price in rows:
        if country not in EU_COUNTRIES or fuel not in EU_FUELS:
            continue
        series = by_country.setdefault(country, {fuel: [] for fuel in EU_FUELS})
        series[fuel].append({"date": week_date, "price": round(price, 4)})
    return by_country


def _write_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _export_eu_weekly(out_dir: Path, eu_db_path: Path) -> bool:
    """Write eu_weekly.json from eu.db, or skip it and log why.

    A missing or empty eu.db is not an error: it just means the bulletin has
    never been ingested in this checkout. The scraper's three files must still
    export, so this never raises. Note it deliberately does not call
    connect_eu() before checking the path -- that would create an empty eu.db
    as a side effect of exporting.
    """
    if not eu_db_path.exists():
        logger.info("no EU database at %s — skipping eu_weekly.json", eu_db_path)
        return False

    conn = connect_eu(eu_db_path)
    try:
        data = build_eu_weekly(conn)
    finally:
        conn.close()

    if not data:
        logger.info("EU database %s holds no exportable rows — skipping eu_weekly.json", eu_db_path)
        return False

    _write_json(out_dir / "eu_weekly.json", data)
    return True


def export(
    db_path: Path = DB_PATH,
    out_dir: Path = OUT_DIR,
    eu_db_path: Path = EU_DB_PATH,
) -> None:
    """Write stations.json, history.json and medians.json from fuel.db, plus
    eu_weekly.json from eu.db when that database is present and non-empty."""
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        _write_json(out_dir / "stations.json", build_stations(conn))
        _write_json(out_dir / "history.json", build_history(conn))
        _write_json(out_dir / "medians.json", build_medians(conn))
    finally:
        conn.close()

    _export_eu_weekly(out_dir, Path(eu_db_path))
    (out_dir / "README.md").write_text(DATA_README, encoding="utf-8")
    logger.info("exported JSON to %s", out_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export()
