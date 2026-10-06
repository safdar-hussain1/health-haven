#!/usr/bin/env python3
"""Check that docs/data/dashboard.json holds what the live demo relies on.

The page's front desk discharges a stay by pricing it from the exported parts:
nights x the room's nightly rate, plus every recorded charge, less the deposit.
Those parts must add up to the balance the application itself quoted for the
same stay, or the bill the page prints would differ from the one the app issues.
Standard library only:

    python3 scripts/test_dashboard_data.py
"""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "docs" / "data" / "dashboard.json").read_text(encoding="utf-8"))


class DashboardDataTest(unittest.TestCase):
    def occupied(self):
        return [b for b in DATA["beds"] if b["state"] == "OCCUPIED"]

    def test_every_stay_prices_to_the_apps_own_quote(self):
        stays = self.occupied()
        self.assertTrue(stays)
        for bed in stays:
            with self.subTest(room=bed["room"]):
                extras = sum(c["quantity"] * c["unitRupees"] for c in bed["charges"])
                balance = bed["nights"] * bed["rate"] + extras - bed["depositRupees"]
                self.assertEqual(balance, bed["quotedBalanceRupees"])

    def test_a_stay_is_at_least_one_night(self):
        for bed in self.occupied():
            self.assertGreaterEqual(bed["nights"], 1, bed["room"])

    def test_occupancy_matches_the_summary(self):
        self.assertEqual(len(self.occupied()), DATA["summary"]["occupiedRooms"])
        self.assertEqual(len(DATA["beds"]), DATA["summary"]["totalRooms"])

    def test_nobody_waiting_is_already_in_a_bed(self):
        in_bed = {b["mrn"] for b in self.occupied()}
        waiting = {p["mrn"] for p in DATA["waiting"]}
        self.assertTrue(waiting)
        self.assertFalse(in_bed & waiting)
        self.assertEqual(len(in_bed) + len(waiting), DATA["summary"]["patients"])

    def test_the_sample_invoice_adds_up(self):
        inv = DATA["sampleInvoice"]
        gross = sum(line["totalRupees"] for line in inv["lines"])
        self.assertEqual(gross, inv["grossTotalRupees"])
        self.assertEqual(gross - inv["depositRupees"], inv["balanceRupees"])
        self.assertEqual(inv["lines"][0]["quantity"], inv["nights"])

    def test_the_fleet_is_exported(self):
        statuses = {a["status"] for a in DATA["ambulances"]}
        self.assertTrue(statuses <= {"AVAILABLE", "DISPATCHED", "MAINTENANCE"})
        self.assertIn("AVAILABLE", statuses)


if __name__ == "__main__":
    unittest.main()
