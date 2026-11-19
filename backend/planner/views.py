import logging

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from .serializers import TripSerializer
from .services import geocoding, heatmap, trip
from .services.errors import PlannerError

logger = logging.getLogger(__name__)


def exception_handler(exc, context):
    """Every error leaves the API as {"error": "<message for the user>"}."""
    if isinstance(exc, PlannerError):
        return Response({"error": exc.message}, status=exc.status_code)
    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = {"error": _flatten(response.data)}
    return response


def _flatten(detail, prefix=""):
    if isinstance(detail, dict):
        return " ".join(_flatten(value, f"{prefix}{key}: " if key != "non_field_errors" else prefix)
                        for key, value in detail.items())
    if isinstance(detail, (list, tuple)):
        return " ".join(_flatten(item, prefix) for item in detail)
    return f"{prefix}{detail}"


def _trip_arguments(request):
    serializer = TripSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    origin = (data["origin"]["lat"], data["origin"]["lon"])
    destination = (data["destination"]["lat"], data["destination"]["lon"])
    return data, origin, destination


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class PlaceSearchView(APIView):
    """GET /api/places/?q=denver - suggestions for the origin/destination boxes."""

    def get(self, request):
        return Response({"results": geocoding.search(request.query_params.get("q", ""))})


class TripPlanView(APIView):
    """POST /api/trips/plan/ - route options with checkpoints, risk and a recommendation."""

    def post(self, request):
        data, origin, destination = _trip_arguments(request)
        plan = trip.plan(origin, destination, data["departure_time"], data["load_weight_lb"], data["interval_miles"])
        plan["request"]["origin"]["label"] = data["origin"].get("label", "")
        plan["request"]["destination"]["label"] = data["destination"].get("label", "")
        return Response(plan)


class TripHeatmapView(APIView):
    """POST /api/trips/heatmap/ - 48 hours of corridor weather for the same trip.

    Takes the same body as the plan endpoint and reuses its cached routes, so
    the browser can show the routes first and load the heatmap behind them.
    """

    def post(self, request):
        data, origin, destination = _trip_arguments(request)
        trip.validate(origin, destination, data["departure_time"])
        routes = trip.get_routes(origin, destination)
        return Response(heatmap.build(routes, data["departure_time"], data["load_weight_lb"]))
