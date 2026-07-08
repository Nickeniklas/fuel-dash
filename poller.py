"""Poll the Tankille API for Helsinki-area stations and record prices in SQLite.

One location request per run. On an empty prices table, backfills 14 days of
per-station history first (roughly one request per station, once ever).
"""

import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from config import BACKFILL_DAYS, DB_PATH, HELSINKI_LAT, HELSINKI_LON, RADIUS_M, TOKEN_FILE
from tankille_client import TankilleClient, TankilleError

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
  id      TEXT PRIMARY KEY,   -- Tankille _id
  name    TEXT NOT NULL,
  chain   TEXT,
  brand   TEXT,
  street  TEXT,
  city    TEXT,
  lat     REAL,
  lon     REAL
);

CREATE TABLE IF NOT EXISTS prices (
  station_id TEXT NOT NULL REFERENCES stations(id),
  fuel       TEXT NOT NULL,     -- API tag: 95, 98, dsl, hvo, ngas, ...
  price      REAL NOT NULL,
  updated    TEXT NOT NULL,     -- report timestamp from API
  fetched_at TEXT NOT NULL,     -- when the poller saw it
  UNIQUE (station_id, fuel, updated)
);
-- No reporter column. Deliberate. Do not add it.
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def upsert_stations(conn: sqlite3.Connection, stations: list[dict]) -> None:
    for s in stations:
        addr = s.get("address") or {}
        coords = (s.get("location") or {}).get("coordinates") or [None, None]
        conn.execute(
            """INSERT INTO stations (id, name, chain, brand, street, city, lat, lon)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, chain=excluded.chain, brand=excluded.brand,
                 street=excluded.street, city=excluded.city,
                 lat=excluded.lat, lon=excluded.lon""",
            (s["_id"], s.get("name", "?"), s.get("chain"), s.get("brand"),
             addr.get("street"), addr.get("city"), coords[1], coords[0]),
        )


def insert_price(conn: sqlite3.Connection, station_id: str, entry: dict, fetched_at: str) -> int:
    """Insert one API price entry, dropping everything but tag/price/updated.

    The reporter field is deliberately never read. Returns rows inserted (0 or 1).
    """
    fuel, price, updated = entry.get("tag"), entry.get("price"), entry.get("updated")
    if not fuel or price is None or not updated:
        return 0
    cur = conn.execute(
        "INSERT OR IGNORE INTO prices (station_id, fuel, price, updated, fetched_at) VALUES (?, ?, ?, ?, ?)",
        (station_id, fuel, price, updated, fetched_at),
    )
    return cur.rowcount


def backfill(conn: sqlite3.Connection, client: TankilleClient, stations: list[dict]) -> int:
    """Seed BACKFILL_DAYS of per-station history. One-time, ~1 request per station."""
    since = datetime.now(timezone.utc) - timedelta(days=BACKFILL_DAYS)
    fetched_at = utcnow_iso()
    inserted = 0
    for i, s in enumerate(stations, 1):
        try:
            entries = client.get_station_prices(s["_id"], since)
        except TankilleError as e:
            # A station missing from the backfill is tolerable; a retry storm is not.
            print(f"  backfill {s['_id']} failed, skipping: {e}", file=sys.stderr)
            continue
        for entry in entries:
            inserted += insert_price(conn, s["_id"], entry, fetched_at)
        print(f"  [{i}/{len(stations)}] {s.get('name', s['_id'])}: {len(entries)} entries")
        time.sleep(0.5)  # be gentle — this is the only bursty path
    return inserted


def main() -> None:
    load_dotenv()
    email = os.environ.get("TANKILLE_EMAIL")
    password = os.environ.get("TANKILLE_PASSWORD")
    if not email or not password:
        sys.exit("TANKILLE_EMAIL and TANKILLE_PASSWORD must be set (.env or environment)")

    client = TankilleClient(email, password, TOKEN_FILE)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    stations = client.get_stations_by_location(HELSINKI_LAT, HELSINKI_LON, RADIUS_M)
    print(f"fetched {len(stations)} stations within {RADIUS_M} m")
    upsert_stations(conn, stations)

    if conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0:
        print(f"empty prices table — backfilling {BACKFILL_DAYS} days of history")
        n = backfill(conn, client, stations)
        print(f"backfill inserted {n} price rows")

    fetched_at = utcnow_iso()
    inserted = 0
    for s in stations:
        for entry in s.get("price") or []:
            inserted += insert_price(conn, s["_id"], entry, fetched_at)
    conn.commit()
    conn.close()
    print(f"poll inserted {inserted} new price rows")


if __name__ == "__main__":
    try:
        main()
    except TankilleError as e:
        sys.exit(f"poll failed: {e}")
