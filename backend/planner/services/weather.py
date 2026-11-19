"""Hourly forecasts from Open-Meteo (free, no API key).

Many locations are requested per HTTP call, calls run in parallel, and every
location's series is cached, so overlapping routes and repeat requests cost
little.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import UpstreamError
from .http import get_json

HOURLY_FIELDS = "temperature_2m,wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,weather_code"
LOCATIONS_PER_CALL = 80
PARALLEL_CALLS = 4
FORECAST_DAYS_AVAILABLE = 15


@dataclass(frozen=True)
class Forecast:
    """Hourly series for one location. Rates are per hour; times are UTC epochs."""

    start: int  # epoch seconds of the first hour
    wind: tuple  # sustained wind, mph
    gust: tuple  # mph
    rain: tuple  # liquid precipitation, inches in the hour
    snow: tuple  # snowfall, inches in the hour
    temp: tuple  # deg F
    code: tuple  # WMO weather code
    utc_offset_seconds: int
    timezone: str  # IANA name, e.g. "America/Denver"

    def index_at(self, epoch_seconds):
        """Index of the forecast hour nearest to a moment, or None if outside."""
        i = round((epoch_seconds - self.start) / 3600)
        return i if 0 <= i < len(self.wind) else None

    def at(self, epoch_seconds):
        i = self.index_at(epoch_seconds)
        if i is None or self.wind[i] is None:
            return None
        return {
            "wind_mph": self.wind[i],
            "gust_mph": self.gust[i],
            "rain_in_per_hr": self.rain[i],
            "snow_in_per_hr": self.snow[i],
            "temperature_f": self.temp[i],
            "weather_code": self.code[i],
        }


def snap(lat, lon, cell_degrees):
    """Centre of the forecast grid cell containing a point."""
    return (round(round(lat / cell_degrees) * cell_degrees, 4), round(round(lon / cell_degrees) * cell_degrees, 4))


def _parse(entry):
    hourly = entry["hourly"]
    rain = tuple(
        None if r is None and s is None else round((r or 0.0) + (s or 0.0), 3)
        for r, s in zip(hourly["rain"], hourly["showers"])
    )
    return Forecast(
        start=hourly["time"][0],
        wind=tuple(hourly["wind_speed_10m"]),
        gust=tuple(hourly["wind_gusts_10m"]),
        rain=rain,
        snow=tuple(hourly["snowfall"]),
        temp=tuple(hourly["temperature_2m"]),
        code=tuple(hourly["weather_code"]),
        utc_offset_seconds=entry.get("utc_offset_seconds", 0),
        timezone=entry.get("timezone", "UTC"),
    )


def _fetch_chunk(points, start_date, end_date):
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        "hourly": HOURLY_FIELDS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timeformat": "unixtime",
        "timezone": "auto",
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        status, payload = get_json(settings.OPEN_METEO_FORECAST_URL, params)
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError(f"The weather service is not responding ({type(exc).__name__}). Please try again.") from exc
    if status == 429:
        raise UpstreamError("The weather service is rate-limiting requests. Please wait a minute and try again.")
    if status != 200:
        reason = payload.get("reason") if isinstance(payload, dict) else status
        raise UpstreamError(f"The weather service returned an error: {reason}")
    entries = payload if isinstance(payload, list) else [payload]
    return {point: _parse(entry) for point, entry in zip(points, entries)}


def get_forecasts(points, start, end):
    """Return {point: Forecast} covering the UTC datetimes `start`..`end`.

    `points` are (lat, lon) tuples, normally already snapped to grid cells.
    """
    today = datetime.now(timezone.utc).date()
    last_available = today + timedelta(days=FORECAST_DAYS_AVAILABLE)
    # Dates are interpreted in each location's own time zone, so pad a day
    # either side to be sure the whole UTC window is covered.
    start_date = max(today - timedelta(days=1), (start - timedelta(days=1)).date()).isoformat()
    end_date = min(last_available, (end + timedelta(days=1)).date()).isoformat()

    def key(point):
        return f"wx:{point[0]}:{point[1]}:{start_date}:{end_date}"

    unique = list(dict.fromkeys(points))
    found = cache.get_many([key(p) for p in unique])
    result = {p: found[key(p)] for p in unique if key(p) in found}
    missing = [p for p in unique if p not in result]
    if missing:
        chunks = [missing[i : i + LOCATIONS_PER_CALL] for i in range(0, len(missing), LOCATIONS_PER_CALL)]
        with ThreadPoolExecutor(max_workers=PARALLEL_CALLS) as pool:
            fetched = {}
            for part in pool.map(lambda chunk: _fetch_chunk(chunk, start_date, end_date), chunks):
                fetched.update(part)
        cache.set_many({key(p): f for p, f in fetched.items()}, settings.WEATHER_CACHE_SECONDS)
        result.update(fetched)
    return result
