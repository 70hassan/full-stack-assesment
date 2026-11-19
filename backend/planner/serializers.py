from django.conf import settings
from rest_framework import serializers


class PlaceSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(required=False, allow_blank=True, max_length=200)


class TripSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_time = serializers.DateTimeField(help_text="ISO 8601 with a UTC offset")
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=200_000)
    interval_miles = serializers.ChoiceField(choices=settings.CHECKPOINT_INTERVALS_MILES, default=25)
