from django.conf import settings
from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("api/", include("planner.urls")),
]

if settings.FRONTEND_DIST.exists():
    # Single-page app: every non-API path returns the React shell.
    urlpatterns.append(re_path(r"^(?!api/).*$", TemplateView.as_view(template_name="index.html")))
