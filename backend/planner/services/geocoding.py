"""Place search for the origin/destination boxes (Open-Meteo geocoding)."""
import re

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import UpstreamError
from .http import get_json

_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def search(query, limit=6):
    query = " ".join(query.split())
    if len(query) < 2:
        return []

    match = _LATLON.match(query)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return [{"label": f"{lat:.4f}, {lon:.4f}", "name": f"{lat:.4f}, {lon:.4f}", "lat": lat, "lon": lon}]
        return []

    key = f"geocode:{query.lower()}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    # The service matches on the place name only, so "Denver, CO" is searched
    # as "Denver" and the remainder is used to prefer matching regions.
    name, _, region_hint = query.partition(",")
    region_hint = region_hint.strip().lower()
    try:
        status, payload = get_json(
            settings.OPEN_METEO_GEOCODING_URL,
            {"name": name.strip(), "count": 20 if region_hint else limit, "language": "en", "format": "json"},
        )
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError("Place search is not responding. Please try again.") from exc
    if status != 200:
        raise UpstreamError("Place search returned an error. Please try again.")

    results = []
    for item in payload.get("results", []):
        region = item.get("admin1") or ""
        country = item.get("country_code") or item.get("country") or ""
        label = ", ".join(part for part in (item["name"], region, country) if part)
        results.append(
            {
                "label": label,
                "name": item["name"],
                "lat": item["latitude"],
                "lon": item["longitude"],
                "_hint": f"{region} {country} {item.get('country', '')} {item.get('admin2', '')}".lower(),
            }
        )
    if region_hint:
        words = region_hint.replace(",", " ").split()

        def score(result):
            # "CO" is expanded to "colorado"; other words match as prefixes.
            wanted = [_STATE_CODES.get(w.upper(), w).lower() for w in words]
            return sum(any(part.startswith(w) for part in result["_hint"].split()) or w in result["_hint"] for w in wanted)

        results.sort(key=score, reverse=True)
    results = [{k: v for k, v in r.items() if k != "_hint"} for r in results[:limit]]
    cache.set(key, results, settings.GEOCODE_CACHE_SECONDS)
    return results


_STATE_CODES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
