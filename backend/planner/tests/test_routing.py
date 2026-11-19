from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from planner.services import geo, routing


def route(points, hours=2.0, name="R"):
    cum = geo.cumulative_miles(points)
    return routing.Route(
        coords=points, distance_miles=cum[-1], duration_seconds=hours * 3600, name=name,
        profile_miles=[0.0, cum[-1]], profile_seconds=[0.0, hours * 3600], cum_miles=cum,
    )


def arc(bulge, hours=2.0):
    """From (40,-100) to (40,-98), bowing north (or south) by `bulge` degrees."""
    points = []
    for i in range(101):
        t = i / 100
        points.append((40.0 + bulge * 4 * t * (1 - t), -100.0 + 2 * t))
    return route(points, hours)


class GeometryTests(SimpleTestCase):
    def test_polyline_round_trip_and_reference_value(self):
        coords = geo.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        self.assertEqual(coords, [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])
        self.assertEqual(geo.encode_polyline(coords), "_p~iF~ps|U_ulLnnqC_mqNvxq`@")

    def test_locate_interpolates_along_the_line(self):
        r = arc(0)
        lat, lon, index = r.locate(r.distance_miles / 2)
        self.assertAlmostEqual(lon, -99.0, places=3)
        self.assertEqual(index, 49)
        self.assertEqual(r.locate(-5)[:2], (40.0, -100.0))
        self.assertEqual(r.locate(1e9)[2], 100)

    def test_simplify_keeps_shape_and_drops_collinear_points(self):
        self.assertEqual(len(geo.simplify(arc(0).coords, 0.01)), 2)
        curved = geo.simplify(arc(0.5).coords, 0.01)
        self.assertLess(len(curved), 101)
        self.assertEqual((curved[0], curved[-1]), (arc(0.5).coords[0], arc(0.5).coords[-1]))


class RouteSelectionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_similarity(self):
        self.assertEqual(routing.similarity(arc(0), arc(0)), 1.0)
        self.assertLess(routing.similarity(arc(0), arc(0.6)), 0.5)

    def test_detects_out_and_back_detours(self):
        there = [(40.0, -100.0 + i * 0.001) for i in range(400)]
        self.assertTrue(routing._doubles_back(route(there + there[::-1] + there)))
        self.assertFalse(routing._doubles_back(arc(0.3)))

    def test_tops_up_to_three_distinct_routes_with_detours(self):
        calls = []

        def fake_request(points, alternatives):
            calls.append(len(points))
            if len(points) == 2:
                return [arc(0, 2.0), arc(0.01, 2.1)]  # the "alternative" is the same road
            via_lat = points[1][0]
            if via_lat > 40.0:
                return [arc(0.5, 2.6)]
            return [arc(-0.5, 9.0)]  # absurdly slow: must be rejected

        with mock.patch.object(routing, "_request", side_effect=fake_request):
            routes = routing.get_routes((40.0, -100.0), (40.0, -98.0))

        self.assertEqual(len(routes), 2)  # only one acceptable, distinct detour exists
        self.assertEqual([r.duration_seconds for r in routes], [7200, 2.6 * 3600])
        self.assertEqual(calls[0], 2)
        self.assertTrue(all(n == 3 for n in calls[1:]))

    def test_uses_osrm_alternatives_without_extra_calls_when_there_are_enough(self):
        with mock.patch.object(routing, "_request", return_value=[arc(0), arc(0.5, 2.4), arc(-0.5, 2.8)]) as request:
            routes = routing.get_routes((40.0, -100.0), (40.0, -98.0))
        self.assertEqual(len(routes), 3)
        request.assert_called_once()
