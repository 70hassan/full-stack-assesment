"""Small geometry helpers: distances, polylines and walking along a line."""
import math
from bisect import bisect_left

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344
MILES_PER_DEGREE_LAT = EARTH_RADIUS_MILES * math.pi / 180


def haversine_miles(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def bearing_degrees(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def offset_point(lat, lon, bearing, miles):
    """The point `miles` away from (lat, lon) in the direction `bearing`."""
    d = miles / EARTH_RADIUS_MILES
    b = math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def decode_polyline(encoded, precision=5):
    """Decode a Google/OSRM encoded polyline into [(lat, lon), ...]."""
    factor = 10**precision
    coords, index, lat, lon = [], 0, 0, 0
    length = len(encoded)
    while index < length:
        for axis in (0, 1):
            result = shift = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


def encode_polyline(coords, precision=5):
    factor = 10**precision
    out, prev_lat, prev_lon = [], 0, 0
    for lat, lon in coords:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def cumulative_miles(coords):
    """Running distance at every vertex of a line; the first value is 0."""
    total, out = 0.0, [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(coords, coords[1:]):
        total += haversine_miles(lat1, lon1, lat2, lon2)
        out.append(total)
    return out


def locate(coords, cum, mile):
    """Return (lat, lon, vertex_index) of the point `mile` miles along a line.

    `vertex_index` is the last vertex at or before that point.
    """
    if mile <= 0:
        return coords[0][0], coords[0][1], 0
    if mile >= cum[-1]:
        return coords[-1][0], coords[-1][1], len(coords) - 1
    i = bisect_left(cum, mile)
    if cum[i] == mile:
        return coords[i][0], coords[i][1], i
    span = cum[i] - cum[i - 1]
    t = (mile - cum[i - 1]) / span if span else 0.0
    (lat1, lon1), (lat2, lon2) = coords[i - 1], coords[i]
    return lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t, i - 1


def interpolate(xs, ys, x):
    """Piecewise-linear interpolation of y at x, clamped to the ends."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_left(xs, x)
    span = xs[i] - xs[i - 1]
    t = (x - xs[i - 1]) / span if span else 0.0
    return ys[i - 1] + (ys[i] - ys[i - 1]) * t


def simplify(coords, tolerance_miles):
    """Douglas-Peucker line simplification (iterative, flat-earth distances)."""
    n = len(coords)
    if n < 3:
        return list(coords)
    cos_lat = math.cos(math.radians(coords[n // 2][0]))
    xs = [lon * MILES_PER_DEGREE_LAT * cos_lat for _, lon in coords]
    ys = [lat * MILES_PER_DEGREE_LAT for lat, _ in coords]
    tolerance_sq = tolerance_miles * tolerance_miles
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        ax, ay = xs[first], ys[first]
        dx, dy = xs[last] - ax, ys[last] - ay
        length_sq = dx * dx + dy * dy
        worst, worst_sq = -1, tolerance_sq
        for i in range(first + 1, last):
            px, py = xs[i] - ax, ys[i] - ay
            if length_sq:
                t = max(0.0, min(1.0, (px * dx + py * dy) / length_sq))
                px, py = px - t * dx, py - t * dy
            d_sq = px * px + py * py
            if d_sq > worst_sq:
                worst, worst_sq = i, d_sq
        if worst != -1:
            keep[worst] = True
            stack.append((first, worst))
            stack.append((worst, last))
    return [c for c, k in zip(coords, keep) if k]
