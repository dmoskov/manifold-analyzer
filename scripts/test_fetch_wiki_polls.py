"""Offline regression checks for Wikipedia polling-table parsing."""

import unittest
from unittest.mock import patch

from fetch_wiki_polls import _end_date, race_polls


def aggregation(candidate="Current Candidate", opp_tag="D"):
    return f'''<table class="wikitable">
      <tr><th>Source of poll aggregation</th><th>Dates administered</th>
      <th>Dates updated</th><th>{candidate} (R)</th><th>Opponent ({opp_tag})</th>
      <th>Undecided</th><th>Margin</th></tr>
      <tr><td>Source A</td><td>September 1–5, 2026</td><td>September 6</td>
      <td>46%</td><td>42%</td><td>12%</td><td>R +4%</td></tr>
      <tr><td>Source B</td><td>September 2–6, 2026</td><td>September 7</td>
      <td>48%</td><td>44%</td><td>8%</td><td>R +4%</td></tr>
      <tr><th colspan="3">Average</th><th>47%</th><th>43%</th>
      <th>10%</th><th>R +4%</th></tr>
    </table>'''


class PollParsingTests(unittest.TestCase):
    def parse(self, html):
        with patch("fetch_wiki_polls._fetch", return_value=html):
            return race_polls("Example", {"R": "Current Candidate", "D": "Opponent"})

    def test_colspan_average_does_not_corrupt_candidate_shares(self):
        poll = self.parse(aggregation())
        self.assertEqual((poll["n"], poll["rep"], poll["opp"], poll["margin"]),
                         (2, 47.0, 43.0, 4.0))
        self.assertEqual(len(poll["sources"]), 2)
        self.assertEqual(poll["latest"], "September 2–6, 2026")
        self.assertTrue(poll["url"].endswith("_Example"))

    def test_full_name_rejects_previous_candidate_with_same_surname(self):
        poll = self.parse(aggregation("Previous Candidate") + aggregation())
        self.assertEqual(poll["n"], 2)
        self.assertIsNone(self.parse(aggregation("Previous Candidate")))

    def test_latest_is_newest_period_not_first_row(self):
        html = aggregation().replace("September 2–6, 2026", "through October 10, 2026")
        self.assertEqual(self.parse(html)["latest"], "through October 10, 2026")

    def test_minnesota_dfl_counts_as_democrat(self):
        poll = self.parse(aggregation(opp_tag="DFL"))
        self.assertEqual((poll["opp_party"], poll["opp"]), ("D", 43.0))

    def test_end_date_formats(self):
        self.assertEqual(_end_date("September 23 – 30, 2026"), (2026, 9, 30))
        self.assertEqual(_end_date("September 18 – October 1, 2026"), (2026, 10, 1))
        self.assertEqual(_end_date("through October 10, 2026"), (2026, 10, 10))
        self.assertEqual(_end_date("October 5–7, 2026"), (2026, 10, 7))
        self.assertIsNone(_end_date("Date unavailable"))

    def test_missing_polling_stays_missing(self):
        self.assertIsNone(self.parse("<p>No general-election polling.</p>"))


if __name__ == "__main__":
    unittest.main()
