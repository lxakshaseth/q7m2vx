# Wind Forecast Insight

Wind Forecast Insight is a full-stack dashboard that evaluates national wind-generation forecasts against half-hourly actual Great Britain generation for January 2026.

## Project overview and business problem

Day-ahead electricity-system decisions depend on expected wind output. A simple actual-versus-forecast chart can accidentally use a forecast published after a planner’s decision. This application instead asks: **at a defined day-before decision cut-off, which forecast was actually available, and how accurately did it match the outturn?**

It makes forecast availability, missing data, publication history, cadence conversion, and metric coverage visible. This is an auditable assignment demonstration, not a real-time control, trading, or dispatch system.

## Features

- Select a January 2026 delivery date and a Europe/London decision cut-off.
- Fetch Elexon actuals and forecast versions in FastAPI; the browser never calls Elexon directly.
- Select the latest forecast eligible at the relevant day-before cut-off.
- Reconcile hourly forecasts and half-hourly actuals explicitly.
- Show MAE, RMSE, WAPE, bias, coverage, charts, an audit table, and data-quality notes.
- Preserve missing values rather than filling them with estimates.
- Run separate Vite and FastAPI services for local development.
- Build one production image where FastAPI serves the Vite build and API from one origin.

## Architecture and technology

~~~text
Browser
  │
  ├─ local development: Vite on :5173 ── /api proxy ──► FastAPI on :8000
  │
  └─ production: FastAPI/Uvicorn serves Vite static files and /api on $PORT
                                                     │
                                                     ▼
                       Elexon BMRS FUELHH and WINDFOR public stream APIs
~~~

React is presentation-only. FastAPI owns retrieval, validation, normalisation, forecast selection, cadence expansion, matching, metric calculation, and short-lived in-memory caching. There is no database and no sample-data fallback. See [docs/architecture.md](docs/architecture.md) for the detailed request flow.

| Area | Technology |
| --- | --- |
| Dashboard | React 19, Vite 6, Recharts |
| API | Python 3.12, FastAPI, Uvicorn, HTTPX, Pydantic |
| Data | Elexon BMRS FUELHH and WINDFOR streams |
| Local containers | Docker Compose with Vite and FastAPI services |
| Production | Multi-stage Node build plus Python/FastAPI runtime |
| Deployment target | Heroku Container Registry / Runtime |
| Tests | Pytest and pytest-asyncio |

## Complete project structure

~~~text
.
├─ .dockerignore                         # Root production-build exclusions
├─ .gitignore                            # Env, build, cache, local-data exclusions
├─ Dockerfile                            # Production multi-stage image
├─ docker-compose.yml                    # Separate local frontend/backend services
├─ heroku.yml                            # Heroku web-image declaration
├─ README.md
├─ backend/
│  ├─ .dockerignore                      # Backend Compose-build exclusions
│  ├─ Dockerfile                         # Reloading local FastAPI service
│  ├─ README.md
│  ├─ requirements.txt
│  ├─ requirements-dev.txt
│  ├─ __init__.py
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py                         # FastAPI, static/API routing, errors
│  │  ├─ config.py, domain.py, errors.py, schemas.py
│  │  ├─ api/
│  │  │  ├─ __init__.py
│  │  │  └─ routes.py
│  │  └─ services/
│  │     ├─ __init__.py
│  │     ├─ analysis.py, cache.py, elexon_client.py
│  │     └─ forecast_selection.py, metrics.py, normalization.py
│  └─ tests/
│     ├─ test_analysis_service.py, test_elexon_client.py
│     ├─ test_forecast_selection.py, test_metrics.py
│     ├─ test_normalization.py, test_routes.py
├─ frontend/
│  ├─ .dockerignore                      # Frontend Compose-build exclusions
│  ├─ .env.example                       # Safe local browser-facing defaults
│  ├─ Dockerfile                         # Vite development service
│  ├─ index.html, package.json, package-lock.json, vite.config.js
│  └─ src/
│     ├─ main.jsx, App.jsx, styles.css
│     ├─ api/client.js
│     ├─ components/
│     │  ├─ AnalysisFilters.jsx, DashboardHeader.jsx
│     │  ├─ DataQualityPanel.jsx, ForecastCharts.jsx
│     │  └─ IntervalTable.jsx, MetricCard.jsx, StatusPanel.jsx
│     └─ utils/format.js
├─ docs/
│  ├─ api-findings.md                    # Timestamped source/API investigation
│  ├─ architecture.md
│  ├─ demo-script.md                     # Submission video script (≤10 minutes)
│  ├─ demo-video-script.md               # Pointer to the current script
│  ├─ implementation-checklist.md
│  └─ requirements-notes.md
└─ scripts/
   └─ inspect_elexon_api.py              # Reproducible source investigation
~~~

## Forecast-selection methodology and metric formulas

For each native hourly delivery target, the backend constructs the cut-off on the **preceding Europe/London calendar day** and selects:

~~~text
arg max publishTime
subject to publishTime <= day-before Europe/London decision cut-off
~~~

A forecast published exactly at the cut-off is eligible; later versions are not. Actual FUELHH revisions are normalised by retaining the latest actual publication for the same half-hour start. Exact duplicates are removed. Conflicting values at the same source key are rejected rather than guessed.

WINDFOR is hourly and FUELHH is half-hourly. After selection, the hourly forecast is repeated to its matching :00 and :30 half-hours. The API exposes the transformation and native forecast start so it cannot be mistaken for a native half-hour forecast.

For a matched half-hour, let error = forecast MW - actual MW and n = matched intervals:

~~~text
MAE  = sum(abs(error)) / n
RMSE = sqrt(sum(error²) / n)
Bias = sum(error) / n
WAPE = 100 × sum(abs(error)) / sum(actual MW)
Forecast coverage = 100 × matched intervals / available actual intervals
~~~

Only matched intervals enter the formulas. With no matches, all accuracy metrics are null. With a zero matched actual denominator, WAPE is null. Positive bias means average over-forecasting.

### Configurable decision cut-off

The default is **12:00 Europe/London on the preceding local calendar day**. The assignment did not prescribe a decision time, so this is an adjustable demo assumption, not a claim about an operational policy. It is labelled in UI and API metadata. Ambiguous or nonexistent local times at DST changes are rejected rather than guessed.

## Data sources and verified query parameters

The timestamped live source investigation is in [docs/api-findings.md](docs/api-findings.md). The backend uses only these verified query parameters:

| Dataset | Purpose | Exact backend parameters |
| --- | --- | --- |
| Elexon FUELHH stream | Half-hourly Great Britain WIND outturn | settlementDateFrom, settlementDateTo, fuelType=WIND |
| Elexon WINDFOR stream | Forecast publication history | publishDateTimeFrom, publishDateTimeTo |

FUELHH settlement-date filters target delivery dates and cannot be combined with its publication-time filters. WINDFOR has publication-time filters but no documented delivery-time filter; the backend retrieves bounded history and filters delivery startTime locally. The default history begins seven days before the month and is configurable with FORECAST_LOOKBACK_DAYS.

Official sources:

- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [Elexon OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json)

## API

| Endpoint | Purpose |
| --- | --- |
| GET /api/health | Local liveness response; it does not call Elexon. |
| GET /api/dashboard?month=2026-01&decision_cutoff_time=12:00 | Monthly metrics, summaries, metadata, and intervals. |
| GET /api/intervals?delivery_date=2026-01-15&decision_cutoff_time=12:00 | One local delivery day, its metrics, and intervals. |
| GET /api/metrics?month=2026-01&decision_cutoff_time=12:00 | Monthly metadata and metrics without interval rows. |

In production, FastAPI serves the React single-page app for non-API paths. An unknown GET /api/* path returns JSON HTTP 404 instead of the app shell.

## Windows and VS Code setup

Install Git, Node.js 22 LTS, Python **3.12**, and Docker Desktop using Linux containers. Open this repository in VS Code, create the environment below, then select the .venv interpreter through the VS Code Python extension. Python 3.12 is the verified local/test runtime and matches the Docker images.

Do not commit .env files. frontend/.env.example contains only safe local routing defaults.

### Run without Docker (PowerShell)

From the repository root:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
~~~

In a second PowerShell window:

~~~powershell
Set-Location .\frontend
Copy-Item .env.example .env
npm ci
npm run dev
~~~

Open http://127.0.0.1:5173. Vite proxies /api to FastAPI. Check the API independently:

~~~powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
~~~

## Docker Compose local development

Compose runs two services: Vite with hot reload and Uvicorn with reload. The frontend /api proxy targets the Compose backend service.

~~~powershell
docker compose up --build
~~~

Browse to http://127.0.0.1:5173, then verify both direct and proxied API paths:

~~~powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:5173/api/health
~~~

Stop it with:

~~~powershell
docker compose down
~~~

## Production Docker build and run

The root Dockerfile uses a Node build stage to compile Vite, then copies the static build into a non-root Python runtime. FastAPI serves both the app and /api, while Uvicorn binds to the deployment platform’s PORT environment variable.

~~~powershell
docker build -t wind-forecast-insight:local .
docker run --rm --name wind-forecast-insight -p 8010:8010 -e PORT=8010 wind-forecast-insight:local
~~~

In another PowerShell window:

~~~powershell
Invoke-WebRequest http://127.0.0.1:8010/
Invoke-RestMethod http://127.0.0.1:8010/api/health
Invoke-RestMethod "http://127.0.0.1:8010/api/intervals?delivery_date=2026-01-15&decision_cutoff_time=12:00"
~~~

## Tests and actual verification results

Run backend tests in the Python 3.12 development container used for final verification:

~~~powershell
docker compose build backend
docker run --rm --entrypoint python wind-forecast-intelligence-backend -m pytest /app/backend/tests -q
~~~

Run the standalone frontend production build:

~~~powershell
Set-Location .\frontend
npm run build
~~~

Final local verification results:

| Check | Actual result |
| --- | --- |
| Backend tests in Python 3.12 container | **57 passed in 1.05s** |
| Frontend production build | Passed; Vite 6.4.5 built 627 modules |
| Root production Docker image | Built successfully |
| Production homepage | HTTP 200; returned the Vite app shell |
| Production /api/health | HTTP 200 JSON |
| Unknown production /api/* route | HTTP 404 JSON, not SPA HTML |
| Production live analysis request | HTTP 200; 48 intervals, 48 matched, 100% coverage for 2026-01-15 at 12:00 |
| Docker Compose config and image build | Passed |
| Compose frontend, backend, and proxied health endpoint | HTTP 200 / ok |

The Vite build emits its standard advisory that the minified JavaScript chunk exceeds 500 kB. The build is successful; code splitting is a future performance improvement.

## Heroku Docker deployment

This project is prepared for Heroku’s Docker deployment flow but has **not been deployed from this workspace**: no authorised Heroku account, CLI session, or app name was provided. No public URL is claimed.

heroku.yml declares the root Dockerfile’s web image. With authorised credentials, use:

~~~powershell
heroku login
heroku container:login
heroku create <your-app-name> --stack container

heroku container:push web --app <your-app-name>
heroku container:release web --app <your-app-name>

heroku logs --tail --app <your-app-name>
heroku open --app <your-app-name>
Invoke-WebRequest https://<your-app-name>.herokuapp.com/
Invoke-RestMethod https://<your-app-name>.herokuapp.com/api/health
~~~

For an existing application, set the container stack if needed:

~~~powershell
heroku stack:set container --app <your-app-name>
~~~

Heroku requires the web process to bind to $PORT; the root Dockerfile does so. The Container Runtime supports x86_64 images, so use docker build --platform linux/amd64 on ARM machines when building images manually. EXPOSE and Docker HEALTHCHECK are useful locally but are not Heroku runtime controls. See the official [Heroku Container Registry & Runtime guide](https://devcenter.heroku.com/articles/container-registry-and-runtime).

**Deployment link:** unavailable until an authorised deployment succeeds and both URLs are checked.

## Security and configuration

No secret is required for these public Elexon endpoints. Backend settings are environment-backed and validated; ELEXON_BASE_URL must be an HTTP(S) URL without credentials. .gitignore and all Docker build contexts exclude .env files, local data, dependency folders, caches, and build output. Do not add tokens, credentials, private URLs, or production .env files to this repository.

## AI tools used

[OpenAI Codex](https://openai.com/codex/) was used to inspect the existing codebase, complete and verify container/static-serving integration, update documentation, and run the listed local checks. Source claims are based on the timestamped Elexon investigation and live verification rather than sample fixtures.

## Known limitations and data-quality caveats

- Elexon historical rows can be revised after a recording or deployment; refresh the dashboard before presenting numerical results.
- The source is Great Britain Elexon generation outturn, not a complete UK measurement audit.
- WINDFOR is hourly and FUELHH is half-hourly; repeated forecast values are an explicit analytical choice.
- The seven-day publication lookback is configurable but is not a complete archive of all prior forecast versions.
- The default 12:00 Europe/London cut-off is a demo assumption.
- Missing values lower coverage and are never imputed.
- There is no durable database, user account system, role control, or alerting. Caches are in memory and vanish on restart.
- The frontend has a chunk-size advisory that could be addressed with code splitting.

## Remaining submission steps

1. Review the source and add a licence if submission rules require one.
2. Create a GitHub repository, commit the checked files, and make the repository public only when ready. Confirm no .env or credential files are included.
3. With authorised credentials, deploy using the Heroku instructions above. Add the public URL here only after the homepage and /api/health checks succeed.
4. Record the presentation using [docs/demo-script.md](docs/demo-script.md). Read current on-screen figures immediately before recording instead of reusing a prior result.
5. Open the GitHub repository, deployed homepage, deployed /api/health, and submitted video URLs in an incognito/private browser window to verify access without your logged-in session.
