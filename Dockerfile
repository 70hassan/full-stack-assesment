# One image: build the React app, then serve it and the API from Django.

FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build \
    # Pre-compress the bundle; WhiteNoise serves the .gz copies automatically.
    && find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' \) -exec gzip -k9 {} \;

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=0
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
EXPOSE 8000
# One worker so the in-memory route and forecast cache is shared by all
# requests; threads handle concurrency (the work is I/O-bound).
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 120"]
