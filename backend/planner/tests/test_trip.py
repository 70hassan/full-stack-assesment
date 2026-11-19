from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase
from django.urls import reverse

from planner.services import geo, routing, trip, weather

ORIGIN, DESTINATION = (40.0, -100.0), (40.0, -98.0)


def straight_route(lat, hours, name):
    """A west-to-east route along one latitude, driven at constant speed."""
    coords = [(lat, -100.0 + i * 0.02) for i in range(101)]
    cum = geo.cumulative_miles(coords)
    return routing.Route(
        coords=coords, distance_miles=cum[-1], duration_seconds=hours * 3600, name=name,
        profile_miles=[0.0, cum[-1]], profile_seconds=[0.0, hours * 3600], cum_miles=cum,
    )


class FakeForecasts(dict):
    """Calm everywhere, except a 50 mph wind band along latitude 40 east of -99."""

    def __init__(self, start):
        super().__init__()
        self.start = int(start.timestamp()) - 3600

    def __missing__(self, cell):
        lat, lon = cell
        stormy = abs(lat - 40.0) < 0.2 and lon > -99.0
        hours = 60
        return weather.Forecast(
            start=self.start,
            wind=(50.0 if stormy else 10.0,) * hours,
            gust=(60.0 if stormy else 15.0,) * hours,
            rain=(0.0,) * hours,
            snow=(0.0,) * hours,
            temp=(40.0,) * hours,
            code=(3,) * hours,
            utc_offset_seconds=-21600,
            timezone="America/Chicago",
        )


class CheckpointTests(SimpleTestCase):
    def test_markers_include_both_ends(self):
        self.assertEqual(trip.checkpoint_miles(105, 25), [0, 25, 50, 75, 100, 105])
        self.assertEqual(trip.checkpoint_miles(100, 50), [0, 50, 100])
        self.assertEqual(trip.checkpoint_miles(8, 10), [0, 8])

    def test_coverage_spans_tile_the_route_exactly(self):
        miles = trip.checkpoint_miles(105, 25)
        spans = trip.coverage(miles, 105)
        self.assertEqual(spans[0], (0.0, 12.5))
        self.assertEqual(spans[-1], (102.5, 105))
        self.assertAlmostEqual(sum(end - start for start, end in spans), 105)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertEqual(end, start)


class TripApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.departure = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
        self.routes = [
            straight_route(40.0, 2.0, "Direct Highway"),  # fastest, but through the wind
            straight_route(40.6, 2.5, "Northern Loop"),
            straight_route(39.4, 3.0, "Southern Loop"),
        ]
        for target, value in (
            ("planner.services.routing.get_routes", mock.Mock(return_value=self.routes)),
            ("planner.services.weather.get_forecasts",
             mock.Mock(side_effect=lambda points, start, end: FakeForecasts(self.departure))),
        ):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def body(self, **overrides):
        return {
            "origin": {"lat": ORIGIN[0], "lon": ORIGIN[1], "label": "Origin"},
            "destination": {"lat": DESTINATION[0], "lon": DESTINATION[1], "label": "Destination"},
            "departure_time": self.departure.isoformat(),
            "load_weight_lb": 20_000,
            "interval_miles": 10,
            **overrides,
        }

    def post(self, name="trip-plan", **overrides):
        return self.client.post(reverse(name), self.body(**overrides), content_type="application/json")

    def test_recommends_the_calm_route_over_the_fastest(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        plan = response.json()
        self.assertEqual([r["id"] for r in plan["routes"]], ["B", "C", "A"])
        self.assertEqual([r["rank"] for r in plan["routes"]], [1, 2, 3])
        self.assertTrue(plan["routes"][0]["recommended"])
        self.assertEqual(plan["recommendation"]["route_id"], "B")
        self.assertEqual(plan["recommendation"]["criterion"], "duration_seconds")
        self.assertFalse(plan["recommendation"]["no_safe_route"])

        windy = plan["routes"][-1]
        self.assertEqual(windy["summary"]["max_level_key"], "severe")
        # The wind covers the eastern half of the direct route.
        self.assertAlmostEqual(windy["summary"]["severe_miles"], windy["distance_miles"] / 2, delta=6)
        self.assertEqual(windy["summary"]["no_travel_miles"], 0)

    def test_heavy_load_turns_severe_wind_into_no_travel(self):
        plan = self.post(load_weight_lb=42_000).json()
        windy = next(r for r in plan["routes"] if r["id"] == "A")
        self.assertEqual(windy["summary"]["max_level_key"], "no_travel")
        self.assertEqual(windy["summary"]["severe_miles"], 0)
        blown = [c for c in windy["checkpoints"] if c["risk"]["key"] == "no_travel"]
        self.assertTrue(blown and all(c["risk"]["load_rule_applied"] for c in blown))
        self.assertEqual(blown[0]["risk"]["drivers"], ["wind"])

    def test_checkpoints_carry_eta_weather_and_span(self):
        route = self.post().json()["routes"][0]
        checkpoints = route["checkpoints"]
        self.assertEqual(checkpoints[0]["mile"], 0)
        self.assertEqual(checkpoints[1]["mile"], 10)
        self.assertAlmostEqual(checkpoints[-1]["mile"], route["distance_miles"], delta=0.1)

        # Constant speed: the ETA at a checkpoint is proportional to its mile marker.
        middle = checkpoints[len(checkpoints) // 2]
        eta = datetime.fromisoformat(middle["eta"].replace("Z", "+00:00"))
        expected = self.departure + timedelta(seconds=route["duration_seconds"] * middle["mile"] / route["distance_miles"])
        self.assertAlmostEqual(eta.timestamp(), expected.timestamp(), delta=2)
        self.assertEqual(route["arrival_time"], checkpoints[-1]["eta"])

        self.assertEqual(middle["weather"]["wind_mph"], 10.0)
        self.assertEqual(middle["timezone"], "America/Chicago")
        self.assertEqual(checkpoints[0]["span"]["from_mile"], 0)
        self.assertEqual(checkpoints[0]["span"]["to_mile"], 5)
        self.assertLess(middle["span"]["from_index"], middle["span"]["to_index"])
        self.assertEqual(geo.decode_polyline(route["geometry"])[0], (40.6, -100.0))

    def test_miles_by_level_add_up_to_the_route_length(self):
        for route in self.post(interval_miles=25).json()["routes"]:
            self.assertAlmostEqual(sum(route["summary"]["miles_by_level"].values()), route["distance_miles"], delta=0.3)

    def test_heatmap_has_an_hourly_series_per_corridor_cell(self):
        response = self.post("trip-heatmap", load_weight_lb=42_000)
        self.assertEqual(response.status_code, 200)
        heat = response.json()
        self.assertEqual(heat["hours"], 48)
        self.assertGreater(len(heat["points"]), 5)
        for point in heat["points"]:
            self.assertEqual({len(point[k]) for k in ("wind", "rain", "snow", "risk")}, {49})
        self.assertEqual({max(p["risk"]) for p in heat["points"]}, {0, 4})

    def test_rejects_bad_input(self):
        past = (self.departure - timedelta(days=2)).isoformat()
        self.assertEqual(self.post(departure_time=past).status_code, 400)
        far = (self.departure + timedelta(days=30)).isoformat()
        self.assertIn("forecasts", self.post(departure_time=far).json()["error"])
        self.assertEqual(self.post(interval_miles=30).status_code, 400)
        self.assertEqual(self.post(load_weight_lb=-5).status_code, 400)
        same = self.post(destination={"lat": ORIGIN[0], "lon": ORIGIN[1]})
        self.assertIn("same place", same.json()["error"])
