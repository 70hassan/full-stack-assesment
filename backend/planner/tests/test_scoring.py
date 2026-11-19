from django.test import SimpleTestCase

from planner.services import scoring
from planner.services.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE


def summary(spans, hours):
    return scoring.summarize(spans, hours * 3600)


class SummarizeTests(SimpleTestCase):
    def test_miles_and_distance_weighted_average(self):
        s = summary([(50, LOW), (30, HIGH), (20, SEVERE)], 2)
        self.assertEqual(s["miles_by_level"], {"low": 50, "moderate": 0, "high": 30, "severe": 20, "no_travel": 0})
        self.assertEqual((s["high_miles"], s["severe_miles"]), (30, 20))
        self.assertAlmostEqual(s["average_risk"], (30 * 2 + 20 * 3) / 100)
        self.assertEqual(s["max_level"], SEVERE)


class RankingTests(SimpleTestCase):
    def test_fewest_severe_miles_beats_everything_else(self):
        fast_but_severe = summary([(90, LOW), (10, SEVERE)], 5)
        slow_and_high = summary([(40, LOW), (60, HIGH)], 9)
        self.assertEqual(scoring.rank([fast_but_severe, slow_and_high]), [1, 0])

    def test_then_fewest_high_miles(self):
        a = summary([(80, LOW), (20, HIGH)], 5)
        b = summary([(50, MODERATE), (50, MODERATE)], 9)  # higher average, but no High miles
        self.assertEqual(scoring.rank([a, b]), [1, 0])

    def test_then_lowest_average_risk(self):
        a = summary([(100, MODERATE)], 5)
        b = summary([(60, LOW), (40, MODERATE)], 9)
        self.assertEqual(scoring.rank([a, b]), [1, 0])

    def test_then_shortest_travel_time(self):
        a = summary([(100, LOW)], 6)
        b = summary([(110, LOW)], 5)
        self.assertEqual(scoring.rank([a, b]), [1, 0])

    def test_no_travel_miles_are_worse_than_severe_miles(self):
        blocked = summary([(95, LOW), (5, NO_TRAVEL)], 5)
        severe = summary([(50, LOW), (50, SEVERE)], 9)
        self.assertEqual(scoring.rank([blocked, severe]), [1, 0])

    def test_explanation_names_the_deciding_criterion(self):
        summaries = [summary([(90, LOW), (10, SEVERE)], 5), summary([(40, LOW), (60, HIGH)], 9)]
        explanation = scoring.explain(summaries, scoring.rank(summaries))
        self.assertEqual(explanation["criterion"], "severe_miles")
        self.assertIn("0 mi vs 10 mi", explanation["text"])

        equal_risk = [summary([(100, LOW)], 6), summary([(110, LOW)], 5)]
        explanation = scoring.explain(equal_risk, scoring.rank(equal_risk))
        self.assertEqual(explanation["criterion"], "duration_seconds")
