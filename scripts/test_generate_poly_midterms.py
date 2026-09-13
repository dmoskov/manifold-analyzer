"""Offline regression checks for midterms dashboard calculations."""

import unittest

from generate_poly_midterms import senate_seat_distribution


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


if __name__ == "__main__":
    unittest.main()
