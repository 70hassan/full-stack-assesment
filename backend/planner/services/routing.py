"""Route options from OSRM.

OSRM returns the fastest route plus up to a few alternatives, but often only
one or two. The assessment asks for three options, so when OSRM comes up short
the remainder are found by routing through a waypoint pushed sideways off the
fastest route, keeping only results that are sensible, distinct roads.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import requests
from django.conf import settings
from django.core.cache import cache

from . import geo
from .errors import NoRouteFound, UpstreamError
from .http import get_json

# A detour is rejected when it is this much longer or slower than the fastest.
MAX_DETOUR_DISTANCE_RATIO = 1.6
MAX_DETOUR_DURATION_RATIO = 1.7
# Two routes sharing more than this fraction of their length are "the same".
MAX_SIMILARITY = 0.82
DETOUR_BATCH = 4


@dataclass
class Route:
    coords: list  # [(lat, lon), ...]
    distance_miles: float
    duration_seconds: float
    name: str
    # Cumulative (mile, seconds) pairs from the turn-by-turn steps, used to
    # estimate arrival times part-way along the route.
    profile_miles: list = field(default_factory=list)
    profile_seconds: list = field(default_factory=list)
    cum_miles: list = field(default_factory=list)

    def seconds_at(self, mile):
        return geo.interpolate(self.profile_miles, self.profile_seconds, mile)

    def locate(self, mile):
        return geo.locate(self.coords, self.cum_miles, mile)


def _parse(osrm_route):
    # Thinning the line (to ~20 m accuracy) keeps responses and map layers small.
    coords = geo.simplify(geo.decode_polyline(osrm_route["geometry"]), tolerance_miles=0.012)
    distance = osrm_route["distance"] / geo.METERS_PER_MILE
    names, miles, seconds = [], [0.0], [0.0]
    for leg in osrm_route["legs"]:
        for part in leg.get("summary", "").split(", "):
            if part and part not in names:
                names.append(part)
        for step in leg["steps"]:
            miles.append(miles[-1] + step["distance"] / geo.METERS_PER_MILE)
            seconds.append(seconds[-1] + step["duration"])

    # Make the vertex mileage agree with the router's own road distance.
    cum = geo.cumulative_miles(coords)
    scale = distance / cum[-1] if cum[-1] else 1.0
    cum = [m * scale for m in cum]
    if miles[-1] > 0:
        fix = distance / miles[-1]
        miles = [m * fix for m in miles]
    else:
        miles, seconds = [0.0, distance], [0.0, osrm_route["duration"]]

    return Route(
        coords=coords,
        distance_miles=distance,
        duration_seconds=float(osrm_route["duration"]),
        name=", ".join(names[:3]),
        profile_miles=miles,
        profile_seconds=seconds,
        cum_miles=cum,
    )


def _request(points, alternatives):
    """Call OSRM for a route through `points` [(lat, lon), ...]."""
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    params = {
        "overview": "full",
        "geometries": "polyline",
        "steps": "true",
        "alternatives": str(alternatives) if alternatives else "false",
        "continue_straight": "true",
    }
    errors = []
    for base_url in settings.OSRM_BASE_URLS:
        try:
            _, payload = get_json(f"{base_url}/route/v1/driving/{path}", params)
        except (requests.RequestException, ValueError) as exc:
            errors.append(f"{base_url}: {type(exc).__name__}")
            continue
        code = payload.get("code")
        if code in ("NoRoute", "NoSegment"):
            raise NoRouteFound("No drivable route was found between those two places.")
        if code == "Ok" and payload.get("routes"):
            return [_parse(route) for route in payload["routes"]]
        errors.append(f"{base_url}: {payload.get('message') or code}")
    raise UpstreamError("The routing service is not responding. Please try again. (" + " | ".join(errors) + ")")


def _sample(route, count):
    step = route.distance_miles / (count - 1)
    return [route.locate(i * step)[:2] for i in range(count)]


def similarity(a, b, samples=48):
    """Fraction of route `a` that runs along route `b` (0 = disjoint, 1 = same)."""
    tolerance = max(1.5, 0.012 * a.distance_miles)
    b_points = _sample(b, samples * 3)
    close = 0
    for lat, lon in _sample(a, samples):
        if any(geo.haversine_miles(lat, lon, blat, blon) <= tolerance for blat, blon in b_points):
            close += 1
    return close / samples


def _doubles_back(route):
    """True when a route drives out to a point and returns the same way."""
    seen, revisits = {}, 0
    for i, (lat, lon) in enumerate(route.coords):
        key = (round(lat, 3), round(lon, 3))
        first = seen.setdefault(key, i)
        if i - first > 40:
            revisits += 1
    return revisits > max(8, 0.02 * len(route.coords))


def _detour_waypoints(best):
    """Candidate waypoints either side of the fastest route."""
    start, end = best.coords[0], best.coords[-1]
    straight = geo.haversine_miles(*start, *end)
    candidates = []
    for fraction, share in ((0.5, 0.22), (0.5, 0.12), (0.33, 0.16), (0.67, 0.16)):
        offset = min(110.0, max(4.0, share * straight))
        mile = best.distance_miles * fraction
        lat, lon, _ = best.locate(mile)
        ahead = best.locate(min(best.distance_miles, mile + max(1.0, 0.02 * best.distance_miles)))
        heading = geo.bearing_degrees(lat, lon, ahead[0], ahead[1])
        for side in (90, -90):
            candidates.append(geo.offset_point(lat, lon, heading + side, offset))
    return candidates


def _detours(best, origin, destination, existing, needed):
    def fetch(waypoint):
        try:
            return _request([origin, waypoint, destination], alternatives=0)[0]
        except (NoRouteFound, UpstreamError):
            return None

    def acceptable(route):
        return (
            route is not None
            and route.distance_miles <= best.distance_miles * MAX_DETOUR_DISTANCE_RATIO
            and route.duration_seconds <= best.duration_seconds * MAX_DETOUR_DURATION_RATIO
            and not _doubles_back(route)
        )

    # Waypoints are tried a few at a time, stopping as soon as enough distinct
    # routes have been found, to stay polite to the free routing server.
    waypoints = _detour_waypoints(best)
    found = []
    with ThreadPoolExecutor(max_workers=DETOUR_BATCH) as pool:
        for start in range(0, len(waypoints), DETOUR_BATCH):
            found += [r for r in pool.map(fetch, waypoints[start : start + DETOUR_BATCH]) if acceptable(r)]
            distinct = []
            for route in sorted(found, key=lambda r: r.duration_seconds):
                if all(similarity(route, kept) < MAX_SIMILARITY for kept in existing + distinct):
                    distinct.append(route)
            if len(distinct) >= needed:
                break
    return distinct


def get_routes(origin, destination, count=None):
    """Return up to `count` distinct routes, fastest first.

    `origin` and `destination` are (lat, lon) tuples.
    """
    count = count or settings.ROUTE_OPTIONS
    key = "routes:{:.4f},{:.4f}:{:.4f},{:.4f}:{}".format(*origin, *destination, count)
    cached = cache.get(key)
    if cached is not None:
        return cached

    routes = []
    for route in _request([origin, destination], alternatives=count):
        if all(similarity(route, kept) < MAX_SIMILARITY for kept in routes):
            routes.append(route)
    routes = routes[:count]

    if len(routes) < count:
        needed = count - len(routes)
        routes += _detours(routes[0], origin, destination, routes, needed)[:needed]

    routes.sort(key=lambda r: r.duration_seconds)
    cache.set(key, routes, settings.ROUTE_CACHE_SECONDS)
    return routes
