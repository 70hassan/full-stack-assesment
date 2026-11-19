"""Weather risk rules for a truck at one place and time.

Pure functions with no I/O: everything here is a direct transcription of the
assessment's threshold table and load rules, so it is easy to test and audit.
"""
from dataclasses import dataclass

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)
LEVEL_KEYS = ("low", "moderate", "high", "severe", "no_travel")
LEVEL_LABELS = ("Low", "Moderate", "High", "Severe", "No Travel")

# Each tuple holds the lower bounds of Moderate, High, Severe and No Travel.
# Bands are lower-inclusive: 25 mph is Moderate, 35 mph is High, and so on.
WIND_MPH_BOUNDS = (25, 35, 45, 55)  # >= 55 mph is No Travel
RAIN_IN_PER_HR_BOUNDS = (0.10, 0.25, 0.50)  # > 1.00 in/hr is No Travel
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_IN_PER_HR_BOUNDS = (0.5, 1.0, 2.0)  # > 3.0 in/hr is No Travel
SNOW_NO_TRAVEL_ABOVE = 3.0

# Load rules: wind that is tolerable for a lighter truck is escalated when
# the load is heavier than the stated weight.
HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # 45-54 mph and heavier than this -> No Travel
HEAVY_LOAD_SEVERE_LB = 40_000  # 35-44 mph and heavier than this -> Severe


def wind_level(mph):
    if mph is None:
        return LOW
    return sum(mph >= bound for bound in WIND_MPH_BOUNDS)


def rain_level(inches_per_hour):
    if inches_per_hour is None:
        return LOW
    if inches_per_hour > RAIN_NO_TRAVEL_ABOVE:
        return NO_TRAVEL
    return sum(inches_per_hour >= bound for bound in RAIN_IN_PER_HR_BOUNDS)


def snow_level(inches_per_hour):
    if inches_per_hour is None:
        return LOW
    if inches_per_hour > SNOW_NO_TRAVEL_ABOVE:
        return NO_TRAVEL
    return sum(inches_per_hour >= bound for bound in SNOW_IN_PER_HR_BOUNDS)


def wind_level_for_load(mph, load_lb):
    """Wind level after the load rules. Returns (level, load_rule_applied)."""
    level = wind_level(mph)
    if level == SEVERE and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return NO_TRAVEL, True
    if level == HIGH and load_lb > HEAVY_LOAD_SEVERE_LB:
        return SEVERE, True
    return level, False


@dataclass(frozen=True)
class Assessment:
    level: int
    wind: int  # after load rules
    rain: int
    snow: int
    load_rule_applied: bool

    @property
    def drivers(self):
        """The condition(s) responsible for the overall level, if above Low."""
        if self.level == LOW:
            return []
        factors = (("wind", self.wind), ("rain", self.rain), ("snow", self.snow))
        return [name for name, level in factors if level == self.level]


def assess(wind_mph, rain_in_per_hr, snow_in_per_hr, load_lb):
    """Overall risk is the worst of the wind, rain and snow levels."""
    wind, load_rule_applied = wind_level_for_load(wind_mph, load_lb)
    rain = rain_level(rain_in_per_hr)
    snow = snow_level(snow_in_per_hr)
    return Assessment(max(wind, rain, snow), wind, rain, snow, load_rule_applied)


def overall_level(wind_mph, rain_in_per_hr, snow_in_per_hr, load_lb):
    return assess(wind_mph, rain_in_per_hr, snow_in_per_hr, load_lb).level
