"""Builds the full trip plan: routes -> checkpoints -> weather -> risk -> ranking."""
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings

from . import geo, risk, routing, scoring, weather
from .errors import InvalidRequest

CHECKPOINT_CELL_SIZES_DEGREES = (0.05, 0.1, 0.2, 0.4)
ROUTE_IDS = "ABC"


def checkpoint_miles(total_miles, interval):
    """Mile markers every `interval` miles, always including both ends."""
    miles = [0.0]
    while miles[-1] + interval < total_miles - 0.5:
        miles.append(miles[-1] + interval)
    if total_miles > 0:
        miles.append(total_miles)
    return miles


def coverage(miles, total_miles):
    """The stretch of road each checkpoint stands for: half-way to its neighbours."""
    spans = []
    for i, mile in enumerate(miles):
        start = 0.0 if i == 0 else (miles[i - 1] + mile) / 2
        end = total_miles if i == len(miles) - 1 else (mile + miles[i + 1]) / 2
        spans.append((start, end))
    return spans


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate(origin, destination, departure):
    now = datetime.now(timezone.utc)
    if departure < now - timedelta(hours=1):
        raise InvalidRequest("Departure time is in the past. Choose a time from now onwards.")
    if departure > now + timedelta(days=settings.MAX_DEPARTURE_DAYS_AHEAD):
        raise InvalidRequest(
            f"Weather forecasts only reach about two weeks ahead. Choose a departure within "
            f"{settings.MAX_DEPARTURE_DAYS_AHEAD} days."
        )
    if geo.haversine_miles(*origin, *destination) < 1:
        raise InvalidRequest("Origin and destination are the same place.")


def get_routes(origin, destination):
    routes = routing.get_routes(origin, destination)
    if routes[0].distance_miles > settings.MAX_ROUTE_MILES:
        raise InvalidRequest(
            f"That trip is {routes[0].distance_miles:,.0f} miles; the planner supports up to "
            f"{settings.MAX_ROUTE_MILES:,} miles."
        )
    return routes


def plan(origin, destination, departure, load_lb, interval_miles):
    """`origin`/`destination` are (lat, lon); `departure` is an aware datetime."""
    started = time.perf_counter()
    validate(origin, destination, departure)
    routes = get_routes(origin, destination)
    departure_epoch = departure.timestamp()

    # 1. Checkpoints with their estimated arrival times.
    drafts = []
    for route in routes:
        miles = checkpoint_miles(route.distance_miles, interval_miles)
        points = []
        for mile, (span_start, span_end) in zip(miles, coverage(miles, route.distance_miles)):
            lat, lon, _ = route.locate(mile)
            points.append(
                {
                    "mile": mile,
                    "lat": lat,
                    "lon": lon,
                    "eta_epoch": departure_epoch + route.seconds_at(mile),
                    "span": (span_start, span_end),
                }
            )
        drafts.append(points)

    # 2. One batched forecast lookup for every checkpoint on every route.
    all_points = [(p["lat"], p["lon"]) for points in drafts for p in points]
    for cell_size in CHECKPOINT_CELL_SIZES_DEGREES:
        cells = {weather.snap(lat, lon, cell_size) for lat, lon in all_points}
        if len(cells) <= settings.MAX_CHECKPOINT_WEATHER_CELLS:
            break
    latest = max(points[-1]["eta_epoch"] for points in drafts)
    forecasts = weather.get_forecasts(
        list(cells), departure, datetime.fromtimestamp(latest, timezone.utc)
    )

    # 3. Risk at each checkpoint, then a summary per route.
    results, summaries = [], []
    for route, points in zip(routes, drafts):
        checkpoints, spans, missing = [], [], 0
        for index, p in enumerate(points):
            forecast = forecasts[weather.snap(p["lat"], p["lon"], cell_size)]
            conditions = forecast.at(p["eta_epoch"])
            if conditions is None:
                missing += 1
                assessment = risk.assess(None, None, None, load_lb)
            else:
                assessment = risk.assess(
                    conditions["wind_mph"], conditions["rain_in_per_hr"], conditions["snow_in_per_hr"], load_lb
                )
            span_start, span_end = p["span"]
            spans.append((span_end - span_start, assessment.level))
            checkpoints.append(
                {
                    "index": index,
                    "mile": round(p["mile"], 1),
                    "lat": round(p["lat"], 5),
                    "lon": round(p["lon"], 5),
                    "eta": _iso(datetime.fromtimestamp(p["eta_epoch"], timezone.utc)),
                    "utc_offset_seconds": forecast.utc_offset_seconds,
                    "timezone": forecast.timezone,
                    "weather": conditions,
                    "risk": {
                        "level": assessment.level,
                        "key": risk.LEVEL_KEYS[assessment.level],
                        "label": risk.LEVEL_LABELS[assessment.level],
                        "wind_level": assessment.wind,
                        "rain_level": assessment.rain,
                        "snow_level": assessment.snow,
                        "drivers": assessment.drivers,
                        "load_rule_applied": assessment.load_rule_applied,
                    },
                    # The stretch of road this checkpoint represents, as mile
                    # markers and as indices into the route geometry.
                    "span": {
                        "from_mile": round(span_start, 1),
                        "to_mile": round(span_end, 1),
                        "from_index": route.locate(span_start)[2],
                        "to_index": min(len(route.coords) - 1, route.locate(span_end)[2] + 1),
                    },
                }
            )
        summary = scoring.summarize(spans, route.duration_seconds)
        summaries.append(summary)
        results.append(
            {
                "name": route.name,
                "distance_miles": round(route.distance_miles, 1),
                "duration_seconds": round(route.duration_seconds),
                "arrival_time": checkpoints[-1]["eta"],
                "arrival_utc_offset_seconds": checkpoints[-1]["utc_offset_seconds"],
                "arrival_timezone": checkpoints[-1]["timezone"],
                "summary": {
                    **summary,
                    "max_level_key": risk.LEVEL_KEYS[summary["max_level"]],
                    "max_level_label": risk.LEVEL_LABELS[summary["max_level"]],
                },
                "forecast_missing_checkpoints": missing,
                "geometry": geo.encode_polyline(route.coords),
                "checkpoints": checkpoints,
            }
        )

    # 4. Rank. Routes keep a stable letter by speed (A = fastest).
    for letter, result in zip(ROUTE_IDS, results):
        result["id"] = letter
    order = scoring.rank(summaries)
    for position, i in enumerate(order, start=1):
        results[i]["rank"] = position
        results[i]["recommended"] = position == 1
    explanation = scoring.explain(summaries, order)
    best = summaries[order[0]]

    return {
        "request": {
            "origin": {"lat": origin[0], "lon": origin[1]},
            "destination": {"lat": destination[0], "lon": destination[1]},
            "departure_time": _iso(departure),
            "load_weight_lb": load_lb,
            "interval_miles": interval_miles,
        },
        "routes": [results[i] for i in order],
        "recommendation": {
            "route_id": results[order[0]]["id"],
            "criterion": explanation["criterion"],
            "reason": explanation["text"],
            # Even the best option crosses conditions the rules forbid driving in.
            "no_safe_route": best["no_travel_miles"] > 0,
        },
        "meta": {
            "route_count": len(results),
            "requested_route_count": settings.ROUTE_OPTIONS,
            "weather_lookups": len(cells),
            "weather_cell_degrees": cell_size,
            "processing_ms": round((time.perf_counter() - started) * 1000),
        },
    }
