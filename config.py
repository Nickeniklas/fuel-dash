"""Shared configuration for the poller and exporter."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Helsinki center (Rautatientori). Radius covers Helsinki + edges of Espoo/Vantaa.
HELSINKI_LAT = 60.1699
HELSINKI_LON = 24.9384
RADIUS_M = 15000

DB_PATH = BASE_DIR / "tankille.db"
TOKEN_FILE = BASE_DIR / ".tankille_tokens.json"  # gitignored — holds credentials
SITE_DATA_DIR = BASE_DIR / "site" / "data"

BACKFILL_DAYS = 14
