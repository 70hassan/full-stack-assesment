"""Django settings for the weather-aware truck routing API."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# Stateless JSON API plus the built React app: no database, sessions or auth.
INSTALLED_APPS = [
    "rest_framework",
    "planner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [FRONTEND_DIST],
        "APP_DIRS": False,
        "OPTIONS": {},
    },
]

DATABASES = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# In production Django also serves the Vite build (frontend/dist) through
# WhiteNoise: hashed files under /assets/ plus index.html for every other path.
STATIC_URL = "/assets/"
STATIC_ROOT = FRONTEND_DIST / "assets"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "planner.views.exception_handler",
}

# --- External services (all free, no API key) -------------------------------
# OSRM-compatible routing servers, tried in order until one answers.
OSRM_BASE_URLS = [
    url.strip().rstrip("/")
    for url in os.environ.get(
        "OSRM_BASE_URLS",
        "https://router.project-osrm.org,https://routing.openstreetmap.de/routed-car",
    ).split(",")
    if url.strip()
]
OPEN_METEO_FORECAST_URL = os.environ.get("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast")
OPEN_METEO_GEOCODING_URL = os.environ.get(
    "OPEN_METEO_GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1/search"
)
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0")
HTTP_CONNECT_TIMEOUT = 6
HTTP_READ_TIMEOUT = float(os.environ.get("HTTP_READ_TIMEOUT", 20))

ROUTE_CACHE_SECONDS = 6 * 60 * 60
WEATHER_CACHE_SECONDS = 30 * 60
GEOCODE_CACHE_SECONDS = 24 * 60 * 60

# --- Trip model -------------------------------------------------------------
ROUTE_OPTIONS = 3
CHECKPOINT_INTERVALS_MILES = (10, 25, 50)
MAX_ROUTE_MILES = 3500
# Open-Meteo forecasts reach 16 days out; leave room for the drive itself
# and for the 48-hour heatmap window after departure.
MAX_DEPARTURE_DAYS_AHEAD = 10
HEATMAP_HOURS = 48
# Upper bounds on distinct weather lookups per request. When a long trip at a
# fine interval would exceed them, nearby points share a forecast grid cell.
MAX_CHECKPOINT_WEATHER_CELLS = 360
MAX_HEATMAP_CELLS = 300

if "test" in sys.argv:
    CACHES["default"] = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
