"""Unit tests for eu_bulletin.py and the eu_weekly export.

Parser tests run against tests/fixtures/eu_bulletin_slice.xlsx, a committed
slice of the real DG Energy workbook (regenerate with
tests/fixtures/make_eu_fixture.py). The slice keeps FI, SE and IT: SE is the
width-8 case whose block carries an extra exchange-rate column, IT has a
missing week, and DE is deliberately absent so the missing-country path is
exercised too. No network in any test.

The bulletin lives in its own database, so every connection here is a
db.connect_eu() one; fuel.db must never gain an eu_weekly table.
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import db
import eu_bulletin as eu
import export as e

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SLICE_PATH = FIXTURES_DIR / "eu_bulletin_slice.xlsx"

# Newest and oldest weeks in the fixture slice.
NEWEST_WEEK = "2026-08-31"
OLDEST_WEEK = "2026-07-27"
FIXTURE_WEEKS = 6

# Hand-read from the fixture: FI, 2026-08-31, Euro-super 95, with taxes.
FI_95_LATEST_PER_1000L = 2203.2631578947376


class ParseWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.rows = eu.parse_workbook(SLICE_PATH)

    def test_parses_both_tax_variants(self):
        self.assertEqual({row["with_taxes"] for row in self.rows}, {0, 1})

    def test_only_requested_fuels_are_kept(self):
        # No 98E exists in the bulletin, and heating oil / fuel oil / LPG are ignored.
        self.assertEqual({row["fuel"] for row in self.rows}, {"95", "dsl"})

    def test_countries_present_in_the_slice_are_parsed(self):
        self.assertEqual({row["country"] for row in self.rows}, {"FI", "SE", "IT"})

    def test_missing_country_is_skipped_not_fatal(self):
        # DE is absent from the slice; parsing must warn and carry on.
        with self.assertLogs("eu_bulletin", level="WARNING"):
            rows = eu.parse_workbook(SLICE_PATH)
        self.assertTrue(rows)
        self.assertNotIn("DE", {row["country"] for row in rows})

    def test_row_count_is_countries_times_fuels_times_variants_times_weeks(self):
        self.assertEqual(len(self.rows), 3 * 2 * 2 * FIXTURE_WEEKS)

    def test_dates_are_iso_strings(self):
        weeks = sorted({row["week_date"] for row in self.rows})
        self.assertEqual(weeks[0], OLDEST_WEEK)
        self.assertEqual(weeks[-1], NEWEST_WEEK)

    def test_label_and_notes_rows_are_skipped(self):
        # The slice's column A holds two label rows, a blank, and "Notes:" —
        # none of which may become an observation.
        self.assertEqual(len({row["week_date"] for row in self.rows}), FIXTURE_WEEKS)

    def test_non_euro_country_prices_are_already_eur(self):
        # SE's block carries an exchange rate we must NOT apply: its price
        # columns are already converted. A double conversion would land far
        # below the sanity floor.
        se = [r["price"] for r in self.rows if r["country"] == "SE"]
        self.assertTrue(all(0.80 <= p <= 4.00 for p in se), se)


class ConversionTests(unittest.TestCase):
    def test_per_1000_litre_values_are_divided_to_eur_per_litre(self):
        rows = eu.parse_workbook(SLICE_PATH)
        row = next(
            r
            for r in rows
            if r["country"] == "FI"
            and r["fuel"] == "95"
            and r["week_date"] == NEWEST_WEEK
            and r["with_taxes"] == 1
        )
        self.assertAlmostEqual(row["price"], FI_95_LATEST_PER_1000L / 1000)
        self.assertAlmostEqual(row["price"], 2.2033, places=4)

    def test_all_converted_prices_are_plausible_per_litre_values(self):
        prices = [row["price"] for row in eu.parse_workbook(SLICE_PATH)]
        self.assertTrue(all(0.80 <= p <= 4.00 for p in prices))

    def test_column_with_unexpected_unit_is_rejected(self):
        # Guards the per-tonne fuel-oil columns: if a layout change ever moved
        # our fuel code onto one, the unit check must refuse it rather than
        # store tonnes as litres.
        header = ("Date", "CTR", "FI_price_with_tax_euro95")
        units = ("Date", None, "t")
        with self.assertLogs("eu_bulletin", level="WARNING"):
            index = eu._column_index(header, units, "FI_price_with_tax_euro95")
        self.assertIsNone(index)

    def test_column_with_expected_unit_is_accepted(self):
        header = ("Date", "CTR", "FI_price_with_tax_euro95")
        units = ("Date", None, "1000 l")
        self.assertEqual(eu._column_index(header, units, "FI_price_with_tax_euro95"), 2)


class UpsertSanityTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect_eu(":memory:")

    def test_valid_row_stored(self):
        self.assertTrue(db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 2.203))
        row = self.conn.execute(
            "SELECT price FROM eu_weekly WHERE country='FI' AND fuel='95'"
        ).fetchone()
        self.assertEqual(row, (2.203,))

    def test_out_of_bounds_price_rejected(self):
        # 2203.26 is the raw per-1000L figure: forgetting the conversion must
        # be caught by the shared sanity bounds, not silently stored.
        with self.assertLogs("db", level="WARNING"):
            result = db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 2203.26)
        self.assertFalse(result)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0], 0)

    def test_below_bounds_price_rejected(self):
        with self.assertLogs("db", level="WARNING"):
            self.assertFalse(db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 0.5))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0], 0)

    def test_pretax_price_below_the_retail_floor_is_accepted(self):
        # Pre-tax petrol really was ~0.30 EUR/L in 2005; the retail 0.80 floor
        # must not apply to the without-taxes series.
        self.assertTrue(
            db.upsert_eu_weekly(self.conn, "FI", "95", "2005-01-03", 0.314, with_taxes=0)
        )
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0], 1)

    def test_same_price_rejected_for_the_with_taxes_series(self):
        with self.assertLogs("db", level="WARNING"):
            self.assertFalse(
                db.upsert_eu_weekly(self.conn, "FI", "95", "2005-01-03", 0.314, with_taxes=1)
            )
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0], 0)

    def test_pretax_ceiling_still_catches_a_missed_conversion(self):
        # The shared 4.00 ceiling is what guards against storing the raw
        # per-1000-litre figure, in either tax variant.
        with self.assertLogs("db", level="WARNING"):
            self.assertFalse(
                db.upsert_eu_weekly(self.conn, "FI", "95", "2005-01-03", 314.0, with_taxes=0)
            )
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0], 0)

    def test_reupsert_overwrites_same_key(self):
        db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 2.203)
        db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 2.111)
        rows = self.conn.execute(
            "SELECT price FROM eu_weekly WHERE country='FI' AND fuel='95'"
        ).fetchall()
        self.assertEqual(rows, [(2.111,)])

    def test_tax_variants_do_not_collide(self):
        db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 2.203, with_taxes=1)
        db.upsert_eu_weekly(self.conn, "FI", "95", NEWEST_WEEK, 1.100, with_taxes=0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0], 2)

    def test_ingest_rows_reports_stored_count_and_is_idempotent(self):
        rows = eu.parse_workbook(SLICE_PATH)
        first = db.ingest_eu_rows(self.conn, rows)
        second = db.ingest_eu_rows(self.conn, rows)
        self.assertEqual(first, len(rows))
        self.assertEqual(second, len(rows))
        stored = self.conn.execute("SELECT COUNT(*) FROM eu_weekly").fetchone()[0]
        self.assertEqual(stored, len(rows))

    def test_ingest_rows_skips_out_of_bounds_rows(self):
        rows = [
            {"country": "FI", "fuel": "95", "week_date": NEWEST_WEEK, "price": 2.2, "with_taxes": 1},
            {"country": "FI", "fuel": "dsl", "week_date": NEWEST_WEEK, "price": 99.0, "with_taxes": 1},
        ]
        with self.assertLogs("db", level="WARNING"):
            stored = db.ingest_eu_rows(self.conn, rows)
        self.assertEqual(stored, 1)


class SelfGateTests(unittest.TestCase):
    """The workbook is ~4.5 MB and updates weekly; the 12 h cron must not
    refetch it every run."""

    def setUp(self):
        self.conn = db.connect_eu(":memory:")

    def test_empty_table_does_not_skip(self):
        self.assertFalse(eu.should_skip(self.conn, today=date(2026, 9, 3)))

    def test_fresh_data_skips(self):
        db.upsert_eu_weekly(self.conn, "FI", "95", "2026-08-31", 2.203)
        self.conn.commit()
        with self.assertLogs("eu_bulletin", level="INFO"):
            self.assertTrue(eu.should_skip(self.conn, today=date(2026, 9, 3)))

    def test_data_exactly_on_the_gate_boundary_skips(self):
        db.upsert_eu_weekly(self.conn, "FI", "95", "2026-08-31", 2.203)
        self.conn.commit()
        boundary = date(2026, 9, 8)  # 8 days after the stored week
        self.assertTrue(eu.should_skip(self.conn, today=boundary))

    def test_stale_data_does_not_skip(self):
        db.upsert_eu_weekly(self.conn, "FI", "95", "2026-08-31", 2.203)
        self.conn.commit()
        self.assertFalse(eu.should_skip(self.conn, today=date(2026, 9, 9)))

    def test_latest_eu_week_is_the_newest_stored(self):
        db.upsert_eu_weekly(self.conn, "FI", "95", "2026-07-27", 2.1)
        db.upsert_eu_weekly(self.conn, "FI", "95", "2026-08-31", 2.2)
        self.conn.commit()
        self.assertEqual(db.latest_eu_week(self.conn), "2026-08-31")

    def test_update_skips_download_when_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            eu_db_path = Path(tmp) / "eu.db"
            conn = db.connect_eu(eu_db_path)
            db.upsert_eu_weekly(conn, "FI", "95", "2026-08-31", 2.203)
            conn.commit()
            conn.close()

            with patch.object(eu, "download_workbook") as fake_download:
                stored = eu.update(eu_db_path=eu_db_path, today=date(2026, 9, 3))
            fake_download.assert_not_called()
            self.assertEqual(stored, 0)

    def test_update_downloads_and_stores_when_not_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            eu_db_path = Path(tmp) / "eu.db"
            payload = SLICE_PATH.read_bytes()
            with patch.object(eu, "download_workbook", return_value=payload) as fake_download:
                stored = eu.update(eu_db_path=eu_db_path, today=date(2026, 9, 3))
            fake_download.assert_called_once()
            self.assertEqual(stored, 3 * 2 * 2 * FIXTURE_WEEKS)

            conn = db.connect_eu(eu_db_path)
            self.assertEqual(db.latest_eu_week(conn), NEWEST_WEEK)
            conn.close()

    def test_explicit_source_bypasses_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            eu_db_path = Path(tmp) / "eu.db"
            conn = db.connect_eu(eu_db_path)
            db.upsert_eu_weekly(conn, "FI", "95", "2026-08-31", 2.203)
            conn.commit()
            conn.close()

            with patch.object(eu, "download_workbook") as fake_download:
                stored = eu.update(
                    eu_db_path=eu_db_path, today=date(2026, 9, 3), source=SLICE_PATH
                )
            fake_download.assert_not_called()
            self.assertEqual(stored, 3 * 2 * 2 * FIXTURE_WEEKS)


class BuildEuWeeklyTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect_eu(":memory:")
        db.ingest_eu_rows(self.conn, eu.parse_workbook(SLICE_PATH))
        self.data = e.build_eu_weekly(self.conn)

    def test_keyed_by_country_then_fuel(self):
        self.assertEqual(set(self.data), {"FI", "SE", "IT"})
        self.assertEqual(set(self.data["FI"]), {"95", "dsl"})

    def test_sorted_ascending_by_date(self):
        dates = [entry["date"] for entry in self.data["FI"]["95"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[0], OLDEST_WEEK)
        self.assertEqual(dates[-1], NEWEST_WEEK)

    def test_entries_are_date_price_pairs(self):
        entry = self.data["FI"]["95"][-1]
        self.assertEqual(set(entry), {"date", "price"})
        self.assertAlmostEqual(entry["price"], 2.2033, places=4)

    def test_only_with_taxes_rows_exported(self):
        # The DB holds both variants; the export must carry one entry per week.
        self.assertEqual(len(self.data["FI"]["95"]), FIXTURE_WEEKS)
        both = self.conn.execute(
            "SELECT COUNT(*) FROM eu_weekly WHERE country='FI' AND fuel='95'"
        ).fetchone()[0]
        self.assertEqual(both, FIXTURE_WEEKS * 2)

    def test_empty_table_exports_empty_object(self):
        empty = db.connect_eu(":memory:")
        self.assertEqual(e.build_eu_weekly(empty), {})


class ExportFileTests(unittest.TestCase):
    """export() reads two databases: fuel.db for the scraper's three files and
    eu.db for eu_weekly.json."""

    OTHER_FILES = ("stations.json", "history.json", "medians.json")

    def test_export_writes_eu_weekly_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "fuel.db"
            eu_db_path = tmp_path / "eu.db"
            out_dir = tmp_path / "data"

            conn = db.connect_eu(eu_db_path)
            db.ingest_eu_rows(conn, eu.parse_workbook(SLICE_PATH))
            conn.close()

            e.export(db_path=db_path, out_dir=out_dir, eu_db_path=eu_db_path)

            data = json.loads((out_dir / "eu_weekly.json").read_text(encoding="utf-8"))
            self.assertEqual(set(data), {"FI", "SE", "IT"})
            self.assertEqual(len(data["FI"]["dsl"]), FIXTURE_WEEKS)
            self.assertIn("eu_weekly.json", (out_dir / "README.md").read_text(encoding="utf-8"))

    def test_eu_rows_are_not_written_into_fuel_db(self):
        # The whole point of the split: fuel.db is committed on every 12 h poll
        # and must not carry the bulletin's ~1.1 MB.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "fuel.db"
            eu_db_path = tmp_path / "eu.db"

            eu.update(eu_db_path=eu_db_path, source=SLICE_PATH)
            e.export(db_path=db_path, out_dir=tmp_path / "data", eu_db_path=eu_db_path)

            conn = db.connect(db_path)
            fuel_tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            conn.close()
            self.assertNotIn("eu_weekly", fuel_tables)
            self.assertEqual(fuel_tables, {"stations", "prices"})

    def test_export_without_eu_db_still_writes_the_other_three(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out_dir = tmp_path / "data"
            eu_db_path = tmp_path / "absent-eu.db"

            with self.assertLogs("export", level="INFO") as logs:
                e.export(
                    db_path=tmp_path / "fuel.db", out_dir=out_dir, eu_db_path=eu_db_path
                )

            for name in self.OTHER_FILES:
                self.assertTrue((out_dir / name).exists(), name)
            self.assertFalse((out_dir / "eu_weekly.json").exists())
            self.assertTrue((out_dir / "README.md").exists())
            self.assertTrue(
                any("skipping eu_weekly.json" in line for line in logs.output), logs.output
            )

    def test_export_does_not_create_an_eu_db_as_a_side_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            eu_db_path = tmp_path / "absent-eu.db"
            e.export(
                db_path=tmp_path / "fuel.db",
                out_dir=tmp_path / "data",
                eu_db_path=eu_db_path,
            )
            self.assertFalse(eu_db_path.exists())

    def test_export_with_empty_eu_db_skips_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            eu_db_path = tmp_path / "eu.db"
            out_dir = tmp_path / "data"
            db.connect_eu(eu_db_path).close()  # schema, no rows

            with self.assertLogs("export", level="INFO") as logs:
                e.export(
                    db_path=tmp_path / "fuel.db", out_dir=out_dir, eu_db_path=eu_db_path
                )

            for name in self.OTHER_FILES:
                self.assertTrue((out_dir / name).exists(), name)
            self.assertFalse((out_dir / "eu_weekly.json").exists())
            self.assertTrue(
                any("no exportable rows" in line for line in logs.output), logs.output
            )


if __name__ == "__main__":
    unittest.main()
