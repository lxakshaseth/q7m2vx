# Implementation and submission checklist

This document records the implementation state after the final local verification. It replaces the earlier planning checklist, which described Docker and Nginx as future work.

## Completed implementation

- [x] Verified the Elexon FUELHH and WINDFOR stream contracts and documented exact query parameters in [api-findings.md](api-findings.md).
- [x] Built an HTTPX Elexon client with bounded timeouts, retries, response validation, and in-memory caching.
- [x] Normalised timestamps and duplicate/revision semantics.
- [x] Implemented latest-at-or-before day-before-cut-off forecast selection in Europe/London.
- [x] Implemented explicit hourly WINDFOR to half-hour FUELHH expansion.
- [x] Implemented MAE, RMSE, WAPE, bias, coverage, and missing-data reporting.
- [x] Built FastAPI health, dashboard, intervals, and metrics routes with typed response models and sanitised errors.
- [x] Built the React/Vite dashboard with controls, KPIs, charts, audit table, empty/loading/error states, and quality notes.
- [x] Added backend and frontend local-development Dockerfiles.
- [x] Added a Compose development environment with separate Vite and FastAPI services, health check, source mounts, and Vite /api proxy.
- [x] Added a root multi-stage production Dockerfile that builds Vite and packages its static output with FastAPI.
- [x] Configured FastAPI to serve production static files while preserving /api routing and JSON API 404 behavior.
- [x] Added Docker context exclusions for environment files and dependency/build folders.
- [x] Added heroku.yml for the root web image and documented Heroku Container Registry deployment.
- [x] Added the submission README and a timed [demo script](demo-script.md).

## Completed verification

- [x] Backend suite: 57 passed in 1.05 seconds in the Python 3.12 development container.
- [x] Frontend production build: passed with Vite 6.4.5.
- [x] Root production image: built and ran with a non-default PORT.
- [x] Production homepage: HTTP 200 Vite app shell.
- [x] Production /api/health: HTTP 200 JSON.
- [x] Unknown production /api route: JSON HTTP 404, not SPA HTML.
- [x] Production live analysis request for 2026-01-15 at 12:00: HTTP 200, 48 matched intervals and 100% coverage.
- [x] Docker Compose configuration, builds, backend health, frontend homepage, and proxied /api health: passed.

## Remaining human-owned submission actions

- [ ] Choose and add a licence if the course or employer requires one.
- [ ] Create a GitHub repository, commit the checked files, and make it public when ready.
- [ ] Confirm .env files, credentials, and private URLs are absent before publication.
- [ ] Authenticate to Heroku, create an application, push and release the Docker image, and verify the public homepage and /api/health.
- [ ] Add the verified deployment link to README only after that deployment succeeds.
- [ ] Record the ≤10-minute video with current dashboard figures.
- [ ] Check every submitted repository, deployment, API, and video link in an incognito/private browser window.
