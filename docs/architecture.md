# Architecture

## Design summary

Wind Forecast Insight is a small monorepo with a React/Vite dashboard and a FastAPI analysis service. React is responsible only for presentation. FastAPI is the single place that retrieves Elexon data, validates it, applies the forecast-selection rule, reconciles hourly WINDFOR and half-hourly FUELHH data, matches intervals, and calculates metrics.

There is no database. The January analysis has at most 1,488 expected half-hour intervals, and bounded in-memory TTL caches reduce repeat source requests without claiming persistence or reproducibility beyond the retrieved response.

## Runtime topology

~~~mermaid
flowchart LR
    User[Dashboard user]
    FUEL[FUELHH stream<br/>actual WIND generation]
    WIND[WINDFOR stream<br/>forecast versions]

    subgraph Development[Local Docker Compose development]
        Vite[Vite frontend<br/>port 5173]
        APIdev[FastAPI/Uvicorn<br/>port 8000]
        Vite -->|/api proxy| APIdev
    end

    subgraph Production[Production Docker / Heroku web image]
        APIprod[FastAPI/Uvicorn on PORT<br/>serves Vite static build and /api]
    end

    User -->|HTTP| Vite
    User -->|HTTP| APIprod
    APIdev --> Analysis[Retrieval and analysis service]
    APIprod --> Analysis
    Analysis <--> Cache[Bounded in-memory TTL caches]
    Analysis -->|HTTPS JSON| FUEL
    Analysis -->|HTTPS JSON| WIND
~~~

Compose is deliberately a development-only two-service arrangement: source mounts and reload improve iteration. The root multi-stage Dockerfile is the production path: it builds Vite with Node, copies dist into the Python runtime, and FastAPI serves static frontend files for non-API paths. Registered API routes remain available at /api; unknown /api paths return JSON 404 rather than the SPA shell.

## Request flow

1. The dashboard requests a January 2026 delivery date and a configurable Europe/London day-before cut-off.
2. FastAPI checks an in-memory cache keyed by delivery month and cut-off.
3. On a miss, it requests FUELHH with settlementDateFrom, settlementDateTo, and fuelType=WIND.
4. It requests WINDFOR with a bounded publication-time history using publishDateTimeFrom and publishDateTimeTo, then filters delivery startTime locally.
5. For every native forecast hour, it selects the greatest publishTime at or before that delivery date’s preceding-local-day cut-off.
6. It normalises actual revisions, repeats the selected hourly forecast to its matching two half-hours, and joins exact UTC delivery-start keys.
7. It calculates metrics from matched pairs only, returns explicit coverage/data-quality counts, and React renders the result.

## API surface

| Endpoint | Purpose |
| --- | --- |
| GET /api/health | Local liveness check without an upstream request. |
| GET /api/dashboard?month=2026-01&decision_cutoff_time=12:00 | Monthly metrics, summaries, metadata, and interval rows. |
| GET /api/intervals?delivery_date=2026-01-15&decision_cutoff_time=12:00 | One Europe/London delivery date and its interval rows. |
| GET /api/metrics?month=2026-01&decision_cutoff_time=12:00 | Monthly metrics and metadata without interval rows. |

Responses contain:

~~~text
metrics: MAE, RMSE, bias, WAPE, coverage, matched and expected counts
intervals: delivery start, actual/forecast MW, errors, publication times,
           native forecast start, decision cut-off, cadence-expansion flag
metadata: delivery/publication ranges, adjustable cut-off assumption,
          cadence policy, source URLs, duplicate/missing counts, retrieval time
~~~

## Forecast integrity

- The default decision rule is an adjustable 12:00 Europe/London cut-off on the preceding calendar day.
- Forecasts published exactly at the cut-off are eligible; later records are excluded.
- FUELHH duplicates are resolved with the latest actual publication, while forecast versions remain available for selection.
- Missing source values are not interpolated, fabricated, or silently included in metrics.
- The hourly-to-half-hour forecast expansion is exposed in the response and interface.
- API validation prevents malformed query values from triggering broad source requests.

## Containers and deployment

- backend/Dockerfile supports local FastAPI development and reload.
- frontend/Dockerfile supports local Vite development and reload.
- docker-compose.yml connects the services and gives the frontend a same-origin /api proxy.
- The root Dockerfile is a production multi-stage build, runs the Python service as a non-root user, and respects PORT.
- heroku.yml maps the Heroku web image to the root Dockerfile. The repository does not claim a public deployment until authorised credentials have completed one.

## Failure and security posture

- HTTP timeouts and retry counts are bounded; only transport, timeout, 429, and 5xx failures are retried.
- Invalid upstream JSON produces safe API errors rather than fabricated output.
- Error responses and logs avoid upstream response bodies, trace IDs, and credentials.
- Environment settings are validated. ELEXON_BASE_URL rejects URLs with user credentials.
- .env files, node modules, build output, local data, and caches are excluded from Git and Docker build contexts.
