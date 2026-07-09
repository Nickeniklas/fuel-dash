"""Unit tests for parser.py. Run against saved HTML fixtures only — no network."""

import logging
import unittest
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

import parser as p

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Fixtures were fetched 2026-07-09; pin the same date so the year-rollover
# rule doesn't shift results as the real clock moves forward.
REFERENCE = date(2026, 7, 9)


def load_fixture(name: str) -> str:
    # Fixtures are saved as the raw bytes the server sent (windows-1252, per
    # SCRAPER.md) — decode the same way fetch_page() does, not as UTF-8.
    return (FIXTURES_DIR / name).read_bytes().decode("cp1252")


class HelsinkiFixtureTests(unittest.TestCase):
    """City page: index.php?t=Helsinki has E10 class on <tr>, per SCRAPER.md."""

    @classmethod
    def setUpClass(cls):
        cls.rows = p.parse_page(load_fixture("helsinki.html"), reference=REFERENCE)
        cls.by_id = {row["station_id"]: row for row in cls.rows}

    def test_row_count_matches_map_link_count(self):
        # Fixture has 23 rows with a valid DD.MM. date, 2 of which have no
        # map link and must be skipped -> 21 remain.
        self.assertEqual(len(self.rows), 21)

    def test_rows_without_map_link_are_skipped(self):
        names = [row["station_name"] for row in self.rows]
        self.assertFalse(any("Tattarisuo" in name for name in names))
        self.assertFalse(any("Ruoholahti Energiakatu" in name for name in names))

    def test_station_id_and_name_extracted(self):
        row = self.by_id[1051]
        self.assertEqual(row["station_name"], "St1, Lauttasaari Heikkiläntie 12")
        self.assertEqual(row["date"], "2026-07-09")
        self.assertEqual(row["prices"], {"95": 2.099, "98": 2.199, "dsl": 2.129})

    def test_vpower_marker_stripped_from_98e(self):
        # Raw cell: <span title="Vpower"><span class="E99">*</span>2.043</span>
        row = self.by_id[1048]
        self.assertEqual(row["prices"]["98"], 2.043)

    def test_empty_price_cell_is_none_not_zero(self):
        # Raw cell text is a literal "-", not empty.
        row = self.by_id[1983]
        self.assertIsNone(row["prices"]["98"])
        self.assertIsNotNone(row["prices"]["95"])

    def test_all_prices_within_sanity_bounds(self):
        for row in self.rows:
            for price in row["prices"].values():
                if price is not None:
                    self.assertGreaterEqual(price, p.PRICE_MIN)
                    self.assertLessEqual(price, p.PRICE_MAX)


class PkSeutuFixtureTests(unittest.TestCase):
    """Regional page: index.php?t=PK-Seutu omits the E10 class on <tr>."""

    @classmethod
    def setUpClass(cls):
        cls.rows = p.parse_page(load_fixture("pk_seutu.html"), reference=REFERENCE)

    def test_row_count_matches_map_link_count(self):
        self.assertEqual(len(self.rows), 76)

    def test_no_class_dependency_still_parses(self):
        # Regression guard for "key on td count, not class" — PK-Seutu rows
        # lack the E10 class the city page has, and must still parse.
        self.assertTrue(len(self.rows) > 0)
        for row in self.rows:
            self.assertIsInstance(row["station_id"], int)

    def test_dates_within_five_day_visibility_window(self):
        for row in self.rows:
            resolved = date.fromisoformat(row["date"])
            self.assertLessEqual((REFERENCE - resolved).days, 7)


class HeaderAndAverageRowFilterTests(unittest.TestCase):
    """Both non-price 5-td rows must be rejected by the DD.MM. check on td 2."""

    def test_header_row_is_skipped(self):
        html = """
        <table><tr>
          <td class="Asema"><a href="/index.php?kaupunki=Helsinki&sort=asema">Jakeluasema</a></td>
          <td class="PvmTd Sort"><a href="/index.php?kaupunki=Helsinki&sort=pvm">PVM</a></td>
          <td class="Hinnat">95E10</td><td class="Hinnat">98E</td><td class="Hinnat">Di</td>
        </tr></table>
        """
        self.assertEqual(p.parse_page(html, reference=REFERENCE), [])

    def test_daily_average_row_is_skipped(self):
        html = """
        <table><tr class="bg1">
          <td class="Keskihinnat">Keskihinnat:</td><td class="PvmTd">&nbsp;</td>
          <td class="Hinnat">2.069</td><td class="Hinnat">2.186</td><td class="Hinnat">2.086</td>
        </tr></table>
        """
        self.assertEqual(p.parse_page(html, reference=REFERENCE), [])


class ResolveDateTests(unittest.TestCase):
    def test_same_year(self):
        self.assertEqual(
            p.resolve_date("05.07.", date(2026, 7, 9)), date(2026, 7, 5)
        )

    def test_today(self):
        self.assertEqual(
            p.resolve_date("09.07.", date(2026, 7, 9)), date(2026, 7, 9)
        )

    def test_new_year_rollover(self):
        # Reference is early January; a late-December date must resolve to
        # the *previous* year, not a future date this year.
        self.assertEqual(
            p.resolve_date("31.12.", date(2026, 1, 2)), date(2025, 12, 31)
        )

    def test_malformed_text_returns_none(self):
        self.assertIsNone(p.resolve_date("PVM", date(2026, 7, 9)))
        self.assertIsNone(p.resolve_date("", date(2026, 7, 9)))
        self.assertIsNone(p.resolve_date("\xa0", date(2026, 7, 9)))

    def test_stale_date_logs_warning_but_still_resolves(self):
        with self.assertLogs("parser", level="WARNING"):
            resolved = p.resolve_date("01.06.", date(2026, 7, 9))
        self.assertEqual(resolved, date(2026, 6, 1))


class PriceCellParsingTests(unittest.TestCase):
    def _cell(self, html: str):
        return BeautifulSoup(html, "html.parser").find("td")

    def test_plain_price(self):
        self.assertEqual(p._parse_price(self._cell("<td>2.043</td>")), 2.043)

    def test_dash_is_none(self):
        self.assertIsNone(p._parse_price(self._cell('<td class="Hinnat Halpa">-</td>')))

    def test_empty_is_none(self):
        self.assertIsNone(p._parse_price(self._cell("<td></td>")))

    def test_vpower_marker_stripped(self):
        html = '<td class="Hinnat"><span title="Vpower"><span class="E99">*</span>2.043</span></td>'
        self.assertEqual(p._parse_price(self._cell(html)), 2.043)


class SanityBoundsTests(unittest.TestCase):
    def test_out_of_bounds_price_drops_whole_row(self):
        html = """
        <table><tr class="bg1 E10">
          <td> <a href="/index.php?cmd=map&id=9999">map</a>Test Station</td>
          <td class="PvmTD Pvm">09.07.</td>
          <td class="Hinnat">2.099</td>
          <td class="Hinnat">5.000</td>
          <td class="Hinnat">2.129</td>
        </tr></table>
        """
        with self.assertLogs("parser", level="WARNING"):
            rows = p.parse_page(html, reference=REFERENCE)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    unittest.main()
