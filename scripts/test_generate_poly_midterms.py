"""Offline regression checks for midterms dashboard calculations."""

import unittest

from generate_poly_midterms import battleground_races, senate_seat_distribution


class SenateSeatDistributionTests(unittest.TestCase):
    def test_exact_distribution_from_race_probabilities(self):
        races = [{"rep": 25.0}, {"rep": 60.0}]
        self.assertEqual(senate_seat_distribution(races, fixed_seats=48), [
            {"label": "48", "p": 30.0},
            {"label": "49", "p": 55.0},
            {"label": "50", "p": 15.0},
        ])

    def test_distribution_clamps_prices_to_valid_probability_range(self):
        races = [{"rep": -5.0}, {"rep": 105.0}]
        self.assertEqual(senate_seat_distribution(races, fixed_seats=48), [
            {"label": "49", "p": 100.0},
        ])


class BattlegroundSelectionTests(unittest.TestCase):
    def test_named_battlegrounds_are_included_outside_competitive_band(self):
        races = [
            {"slug": "ohio", "state": "Ohio", "rep": 80.0},
            {"slug": "virginia", "state": "Virginia", "rep": 24.0},
        ]
        self.assertEqual([r["slug"] for r in battleground_races(races)], ["ohio"])

    def test_competitive_band_is_included_and_sorted_by_republican_price(self):
        races = [
            {"slug": "florida", "state": "Florida", "rep": 76.0},
            {"slug": "maine", "state": "Maine", "rep": 31.0},
            {"slug": "michigan", "state": "Michigan", "rep": 40.0},
            {"slug": "kansas", "state": "Kansas", "rep": 74.0},
        ]
        self.assertEqual([r["slug"] for r in battleground_races(races)], [
            "maine", "michigan", "kansas",
        ])


if __name__ == "__main__":
    unittest.main()
