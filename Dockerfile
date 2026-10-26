# syntax=docker/dockerfile:1

# Build the React/Vite bundle with a same-origin /api base path.
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build


# Keep the static build and FastAPI service together for production platforms.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST_DIR=/app/frontend_dist \
    PORT=8000

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --disable-pip-version-check -r /tmp/requirements.txt

COPY --chown=app:app backend/ /app/backend/
COPY --from=frontend-build --chown=app:app /build/frontend/dist/ /app/frontend_dist/

USER app

EXPOSE 8000

# Heroku overrides PORT; the shell form expands it at container start-up.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
