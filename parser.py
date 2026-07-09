"""Parser for polttoaine.net price-listing pages. Contract: docs/SCRAPER.md.

Written from docs/SCRAPER.md only — no code read from or copied out of Pumperly
(GPL-3.0), which is spec reference only.
"""

from __future__ import annotations

import logging
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "helsinki-fuel-dash/0.1 (personal project; contact: savonheimoniklas@gmail.com)"

DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.$")
MAP_ID_RE = re.compile(r"id=(\d+)")

PRICE_MIN = 0.80
PRICE_MAX = 4.00


def fetch_page(url: str) -> str:
    """GET a polttoaine.net page with the project's honest UA, decoded as cp1252."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    response.encoding = "cp1252"
    return response.text


def resolve_date(dm_text: str, reference: date) -> date | None:
    """Resolve a DD.MM. string to an ISO date, applying the year-rollover rule.

    Attaches `reference`'s year; if the result would be in the future, that
    means the date is really from the previous year (New Year rollover).
    """
    match = DATE_RE.match(dm_text)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    try:
        resolved = date(reference.year, month, day)
    except ValueError:
        return None
    if resolved > reference:
        resolved = date(reference.year - 1, month, day)
    age_days = (reference - resolved).days
    if age_days > 7:
        logger.warning(
            "resolved date %s is %d days before reference %s (> 7) — "
            "rollover rule or site format may have changed",
            resolved.isoformat(), age_days, reference.isoformat(),
        )
    return resolved


def _parse_price(cell) -> float | None:
    text = cell.get_text(strip=True).lstrip("*").strip()
    if text in ("", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        logger.warning("unparseable price cell %r", text)
        return None


def _parse_row(tr, reference: date) -> dict | None:
    tds = tr.find_all("td", recursive=False)
    if len(tds) != 5:
        return None

    resolved_date = resolve_date(tds[1].get_text(strip=True), reference)
    if resolved_date is None:
        return None  # header row or the "Keskihinnat:" daily-average row

    name_cell = tds[0]
    map_link = name_cell.find("a", href=MAP_ID_RE)
    if map_link is None:
        return None  # no station ID, can't geocode — skip per SCRAPER.md
    station_id = int(MAP_ID_RE.search(map_link["href"]).group(1))
    map_link.extract()
    station_name = " ".join(name_cell.get_text(strip=True).split())

    prices = {
        "95": _parse_price(tds[2]),
        "98": _parse_price(tds[3]),
        "dsl": _parse_price(tds[4]),
    }

    for fuel, price in prices.items():
        if price is not None and not (PRICE_MIN <= price <= PRICE_MAX):
            logger.warning(
                "station %s date %s: %s price %.3f outside sanity bounds "
                "[%.2f, %.2f] — dropping row",
                station_id, resolved_date.isoformat(), fuel, price, PRICE_MIN, PRICE_MAX,
            )
            return None

    return {
        "station_id": station_id,
        "station_name": station_name,
        "date": resolved_date.isoformat(),
        "prices": prices,
    }


def parse_page(html: str, reference: date | None = None) -> list[dict]:
    """Parse a polttoaine.net listing page into a list of price-row dicts.

    Each dict: {station_id, station_name, date (ISO), prices: {"95", "98", "dsl"}}.
    `reference` pins "today" for the date year-rollover rule; defaults to
    date.today() — pass it explicitly in tests so results don't drift with the clock.
    """
    if reference is None:
        reference = date.today()

    soup = BeautifulSoup(html, "html.parser")
    return [
        row
        for tr in soup.find_all("tr")
        if (row := _parse_row(tr, reference)) is not None
    ]
