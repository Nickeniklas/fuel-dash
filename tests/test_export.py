"""Unit tests for export.py: build_stations/build_history/build_medians against
an in-memory DB seeded with known rows, plus an end-to-end file-write check."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import db
import export as e

REFERENCE = date(2026, 7, 9)


def seed(conn) -> None:
    """Two stations, two dates, one missing coords, one fuel never reported."""
    db.upsert_station(conn, 1051, "St1, Lauttasaari", REFERENCE)
    db.set_station_coords(conn, 1051, 60.156120, 24.883408)
    db.upsert_price(conn, 1051, "95", "2026-07-08", 2.089)
    db.upsert_price(conn, 1051, "95", "2026-07-09", 2.099)
    db.upsert_price(conn, 1051, "98", "2026-07-09", 2.199)
    # station 1051 never reports dsl

    db.upsert_station(conn, 2002, "Neste, Kehä I", REFERENCE)
    # station 2002 coords never backfilled
    db.upsert_price(conn, 2002, "95", "2026-07-09", 2.199)
    db.upsert_price(conn, 2002, "dsl", "2026-07-09", 2.129)
    conn.commit()


class BuildStationsTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        seed(self.conn)
        self.stations = {s["station_id"]: s for s in e.build_stations(self.conn)}

    def test_all_stations_present(self):
        self.assertEqual(set(self.stations), {1051, 2002})

    def test_coords_included_when_known(self):
        self.assertEqual(self.stations[1051]["lat"], 60.156120)
        self.assertEqual(self.stations[1051]["lon"], 24.883408)

    def test_coords_null_when_missing(self):
        self.assertIsNone(self.stations[2002]["lat"])
        self.assertIsNone(self.stations[2002]["lon"])

    def test_latest_price_is_most_recent_date_per_fuel(self):
        self.assertEqual(
            self.stations[1051]["latest"]["95"], {"date": "2026-07-09", "price": 2.099}
        )

    def test_latest_null_for_fuel_never_reported(self):
        self.assertIsNone(self.stations[1051]["latest"]["dsl"])


class BuildHistoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        seed(self.conn)
        self.history = e.build_history(self.conn)

    def test_keyed_by_station_id_as_string(self):
        self.assertEqual(set(self.history), {"1051", "2002"})

    def test_sorted_oldest_to_newest(self):
        dates = [entry["date"] for entry in self.history["1051"]]
        self.assertEqual(dates, sorted(dates))

    def test_entry_only_has_fuels_reported_that_day(self):
        first_day = self.history["1051"][0]
        self.assertEqual(first_day, {"date": "2026-07-08", "95": 2.089})

    def test_later_day_has_both_fuels_reported(self):
        second_day = self.history["1051"][1]
        self.assertEqual(second_day, {"date": "2026-07-09", "95": 2.099, "98": 2.199})


class BuildMediansTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        seed(self.conn)
        self.medians = {entry["date"]: entry for entry in e.build_medians(self.conn)}

    def test_sorted_oldest_to_newest(self):
        dates = [entry["date"] for entry in e.build_medians(self.conn)]
        self.assertEqual(dates, sorted(dates))

    def test_median_across_two_stations(self):
        self.assertAlmostEqual(self.medians["2026-07-09"]["95"], 2.149)

    def test_single_report_median_is_that_value(self):
        self.assertEqual(self.medians["2026-07-08"]["95"], 2.089)

    def test_null_for_fuel_not_reported_that_day(self):
        self.assertIsNone(self.medians["2026-07-08"]["98"])
        self.assertIsNone(self.medians["2026-07-08"]["dsl"])


class MedianGapFillTests(unittest.TestCase):
    """A polling outage must survive as a hole in the series, not vanish.

    The dashboard plots medians on a categorical axis, so a date with no
    entry is a date with no label: the line would close over the gap and
    read as continuous. Filling the range with null entries is what makes
    the outage visible and countable downstream.
    """

    def setUp(self):
        self.conn = db.connect(":memory:")
        db.upsert_station(self.conn, 1051, "St1, Lauttasaari", REFERENCE)

    def _medians(self):
        return e.build_medians(self.conn)

    def test_interior_hole_becomes_null_entries(self):
        db.upsert_price(self.conn, 1051, "95", "2026-09-02", 2.089)
        db.upsert_price(self.conn, 1051, "95", "2026-09-06", 2.109)
        entries = {m["date"]: m for m in self._medians()}
        self.assertEqual(
            sorted(entries),
            ["2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"],
        )
        for missing in ("2026-09-03", "2026-09-04", "2026-09-05"):
            self.assertIsNone(entries[missing]["95"], missing)
            self.assertIsNone(entries[missing]["98"], missing)
            self.assertIsNone(entries[missing]["dsl"], missing)

    def test_observed_dates_keep_their_values(self):
        db.upsert_price(self.conn, 1051, "95", "2026-09-02", 2.089)
        db.upsert_price(self.conn, 1051, "95", "2026-09-06", 2.109)
        entries = {m["date"]: m for m in self._medians()}
        self.assertEqual(entries["2026-09-02"]["95"], 2.089)
        self.assertEqual(entries["2026-09-06"]["95"], 2.109)

    def test_no_padding_outside_observed_range(self):
        db.upsert_price(self.conn, 1051, "95", "2026-09-02", 2.089)
        db.upsert_price(self.conn, 1051, "95", "2026-09-06", 2.109)
        entries = self._medians()
        self.assertEqual(entries[0]["date"], "2026-09-02")
        self.assertEqual(entries[-1]["date"], "2026-09-06")

    def test_contiguous_series_gains_no_null_entries(self):
        db.upsert_price(self.conn, 1051, "95", "2026-09-02", 2.089)
        db.upsert_price(self.conn, 1051, "95", "2026-09-03", 2.099)
        entries = self._medians()
        self.assertEqual([m["date"] for m in entries], ["2026-09-02", "2026-09-03"])
        self.assertTrue(all(m["95"] is not None for m in entries))

    def test_single_entry_series(self):
        db.upsert_price(self.conn, 1051, "95", "2026-09-02", 2.089)
        entries = self._medians()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["date"], "2026-09-02")
        self.assertEqual(entries[0]["95"], 2.089)

    def test_empty_series(self):
        self.assertEqual(self._medians(), [])

    def test_entry_count_equals_calendar_span(self):
        db.upsert_price(self.conn, 1051, "95", "2026-09-02", 2.089)
        db.upsert_price(self.conn, 1051, "95", "2026-09-20", 2.109)
        entries = self._medians()
        span = (date(2026, 9, 20) - date(2026, 9, 2)).days + 1
        self.assertEqual(len(entries), span)
        nulls = [m for m in entries if m["95"] is None]
        self.assertEqual(len(nulls), span - 2)


class ExportFilesTests(unittest.TestCase):
    """End-to-end: export() writes valid JSON files to disk from a real DB file."""

    def test_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "fuel.db"
            out_dir = tmp_path / "data"

            conn = db.connect(db_path)
            seed(conn)
            conn.close()

            e.export(db_path=db_path, out_dir=out_dir)

            stations = json.loads((out_dir / "stations.json").read_text(encoding="utf-8"))
            history = json.loads((out_dir / "history.json").read_text(encoding="utf-8"))
            medians = json.loads((out_dir / "medians.json").read_text(encoding="utf-8"))

            self.assertEqual({s["station_id"] for s in stations}, {1051, 2002})
            self.assertEqual(set(history), {"1051", "2002"})
            self.assertEqual({m["date"] for m in medians}, {"2026-07-08", "2026-07-09"})
            self.assertTrue((out_dir / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
