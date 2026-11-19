from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("places/", views.PlaceSearchView.as_view(), name="place-search"),
    path("trips/plan/", views.TripPlanView.as_view(), name="trip-plan"),
    path("trips/heatmap/", views.TripHeatmapView.as_view(), name="trip-heatmap"),
]
