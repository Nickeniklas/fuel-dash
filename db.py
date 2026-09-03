"""SQLite storage layer. Schema and dedupe rule: docs/SCRAPER.md.

Owns the only writes to both databases:

- **fuel.db** (`connect`): station upsert, coordinate backfill, and price
  upsert with same-day-overwrite dedupe on (station_id, fuel, date).
- **eu.db** (`connect_eu`): the EU Weekly Oil Bulletin series (eu_bulletin.py).

They are deliberately separate files. fuel.db is committed on every 12 h poll,
while the bulletin only changes weekly and is ~1.1 MB of it -- keeping the two
apart stops git from rewriting that blob twice a day for no new data.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from parser import PRICE_MAX, PRICE_MIN

logger = logging.getLogger(__name__)

LAT_MIN, LAT_MAX = 59.7, 70.1
LON_MIN, LON_MAX = 20.5, 31.6

# The scraper's PRICE_MIN (0.80) is a retail-pump-price floor: it assumes tax
# is included. The EU bulletin's without-taxes series is structurally lower --
# pre-tax petrol was ~0.23-0.45 EUR/L through the 2000s -- and measured live
# 2026-09-03, that floor rejected 7227 of 8654 real without-taxes rows (84%)
# while rejecting zero with-taxes rows. So with-taxes keeps the shared bounds
# unchanged, and without-taxes gets its own floor. The 4.00 ceiling is shared
# and is what actually catches a missed per-1000-litre conversion (which would
# land in the hundreds or thousands, not just above the floor).
EU_PRETAX_PRICE_MIN = 0.10

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
  station_id INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  lat        REAL,
  lon        REAL,
  first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
  station_id INTEGER NOT NULL REFERENCES stations(station_id),
  fuel       TEXT NOT NULL,
  date       TEXT NOT NULL,
  price      REAL NOT NULL,
  UNIQUE(station_id, fuel, date)
);
"""

# Lives in eu.db, not fuel.db -- see the module docstring for why.
EU_SCHEMA = """
CREATE TABLE IF NOT EXISTS eu_weekly (
  country    TEXT NOT NULL,
  fuel       TEXT NOT NULL,
  week_date  TEXT NOT NULL,
  price      REAL NOT NULL,
  with_taxes INTEGER NOT NULL DEFAULT 1,
  UNIQUE(country, fuel, week_date, with_taxes)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the fuel DB and ensure the schema exists."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def connect_eu(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the EU bulletin DB and ensure its schema exists.

    Deliberately a separate function over a separate file rather than a
    parameter on connect(): the two databases have different write cadences and
    nothing joins across them, so a caller should have to say which one it
    means. Note this *creates* the file if absent -- callers that must not do
    that (export.py) check for the file first.
    """
    conn = sqlite3.connect(db_path)
    conn.executescript(EU_SCHEMA)
    conn.commit()
    return conn


def upsert_station(conn: sqlite3.Connection, station_id: int, name: str, seen_on: date) -> None:
    """Register a station on first sight. Existing rows are left untouched —
    name/coords are handled by set_station_coords(), not overwritten here."""
    conn.execute(
        "INSERT OR IGNORE INTO stations (station_id, name, lat, lon, first_seen) "
        "VALUES (?, ?, NULL, NULL, ?)",
        (station_id, name, seen_on.isoformat()),
    )


def stations_missing_coords(conn: sqlite3.Connection) -> list[int]:
    """Station IDs that still need a coordinate fetch."""
    rows = conn.execute(
        "SELECT station_id FROM stations WHERE lat IS NULL OR lon IS NULL"
    ).fetchall()
    return [row[0] for row in rows]


def set_station_coords(conn: sqlite3.Connection, station_id: int, lat: float, lon: float) -> bool:
    """Cache coords for a station. Returns False (and logs) if out of the
    Finland bbox sanity bounds, per SCRAPER.md — coords are never refetched,
    so a bad value here would stick permanently if we didn't reject it."""
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        logger.warning(
            "station %s: coords (%.5f, %.5f) outside Finland bbox "
            "[%.1f, %.1f] x [%.1f, %.1f] — skipping",
            station_id, lat, lon, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX,
        )
        return False
    conn.execute(
        "UPDATE stations SET lat = ?, lon = ? WHERE station_id = ?",
        (lat, lon, station_id),
    )
    return True


def upsert_price(conn: sqlite3.Connection, station_id: int, fuel: str, price_date: str, price: float) -> bool:
    """Insert a price, overwriting same-day (station_id, fuel, date) — latest
    seen wins, per the dedupe rule. Returns False (and logs) if the price is
    outside sanity bounds; the row is skipped, not just the fuel field."""
    if not (PRICE_MIN <= price <= PRICE_MAX):
        logger.warning(
            "station %s %s %s: price %.3f outside sanity bounds [%.2f, %.2f] — skipping",
            station_id, fuel, price_date, price, PRICE_MIN, PRICE_MAX,
        )
        return False
    conn.execute(
        "INSERT INTO prices (station_id, fuel, date, price) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(station_id, fuel, date) DO UPDATE SET price = excluded.price",
        (station_id, fuel, price_date, price),
    )
    return True


def ingest_rows(conn: sqlite3.Connection, rows: list[dict], seen_on: date) -> None:
    """Upsert a batch of parser.parse_page() rows: register any new stations,
    then upsert each present fuel price. Safe to call twice with the same
    rows (idempotent) — same-day prices just overwrite themselves."""
    for row in rows:
        upsert_station(conn, row["station_id"], row["station_name"], seen_on)
        for fuel, price in row["prices"].items():
            if price is not None:
                upsert_price(conn, row["station_id"], fuel, row["date"], price)
    conn.commit()


def upsert_eu_weekly(
    conn: sqlite3.Connection,
    country: str,
    fuel: str,
    week_date: str,
    price: float,
    with_taxes: int = 1,
) -> bool:
    """Insert one EU Weekly Oil Bulletin observation, overwriting the same
    (country, fuel, week_date, with_taxes) — the bulletin restates history on
    every publish, so re-parsing the file must be idempotent.

    `price` is EUR/L (the bulletin's per-1000-litre figure is converted before
    it gets here). Returns False (and logs) if it falls outside the sanity
    bounds for its tax variant; the row is skipped, not stored. With-taxes
    rows use the scraper's shared bounds; without-taxes rows use a lower
    floor, per EU_PRETAX_PRICE_MIN above.
    """
    floor = PRICE_MIN if with_taxes else EU_PRETAX_PRICE_MIN
    if not (floor <= price <= PRICE_MAX):
        logger.warning(
            "eu_weekly %s %s %s (with_taxes=%d): price %.3f outside sanity bounds "
            "[%.2f, %.2f] — skipping",
            country, fuel, week_date, with_taxes, price, floor, PRICE_MAX,
        )
        return False
    conn.execute(
        "INSERT INTO eu_weekly (country, fuel, week_date, price, with_taxes) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(country, fuel, week_date, with_taxes) "
        "DO UPDATE SET price = excluded.price",
        (country, fuel, week_date, price, with_taxes),
    )
    return True


def latest_eu_week(conn: sqlite3.Connection) -> str | None:
    """Newest week_date in eu.db's eu_weekly, or None if the table is empty.
    Drives eu_bulletin.py's self-gate — the bulletin file is multi-megabyte
    and only refreshed weekly, so the 12 h cron must not refetch it blindly."""
    row = conn.execute("SELECT MAX(week_date) FROM eu_weekly").fetchone()
    return row[0] if row and row[0] else None


def ingest_eu_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Upsert a batch of eu_bulletin.parse_workbook() rows. Returns the number
    of rows actually stored (out-of-bounds rows are rejected and logged)."""
    stored = 0
    for row in rows:
        if upsert_eu_weekly(
            conn,
            row["country"],
            row["fuel"],
            row["week_date"],
            row["price"],
            row["with_taxes"],
        ):
            stored += 1
    conn.commit()
    return stored
