from django.test import SimpleTestCase

from planner.services import risk
from planner.services.risk import HIGH, LOW, MODERATE, NO_TRAVEL, SEVERE


class ThresholdTests(SimpleTestCase):
    def test_wind_bands(self):
        cases = {0: LOW, 24.9: LOW, 25: MODERATE, 34.9: MODERATE, 35: HIGH, 44.9: HIGH,
                 45: SEVERE, 54.9: SEVERE, 55: NO_TRAVEL, 80: NO_TRAVEL}
        for mph, expected in cases.items():
            self.assertEqual(risk.wind_level(mph), expected, mph)

    def test_rain_bands(self):
        cases = {0: LOW, 0.09: LOW, 0.10: MODERATE, 0.24: MODERATE, 0.25: HIGH, 0.49: HIGH,
                 0.50: SEVERE, 1.00: SEVERE, 1.01: NO_TRAVEL}
        for rate, expected in cases.items():
            self.assertEqual(risk.rain_level(rate), expected, rate)

    def test_snow_bands(self):
        cases = {0: LOW, 0.49: LOW, 0.5: MODERATE, 0.99: MODERATE, 1.0: HIGH, 1.99: HIGH,
                 2.0: SEVERE, 3.0: SEVERE, 3.01: NO_TRAVEL}
        for rate, expected in cases.items():
            self.assertEqual(risk.snow_level(rate), expected, rate)

    def test_missing_values_count_as_low(self):
        self.assertEqual(risk.overall_level(None, None, None, 80_000), LOW)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        for load in (0, 10_000, 80_000):
            self.assertEqual(risk.overall_level(55, 0, 0, load), NO_TRAVEL)

    def test_45_to_54_mph_is_no_travel_only_above_30000_lb(self):
        self.assertEqual(risk.overall_level(50, 0, 0, 30_000), SEVERE)
        self.assertEqual(risk.overall_level(50, 0, 0, 30_001), NO_TRAVEL)
        self.assertEqual(risk.overall_level(45, 0, 0, 45_000), NO_TRAVEL)

    def test_35_to_44_mph_is_severe_only_above_40000_lb(self):
        self.assertEqual(risk.overall_level(40, 0, 0, 40_000), HIGH)
        self.assertEqual(risk.overall_level(40, 0, 0, 40_001), SEVERE)
        # 30,001-40,000 lb is heavy enough for the 45+ rule but not this one.
        self.assertEqual(risk.overall_level(40, 0, 0, 35_000), HIGH)

    def test_load_does_not_change_lower_winds_or_precipitation(self):
        self.assertEqual(risk.overall_level(30, 0, 0, 80_000), MODERATE)
        self.assertEqual(risk.overall_level(0, 0.3, 0, 80_000), HIGH)
        self.assertEqual(risk.overall_level(0, 0, 1.5, 80_000), HIGH)


class AssessmentTests(SimpleTestCase):
    def test_overall_level_is_the_worst_condition(self):
        result = risk.assess(wind_mph=28, rain_in_per_hr=0.6, snow_in_per_hr=0.0, load_lb=20_000)
        self.assertEqual((result.wind, result.rain, result.snow), (MODERATE, SEVERE, LOW))
        self.assertEqual(result.level, SEVERE)
        self.assertEqual(result.drivers, ["rain"])

    def test_reports_when_the_load_rule_escalated(self):
        result = risk.assess(wind_mph=38, rain_in_per_hr=0, snow_in_per_hr=0, load_lb=44_000)
        self.assertTrue(result.load_rule_applied)
        self.assertEqual(result.drivers, ["wind"])
        self.assertFalse(risk.assess(38, 0, 0, 20_000).load_rule_applied)

    def test_low_has_no_drivers(self):
        self.assertEqual(risk.assess(5, 0, 0, 20_000).drivers, [])
