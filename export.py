"""Export the SQLite DB to the static JSON files the dashboard reads.

Output contract (docs/PLAN.md):
  site/data/current.json   latest price per station per fuel + 7-day avg + metadata
  site/data/series.json    (or site/data/stations/<id>.json) full per-station series
  site/data/median.json    daily area median per fuel (95/98/dsl), full history
  site/data/meta.json      last poll time, station count, radius, series mode

Series split decision: rough math says a 14-day backfill (~150 stations x 4 fuels
x a few reports/day) lands well under 1 MB combined, so a single series.json is
expected. Rather than hardcode that, the export measures: past SERIES_SPLIT_BYTES
it flips to per-station files, and the dashboard follows via meta.json's
series_mode either way.
"""

import json
import shutil
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone

from config import DB_PATH, RADIUS_M, SITE_DATA_DIR

DISPLAY_FUELS = ("95", "98", "dsl")  # ingest stores every tag; display filters
SERIES_SPLIT_BYTES = 1_500_000


def write_json(name: str, obj) -> None:
    path = SITE_DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def export_current(conn: sqlite3.Connection) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    stations = {}
    for row in conn.execute("SELECT id, name, chain, brand, street, city, lat, lon FROM stations"):
        stations[row[0]] = {
            "id": row[0], "name": row[1], "chain": row[2], "brand": row[3],
            "street": row[4], "city": row[5], "lat": row[6], "lon": row[7],
            "prices": {},
        }
    rows = conn.execute(
        """SELECT p.station_id, p.fuel, p.price, p.updated, a.avg7d
           FROM prices p
           JOIN (SELECT station_id, fuel, MAX(updated) AS mu FROM prices
                 GROUP BY station_id, fuel) latest
             ON latest.station_id = p.station_id AND latest.fuel = p.fuel
                AND latest.mu = p.updated
           LEFT JOIN (SELECT station_id, fuel, AVG(price) AS avg7d FROM prices
                      WHERE updated >= ? GROUP BY station_id, fuel) a
             ON a.station_id = p.station_id AND a.fuel = p.fuel""",
        (cutoff,),
    )
    for station_id, fuel, price, updated, avg7d in rows:
        if station_id in stations:
            stations[station_id]["prices"][fuel] = {
                "price": price,
                "updated": updated,
                "avg7d": round(avg7d, 4) if avg7d is not None else None,
            }
    write_json("current.json", {"stations": list(stations.values())})
    return len(stations)


def export_series(conn: sqlite3.Connection) -> str:
    """Full price series per station. Returns the series_mode for meta.json."""
    series: dict[str, dict[str, list]] = {}
    for station_id, fuel, price, updated in conn.execute(
        "SELECT station_id, fuel, price, updated FROM prices ORDER BY updated"
    ):
        series.setdefault(station_id, {}).setdefault(fuel, []).append([updated, price])

    combined = json.dumps(series, separators=(",", ":"))
    per_station_dir = SITE_DATA_DIR / "stations"
    if len(combined) <= SERIES_SPLIT_BYTES:
        (SITE_DATA_DIR / "series.json").parent.mkdir(parents=True, exist_ok=True)
        (SITE_DATA_DIR / "series.json").write_text(combined, encoding="utf-8")
        shutil.rmtree(per_station_dir, ignore_errors=True)
        return "combined"
    per_station_dir.mkdir(parents=True, exist_ok=True)
    for station_id, fuels in series.items():
        write_json(f"stations/{station_id}.json", fuels)
    (SITE_DATA_DIR / "series.json").unlink(missing_ok=True)
    return "per_station"


def export_median(conn: sqlite3.Connection) -> None:
    # Last report per station per fuel per day, then median across stations.
    daily: dict[str, dict[str, list[float]]] = {}  # date -> fuel -> prices
    for day, fuel, price in conn.execute(
        """SELECT substr(updated, 1, 10) AS day, fuel, price
           FROM prices p
           WHERE fuel IN (?, ?, ?)
             AND updated = (SELECT MAX(updated) FROM prices
                            WHERE station_id = p.station_id AND fuel = p.fuel
                              AND substr(updated, 1, 10) = substr(p.updated, 1, 10))""",
        DISPLAY_FUELS,
    ):
        daily.setdefault(day, {}).setdefault(fuel, []).append(price)

    dates = sorted(daily)
    out = {"dates": dates}
    for fuel in DISPLAY_FUELS:
        out[fuel] = [
            round(statistics.median(daily[d][fuel]), 4) if daily[d].get(fuel) else None
            for d in dates
        ]
    write_json("median.json", out)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    station_count = export_current(conn)
    series_mode = export_series(conn)
    export_median(conn)
    last_poll = conn.execute("SELECT MAX(fetched_at) FROM prices").fetchone()[0]
    write_json("meta.json", {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "last_poll": last_poll,
        "station_count": station_count,
        "radius_m": RADIUS_M,
        "series_mode": series_mode,
    })
    conn.close()
    print(f"exported {station_count} stations, series_mode={series_mode}")


if __name__ == "__main__":
    main()
