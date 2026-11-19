"""Weather along the trip corridor for the 48 hours after departure.

The corridor is the band of land either side of all route options. It is
covered with a regular grid of forecast cells; each cell carries an hourly
series, so the browser can scrub through time without further requests.
"""
from datetime import timedelta

from django.conf import settings

from . import geo, risk, weather

SAMPLE_EVERY_MILES = 12
LATERAL_OFFSETS_MILES = (0, 18, 36)
CELL_SIZES_DEGREES = (0.25, 0.35, 0.5, 0.75, 1.0)


def corridor_cells(routes, max_cells):
    """Grid cells within the corridor, at the finest size that fits `max_cells`."""
    points = []
    for route in routes:
        steps = max(1, round(route.distance_miles / SAMPLE_EVERY_MILES))
        previous = None
        for i in range(steps + 1):
            lat, lon, _ = route.locate(route.distance_miles * i / steps)
            heading = geo.bearing_degrees(*previous, lat, lon) if previous and previous != (lat, lon) else None
            previous = (lat, lon)
            points.append((lat, lon))
            if heading is None:
                continue
            for offset in LATERAL_OFFSETS_MILES[1:]:
                points.append(geo.offset_point(lat, lon, heading + 90, offset))
                points.append(geo.offset_point(lat, lon, heading - 90, offset))

    for size in CELL_SIZES_DEGREES:
        cells = list(dict.fromkeys(weather.snap(lat, lon, size) for lat, lon in points))
        if len(cells) <= max_cells:
            break
    return cells, size


def build(routes, departure, load_lb):
    """Return hourly wind, rain, snow and risk for every corridor cell."""
    hours = settings.HEATMAP_HOURS
    start = departure.replace(minute=0, second=0, microsecond=0)
    cells, size = corridor_cells(routes, settings.MAX_HEATMAP_CELLS)
    forecasts = weather.get_forecasts(cells, start, start + timedelta(hours=hours))

    start_epoch = int(start.timestamp())
    points = []
    for cell in cells:
        forecast = forecasts[cell]
        first = forecast.index_at(start_epoch)
        if first is None:
            continue
        wind, rain, snow, level = [], [], [], []
        for i in range(first, first + hours + 1):
            ok = i < len(forecast.wind) and forecast.wind[i] is not None
            w = forecast.wind[i] if ok else 0.0
            r = (forecast.rain[i] or 0.0) if ok else 0.0
            s = (forecast.snow[i] or 0.0) if ok else 0.0
            wind.append(round(w))
            rain.append(round(r, 2))
            snow.append(round(s, 2))
            level.append(risk.overall_level(w, r, s, load_lb))
        points.append({"lat": cell[0], "lon": cell[1], "wind": wind, "rain": rain, "snow": snow, "risk": level})

    return {
        "start_time": start.isoformat().replace("+00:00", "Z"),
        "hours": hours,
        "cell_degrees": size,
        "points": points,
    }
