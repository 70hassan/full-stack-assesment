# Weather-Aware Truck Routing

A React + Django app that helps a truck driver choose the safest route. The driver enters an
origin, destination, departure time and load weight. The app:

- finds **three route options**,
- samples the weather forecast every **10, 25 or 50 miles**, at the time the truck is expected to
  be at each checkpoint,
- scores every checkpoint with the wind / rain / snow thresholds and the load rules,
- **recommends a route**: fewest Severe miles, then fewest High miles, then lowest average risk,
  then shortest travel time,
- shows the routes, checkpoints, risk levels, ETAs and summaries on a map,
- shows a **weather heatmap along the trip corridor** with a 0–48 hour forecast slider.

## Run it locally

Requires Python 3.12+ and Node 20+.

```bash
# 1. API (http://127.0.0.1:8000)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver

# 2. Web app (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

There is no database and no API key to configure. Tests: `cd backend && python manage.py test`.

To run the production build instead (one server for both the API and the app):

```bash
docker build -t truck-routing . && docker run -p 8000:8000 truck-routing
```

## How it works

```
React (Vite, TypeScript, MapLibre GL)
   │  POST /api/trips/plan/      routes, checkpoints, risk, recommendation
   │  POST /api/trips/heatmap/   48 h of corridor weather (loaded after the routes)
   │  GET  /api/places/?q=       place search for the origin/destination boxes
   ▼
Django REST Framework  ──►  OSRM (routing)  ·  Open-Meteo (forecast, geocoding)
```

| Step | Where | What happens |
|---|---|---|
| Routes | `backend/planner/services/routing.py` | OSRM returns the fastest route and its alternatives. If it returns fewer than three, the rest are found by routing through a waypoint pushed sideways off the fastest route; detours that double back, are much longer, or mostly repeat an existing option are discarded. |
| Checkpoints | `services/trip.py` | A checkpoint every N miles plus both ends. Each ETA comes from the route's turn-by-turn step durations, so it reflects slow and fast stretches rather than one average speed. |
| Weather | `services/weather.py` | One batched Open-Meteo request covers many checkpoints; batches run in parallel and every location is cached for 30 minutes. The value used is the forecast for the hour nearest the ETA. |
| Risk | `services/risk.py` | Pure functions transcribing the threshold table and load rules. A checkpoint's level is the worst of its wind, rain and snow levels. |
| Ranking | `services/scoring.py` | Each checkpoint stands for the road half-way to its neighbours; those stretches give miles per risk level. Routes are sorted by the brief's preference order. |
| Heatmap | `services/heatmap.py` | The corridor (a band about 35 miles either side of every route) is covered with a grid of forecast cells, each with 49 hourly values for wind, rain, snow and risk. |

### Frontend performance

- The plan and the heatmap are separate requests, so the routes appear as soon as they are scored
  and the heatmap fills in behind them.
- Route geometry is simplified on the server (to about 20 m) and sent as an encoded polyline.
- The heatmap is a single GeoJSON source with one property per forecast hour. Moving the slider
  only swaps a paint expression, so nothing is re-uploaded and scrubbing or playing is instant;
  between hours the values are interpolated for a smooth animation.
- Changing the sampling interval re-scores the cached routes and forecasts without reloading the
  heatmap.

## Risk rules as implemented

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules: ≥ 55 mph is No Travel for any load; 45–54 mph with more than 30,000 lb is No Travel;
35–44 mph with more than 40,000 lb is Severe.

Recommendation order: fewest Severe miles → fewest High miles → lowest average risk → shortest
travel time.

Interpretations where the brief leaves room:

- **Band edges** are lower-inclusive, so a value on a shared edge takes the higher level (0.25 in/hr
  of rain is High). The top bands follow the table's own symbols: wind ≥ 55 is No Travel, while
  rain of exactly 1.00 and snow of exactly 3.0 are still Severe.
- **No Travel in the ranking.** The preference list starts at Severe, but No Travel is worse, so
  No Travel miles are compared first. If even the best route has No Travel miles, the app says
  there is no safe option at that departure time rather than recommending it outright.
- **Average risk** is the distance-weighted mean of the levels (Low 0 … No Travel 4).
- **Wind** is the sustained 10 m wind speed. Gusts are shown for information but do not change the
  level.
- **Rain** is liquid precipitation (rain plus showers) in the hour; **snow** is snowfall depth in
  the hour.

## Assumptions and limits

- The truck drives continuously: mandatory rest breaks are not added to the ETAs.
- Travel times come from OSRM's general driving profile, not a truck-specific one.
- Departure must be within the next 10 days, because forecasts reach about two weeks ahead.
- On very long trips at the 10-mile interval, nearby checkpoints share a forecast grid cell
  (from about 3.5 miles across up to at most 28) to stay within the free weather API's limits;
  the cell size used is returned in `meta`.
- Fewer than three options are returned only when no other sensible road exists, and the app says so.
- Caches are in memory, so the app is meant to run as a single process (see the Dockerfile).

## Deploying

**Vercel (used for the hosted demo).** Two projects from this repository: one with Root Directory
`backend` (detected as Django) and one with Root Directory `frontend` (detected as Vite).
`frontend/vercel.json` forwards `/api/*` to the backend project, so the browser talks to a single
origin; change the destination there if the backend URL differs.

**Docker (any container host).** The Dockerfile builds the React app and serves it together with
the API from one container (WhiteNoise + gunicorn). `render.yaml` is a Render blueprint for it. Set
`DJANGO_SECRET_KEY` and `DJANGO_DEBUG=0`.

## Services used

All free and keyless: [OSRM](https://project-osrm.org/) for routing,
[Open-Meteo](https://open-meteo.com/) for forecasts and place search, and
[OpenFreeMap](https://openfreemap.org/) for map tiles (© OpenStreetMap contributors).
