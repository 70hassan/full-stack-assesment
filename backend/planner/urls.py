from django.urls import re_path

from . import views

# The trailing slash is optional so the API works the same behind proxies
# and rewrites that strip it.
urlpatterns = [
    re_path(r"^health/?$", views.HealthView.as_view(), name="health"),
    re_path(r"^places/?$", views.PlaceSearchView.as_view(), name="place-search"),
    re_path(r"^trips/plan/?$", views.TripPlanView.as_view(), name="trip-plan"),
    re_path(r"^trips/heatmap/?$", views.TripHeatmapView.as_view(), name="trip-heatmap"),
]
